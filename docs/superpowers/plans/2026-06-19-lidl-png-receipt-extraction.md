# Lidl PNG Receipt Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract structured data (store, date, UNP, items, totals) from Lidl receipt **PNG** images via Tesseract OCR + a Lidl-specific parser, feeding the existing database/web pipeline alongside the Kaufland PDF path.

**Architecture:** OCR runs **inside the Docker container** (Debian base + apt Tesseract `bul`). `extract/ocr.py` turns a PNG into text; `extract/parse_lidl.py` turns that text into the **same `ParsedReceipt`/`LineItem`** dataclasses used by the Kaufland parser, so `normalize`/`categorize`/`build_db`/API are reused. `build_db` routes `*.pdf`→Kaufland and `*.png`→Lidl, stores the source bytes as a blob with a `media_type`, and the web modal previews images with `<img>`.

**Tech Stack:** Python 3.12, Tesseract 5 (`tesseract-ocr`, `tesseract-ocr-bul`), pytesseract, Pillow, pytest; FastAPI; React/Vite; Docker Compose.

## Global Constraints

- **No git repo** in this project (per project CLAUDE.md). Replace every "commit" with a **Checkpoint**: run the task's full verification and stop for review. Do **not** run `git`.
- **Reuse** `ParsedReceipt`, `LineItem`, `_sanitize_text`, `_sanitize_name` from `extract/parse.py`. Do **not** duplicate them.
- **Do not change** the Kaufland PDF path (`extract/parse.py`) behaviour.
- **All amounts stored in EUR.** Lidl receipts are EUR (`currency="EUR"`), so `build_db`'s conversion factor is 1.0 for them.
- **No silent drops:** unmatched item-region lines go to `ParsedReceipt.unparsed` → `data/unparsed_lines.log`.
- Host Python: `./venv/Scripts/python.exe` (the bare `python` is the Store stub — never use it).
- Receipts live at `C:\Users\s.demirov\My Drive\1Kaufland Receipts` (`RECEIPTS_DIR`); PNGs stay there mixed with the PDFs.
- Windows UTF-8: any script printing Cyrillic must `sys.stdout.reconfigure(encoding="utf-8")`.

---

### Task 1: `parse_lidl_text` — the Lidl parser (pure, fixture-driven, host)

Pure text→`ParsedReceipt` so it's testable **without** the tesseract binary. This is the core logic.

**Files:**
- Create: `extract/parse_lidl.py`
- Create: `tests/test_parse_lidl.py`
- Create: `tests/fixtures/lidl_sample_1.txt`
- Modify: `requirements.txt` (add deps)

**Interfaces:**
- Consumes: `LineItem`, `ParsedReceipt`, `_sanitize_text`, `_sanitize_name` from `extract/parse.py`.
- Produces:
  - `parse_lidl_text(text: str, source: str) -> ParsedReceipt`
  - module-level regexes reused by Task 2's wrapper.

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:
```
pytesseract==0.3.13
Pillow==11.0.0
pytest==8.3.4
```
Install into the host venv (pytesseract imports fine without the binary; it's only needed at OCR call time):
```bash
./venv/Scripts/python.exe -m pip install pytesseract==0.3.13 Pillow==11.0.0 pytest==8.3.4
```

- [ ] **Step 2: Create the OCR-text fixture** `tests/fixtures/lidl_sample_1.txt`

Real-shaped Lidl OCR text (qty line precedes the item; trailing single-letter VAT):
```
# Евро #
2,00 x 0,97
СОДА ВОДА 1,94 Б
НАЙЛОНОВА ТОРБИЧКА 0,15 Б
2,00 x 1,10
БИО КИСЕЛО МЛЯКО 2,20 Б
МЕЖДИННА СУМА 4,29
ОБЩА СУМА 4,29
42,99 (лв)
ОБМЕНЕН КУРС 1 EUR = 1.95583 ЛВ
КРЕДИТНА / ДЕБИТНА КАРТ 4,29
УНП: BN013286-0009-0559315
05.04.2026 18:14:45 3 АРТИКУЛА
```

- [ ] **Step 3: Write the failing test** `tests/test_parse_lidl.py`

```python
from pathlib import Path
from extract.parse_lidl import parse_lidl_text

FIX = Path(__file__).parent / "fixtures" / "lidl_sample_1.txt"


def _parsed():
    return parse_lidl_text(FIX.read_text(encoding="utf-8"), "lidl_sample_1.png")


def test_metadata():
    r = _parsed()
    assert r.unp == "BN013286-0009-0559315"
    assert r.purchase_date == "2026-04-05"
    assert r.currency == "EUR"
    assert r.total == 4.29
    assert r.subtotal == 4.29
    assert r.payment_method == "Карта"


def test_items():
    r = _parsed()
    assert len(r.items) == 3
    soda, bag, milk = r.items
    assert (soda.raw_name, soda.qty, soda.unit_price, soda.line_total, soda.vat_class) \
        == ("СОДА ВОДА", 2, 0.97, 1.94, "Б")
    assert (bag.qty, bag.unit_price, bag.line_total) == (1, 0.15, 0.15)
    assert (milk.qty, milk.unit_price, milk.line_total) == (2, 1.10, 2.20)
    assert not r.unparsed


def test_item_count_matches_checksum():
    r = _parsed()
    assert r.item_count_hint == 3
    assert len(r.items) == r.item_count_hint
```

- [ ] **Step 4: Run test to verify it fails**

Run: `./venv/Scripts/python.exe -m pytest tests/test_parse_lidl.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'extract.parse_lidl'`.

- [ ] **Step 5: Write `extract/parse_lidl.py`**

```python
"""Parse a Lidl receipt PNG (via OCR) into the shared ParsedReceipt model.

Lidl layout differs from Kaufland: the quantity line ("2,00 x 0,97") PRECEDES
the item's name+total line, totals are "МЕЖДИННА СУМА"/"ОБЩА СУМА", currency is
EUR ("Евро" header). OCR is noisy (0<->д<->8, Б often read as В), so patterns are
tolerant and amounts accept both ',' and '.' decimals.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from extract.parse import (LineItem, ParsedReceipt, _sanitize_name,
                           _sanitize_text)

UNP_RE = re.compile(r"УНП[:\s]+([A-Za-zА-Яа-я0-9-]+)")
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b")
COUNT_RE = re.compile(r"(\d+)\s+АРТИКУЛ")
SUBTOTAL_RE = re.compile(r"МЕЖДИННА\s+СУМА\s+(\d+[.,]\d{2})")
TOTAL_RE = re.compile(r"ОБЩА\s+СУМА\s+(\d+[.,]\d{2})")
STORE_RE = re.compile(r"Лидл[^\n]*")

# item-region boundaries
ITEM_START_RE = re.compile(r"Евро")                       # currency header line
ITEM_END_RE = re.compile(r"^(МЕЖДИННА|ОБЩА)\s+СУМА")
# a qty line:  "2,00 x 0,97"  (x / х / *)
QTY_RE = re.compile(r"^(?P<qty>\d+)[.,]\d{2,3}\s*[xх*]\s*(?P<unit>\d+[.,]\d{2})$")
# an item line: "<name> <amount> <VAT-letter>"
ITEM_RE = re.compile(r"^(?P<name>.+?)\s+(?P<amt>\d+[.,]\d{2})\s+(?P<vat>[А-Я])$")
PAY_CARD_RE = re.compile(r"КАРТ", re.I)
PAY_CASH_RE = re.compile(r"В\s*БРОЙ", re.I)
VAT_FIX = {"В": "Б"}  # common OCR confusion: В read where Б was printed


def _money(s: str) -> float:
    return float(s.replace(",", "."))


def parse_lidl_text(text: str, source: str) -> ParsedReceipt:
    text = _sanitize_text(text)
    lines = [ln.strip() for ln in text.splitlines()]
    r = ParsedReceipt(source_pdf=source, raw_text=text,
                      currency="EUR", store_name="Лидл")

    if m := UNP_RE.search(text):
        r.unp = m.group(1)
    if m := DATE_RE.search(text):
        dd, mm, yy = m.groups()
        if 1 <= int(dd) <= 31 and 1 <= int(mm) <= 12:
            r.purchase_date = f"{yy}-{mm}-{dd}"
    if m := COUNT_RE.search(text):
        r.item_count_hint = int(m.group(1))
    if m := STORE_RE.search(text):
        r.store_name = _sanitize_name(m.group(0))
        if b := re.search(r"(\d{2,4})\s*$", r.store_name):
            r.branch_id = b.group(1)
    if m := SUBTOTAL_RE.search(text):
        r.subtotal = _money(m.group(1))
    if m := TOTAL_RE.search(text):
        r.total = _money(m.group(1))
    if r.subtotal is None:
        r.subtotal = r.total
    if PAY_CARD_RE.search(text):
        r.payment_method = "Карта"
    elif PAY_CASH_RE.search(text):
        r.payment_method = "В брой"

    # locate item region
    start = next((i for i, ln in enumerate(lines) if ITEM_START_RE.search(ln)), None)
    if start is None:
        return r
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if ITEM_END_RE.match(lines[i]):
            end = i
            break

    pending: Optional[tuple[int, float]] = None
    for line in lines[start + 1:end]:
        if not line:
            continue
        if m := QTY_RE.match(line):
            pending = (int(m.group("qty")), _money(m.group("unit")))
            continue
        if m := ITEM_RE.match(line):
            amt = _money(m.group("amt"))
            vat = VAT_FIX.get(m.group("vat"), m.group("vat"))
            name = _sanitize_name(m.group("name"))
            if pending:
                qty, unit = pending
                r.items.append(LineItem(name, qty, unit, amt, vat))
            else:
                r.items.append(LineItem(name, 1, amt, amt, vat))
            pending = None
            continue
        pending = None
        r.unparsed.append(line)
    return r
```

- [ ] **Step 6: Add the `item_count_hint` field to `ParsedReceipt`**

In `extract/parse.py`, inside the `ParsedReceipt` dataclass (after `points: Optional[int] = None`):
```python
    item_count_hint: Optional[int] = None  # "N АРТИКУЛА" checksum (Lidl)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_parse_lidl.py -v`
Expected: 3 passed.

- [ ] **Step 8: Checkpoint**

Run the full suite; expect all green:
```bash
./venv/Scripts/python.exe -m pytest -v
```

---

### Task 2: `extract/ocr.py` + `parse_lidl` wrapper + Tesseract in Docker

Add the real OCR step and put Tesseract in the image. Integration is verified in the container against a real PNG.

**Files:**
- Create: `extract/ocr.py`
- Modify: `extract/parse_lidl.py` (add `parse_lidl(path)` wrapper)
- Modify: `Dockerfile` (apt Tesseract)
- Modify: `docker-compose.yml` (mount receipts read-only; set `RECEIPTS_DIR`)

**Interfaces:**
- Consumes: `parse_lidl_text` (Task 1).
- Produces:
  - `ocr_image(path: str | Path) -> str`
  - `parse_lidl(path: str | Path) -> ParsedReceipt`

- [ ] **Step 1: Write `extract/ocr.py`**

```python
"""PNG receipt -> text via Tesseract (Bulgarian). Light preprocessing helps the
thermal-print digit noise. Requires the system `tesseract` binary + `bul` data
(installed in the Docker image)."""
from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image, ImageOps


def ocr_image(path: str | Path) -> str:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = ImageOps.grayscale(img)
    w, h = img.size
    if max(w, h) < 2000:                      # upscale small scans
        img = img.resize((w * 2, h * 2))
    img = ImageOps.autocontrast(img)
    return pytesseract.image_to_string(img, lang="bul")
```

- [ ] **Step 2: Add the `parse_lidl` wrapper to `extract/parse_lidl.py`**

At the end of the module:
```python
def parse_lidl(path: str | Path) -> ParsedReceipt:
    from extract.ocr import ocr_image  # lazy: only needs tesseract at call time
    return parse_lidl_text(ocr_image(path), Path(path).name)
```

- [ ] **Step 3: Add Tesseract to the `Dockerfile` runtime stage**

After `WORKDIR /app` and the `ENV` block, before `COPY requirements.txt`:
```dockerfile
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-bul \
 && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 4: Mount receipts + set RECEIPTS_DIR in `docker-compose.yml`**

Under `services.app`, extend `volumes` and add `environment`:
```yaml
    volumes:
      - ./data:/app/data
      - "C:/Users/s.demirov/My Drive/1Kaufland Receipts:/receipts:ro"
    environment:
      - RECEIPTS_DIR=/receipts
```

- [ ] **Step 5: Build the image**

Run: `docker compose build`
Expected: build succeeds (apt installs tesseract; pip installs pytesseract/Pillow).

- [ ] **Step 6: Verify `bul` and OCR end-to-end in the container**

```bash
docker compose run --rm app tesseract --list-langs
docker compose run --rm app python -c "import sys; sys.stdout.reconfigure(encoding='utf-8'); from extract.parse_lidl import parse_lidl; r=parse_lidl('/receipts/Файл_000 (1).png'); print(r.unp, r.purchase_date, r.total, 'items=', len(r.items), 'hint=', r.item_count_hint)"
```
Expected: `bul` listed; the second command prints a UNP, a date, a total, and a non-zero item count.

- [ ] **Step 7: Checkpoint**

Host unit tests still green (no tesseract needed):
```bash
./venv/Scripts/python.exe -m pytest -v
```

---

### Task 3: `build_db` routing + PNG blob + `media_type`

Route by extension, store the source bytes (PDF or PNG) with a media type.

**Files:**
- Modify: `extract/build_db.py` (`SCHEMA`, `parse_all`, blob insert)

**Interfaces:**
- Consumes: `parse_lidl` (Task 2), `parse_receipt` (existing).
- Produces: `receipt_pdfs(receipt_id, pdf BLOB, media_type TEXT)` populated for both types.

- [ ] **Step 1: Add `media_type` to the blob table in `SCHEMA`**

In `extract/build_db.py`, change the `receipt_pdfs` table definition to:
```sql
CREATE TABLE receipt_pdfs (
    receipt_id      INTEGER PRIMARY KEY REFERENCES receipts(id),
    pdf             BLOB,
    media_type      TEXT
);
```

- [ ] **Step 2: Route PDFs and PNGs in `parse_all()`**

Replace the body of `parse_all()` with:
```python
def parse_all() -> list[ParsedReceipt]:
    from extract.parse_lidl import parse_lidl
    sources = sorted(RECEIPTS_DIR.glob("*.pdf")) + sorted(RECEIPTS_DIR.glob("*.png"))
    receipts, unparsed_log = [], []
    for p in sources:
        r = parse_lidl(p) if p.suffix.lower() == ".png" else parse_receipt(p)
        receipts.append(r)
        for line in r.unparsed:
            unparsed_log.append(f"{r.source_pdf}\t{line}")
    UNPARSED_LOG.write_text("\n".join(unparsed_log), encoding="utf-8")
    return receipts
```

- [ ] **Step 3: Store the blob with its media type**

In `main()`, replace the PDF-blob insert block with:
```python
        src_path = RECEIPTS_DIR / r.source_pdf
        if src_path.exists():
            media = "image/png" if src_path.suffix.lower() == ".png" else "application/pdf"
            cur.execute(
                "INSERT INTO receipt_pdfs (receipt_id, pdf, media_type) VALUES (?, ?, ?)",
                (rid, src_path.read_bytes(), media))
```

- [ ] **Step 4: Add a sanity-check report to `main()`**

After the de-dup loop produces `kept`, before writing the DB, add:
```python
    for r in kept:
        if r.item_count_hint and len(r.items) != r.item_count_hint:
            print(f"  [check] {r.source_pdf}: parsed {len(r.items)} items "
                  f"but receipt says {r.item_count_hint}")
        if r.total and r.items:
            s = round(sum(it.line_total for it in r.items), 2)
            if abs(s - r.total) > 0.05:
                print(f"  [check] {r.source_pdf}: items sum {s} != total {r.total}")
```

- [ ] **Step 5: Rebuild the DB in the container**

```bash
docker compose run --rm app python -m extract.build_db
```
Expected: prints receipts/line_items/products counts higher than the PDF-only baseline; lists any `[check]` mismatches; `data/unparsed_lines.log` written (review it).

- [ ] **Step 6: Verify Lidl rows landed**

```bash
docker compose run --rm app python -c "import sqlite3,sys; sys.stdout.reconfigure(encoding='utf-8'); c=sqlite3.connect('data/receipts.db'); print('png receipts:', c.execute(\"select count(*) from receipts where source_pdf like '%.png'\").fetchone()[0]); print('png blobs:', c.execute(\"select count(*) from receipt_pdfs where media_type='image/png'\").fetchone()[0])"
```
Expected: both counts > 0 (up to 43, minus any UNP-less/duplicate).

- [ ] **Step 7: Checkpoint** — review `data/unparsed_lines.log` and any `[check]` lines; note receipts needing parser refinement (handled in Task 6).

---

### Task 4: API serves the blob with its stored media type

**Files:**
- Modify: `api/main.py` (`receipt_pdf` endpoint)

**Interfaces:**
- Consumes: `receipt_pdfs.media_type` (Task 3).
- Produces: `GET /receipts/{rid}/pdf` responding with the correct `Content-Type`.

- [ ] **Step 1: Read and return the stored media type**

Replace the `receipt_pdf` function body:
```python
@app.get("/receipts/{rid}/pdf")
def receipt_pdf(rid: int):
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute(
            "SELECT pdf, media_type FROM receipt_pdfs WHERE receipt_id = ?",
            (rid,)).fetchone()
    finally:
        con.close()
    if not row or row[0] is None:
        raise HTTPException(404, "media not found")
    media_type = row[1] or "application/pdf"
    return Response(content=row[0], media_type=media_type,
                    headers={"Content-Disposition": "inline"})
```

- [ ] **Step 2: Verify the content types**

Start the API (container already serves it on :8090). For a PNG receipt id `<P>` and a PDF receipt id `<D>` (from Task 3's query / `/receipts`):
```bash
curl -s -o /dev/null -w "%{content_type}\n" http://localhost:8090/api/receipts/<P>/pdf
curl -s -o /dev/null -w "%{content_type}\n" http://localhost:8090/api/receipts/<D>/pdf
```
Expected: `image/png` and `application/pdf` respectively.

- [ ] **Step 3: Checkpoint** — host unit tests green: `./venv/Scripts/python.exe -m pytest -v`.

---

### Task 5: Web modal previews images with `<img>`

The receipt detail already returns `source_pdf`; branch the preview on its extension.

**Files:**
- Modify: `web/src/components/ReceiptModal.jsx`

**Interfaces:**
- Consumes: `data.receipt.source_pdf`, `api.pdfUrl(rid)`.
- Produces: image receipts render `<img>`; PDFs keep the iframe.

- [ ] **Step 1: Compute an `isImage` flag**

In `ReceiptModal`, after `const r = data?.receipt;`:
```jsx
  const isImage = !!r?.source_pdf && /\.png$/i.test(r.source_pdf);
```

- [ ] **Step 2: Relabel the preview tab**

Change the third tab button text:
```jsx
              <button className={tab === "pdf" ? "on" : ""} onClick={() => setTab("pdf")}>{isImage ? "Снимка" : "PDF"}</button>
```

- [ ] **Step 3: Render `<img>` for images**

Replace the `{tab === "pdf" && (...)}` block with:
```jsx
              {tab === "pdf" && (
                <div className="pdf-view">
                  <div className="pdf-actions">
                    <a href={api.pdfUrl(rid)} target="_blank" rel="noreferrer">Отвори в нов раздел ↗</a>
                    <a href={api.pdfUrl(rid)} download={`${r.purchase_date || "receipt"}${isImage ? ".png" : ".pdf"}`}>⬇ Изтегли {isImage ? "снимка" : "PDF"}</a>
                  </div>
                  {isImage
                    ? <img className="pdf-frame" alt="receipt" src={api.pdfUrl(rid)} style={{ width: "100%", objectFit: "contain" }} />
                    : <iframe className="pdf-frame" title="receipt pdf" src={api.pdfUrl(rid)} />}
                </div>
              )}
```

- [ ] **Step 4: Rebuild the web bundle and verify**

```bash
cd web && PATH=/c/nvm4w/nodejs:$PATH npm run build
```
Then `docker compose build && docker compose up -d`, open http://localhost:8090, open a Lidl (PNG) receipt → the "Снимка" tab shows the photo; open a Kaufland receipt → the "PDF" tab still renders the PDF.

- [ ] **Step 5: Checkpoint** — manual UI check above passes for both a PNG and a PDF receipt.

---

### Task 6: Run over all 43 PNGs, refine, document

Iterate parser regexes against real OCR until the batch is clean, then update docs.

**Files:**
- Modify: `extract/parse_lidl.py` (only if real receipts reveal unhandled layouts)
- Modify: `CLAUDE.md`, `docs/extraction.md` (document the Lidl path + counts)

- [ ] **Step 1: Full rebuild + capture diagnostics**

```bash
docker compose run --rm app python -m extract.build_db | tee /tmp/build.log
```
Review every `[check]` line and `data/unparsed_lines.log`.

- [ ] **Step 2: For each recurring unparsed pattern, add a fixture + test, then fix the regex**

For a new layout line `L` seen in the log: add it to a new `tests/fixtures/lidl_sample_N.txt`, write a failing test asserting the expected `LineItem`, then adjust the relevant regex in `extract/parse_lidl.py` (re-run `./venv/Scripts/python.exe -m pytest -v` to green). Repeat until the log is empty or only genuinely illegible receipts remain (note those explicitly).

- [ ] **Step 3: Confirm the batch result**

```bash
docker compose run --rm app python -c "import sqlite3,sys; sys.stdout.reconfigure(encoding='utf-8'); c=sqlite3.connect('data/receipts.db'); print('lidl receipts:', c.execute(\"select count(*) from receipts where source_pdf like '%.png'\").fetchone()[0]); print('lidl items:', c.execute(\"select count(*) from line_items li join receipts r on r.id=li.receipt_id where r.source_pdf like '%.png'\").fetchone()[0])"
```
Expected: receipts close to 43 (minus any UNP-less/duplicate, which build_db reports), items > 0, with the count of any still-unparsed receipts explicitly recorded.

- [ ] **Step 4: Document**

In `CLAUDE.md` ("What this is" + a new "Lidl PNG receipts" note) and `docs/extraction.md`: record that `*.png` → `extract/parse_lidl.py` via Tesseract-in-Docker, the qty-before-name layout, EUR, the `media_type` blob column, and the new dataset counts. Update the run instructions to note `docker compose run --rm app python -m extract.build_db`.

- [ ] **Step 5: Checkpoint** — `./venv/Scripts/python.exe -m pytest -v` green; build log shows no unexplained `[check]`/unparsed lines.

---

## Self-Review

**Spec coverage:**
- OCR-in-Docker → Task 2 (Dockerfile apt, compose mount). ✓
- Tesseract `bul` + pytesseract/Pillow → Task 1 deps + Task 2 image. ✓
- `extract/ocr.py` preprocessing → Task 2. ✓
- `extract/parse_lidl.py` reusing dataclasses, qty-before-name, single-line, totals, EUR, UNP, date, store → Task 1. ✓
- build_db routing by extension + PNG blob + media_type → Task 3. ✓
- Sanity checks (count vs `АРТИКУЛА`, sum vs total) + unparsed log → Task 3/Task 6. ✓
- API media type → Task 4. ✓
- Web `<img>` preview → Task 5. ✓
- Mixed folder, EUR factor=1.0, no-Kaufland-change → Global Constraints + Task 3. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. Task 6 Step 2 is intentionally data-driven iteration but specifies the exact TDD procedure. ✓

**Type consistency:** `parse_lidl_text(text, source)` and `parse_lidl(path)` consistent across Tasks 1–3; `ocr_image` signature consistent (Task 2 def, Task 2 wrapper); `item_count_hint` defined in `parse.py` (Task 1 Step 6) and used in Tasks 1/3; `receipt_pdfs.media_type` defined (Task 3) and read (Task 4); `LineItem(name, qty, unit_price, line_total, vat)` positional order matches the dataclass field order in `parse.py`. ✓
