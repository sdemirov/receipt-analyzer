# Lidl PNG Receipt Extraction — Design

**Date:** 2026-06-19
**Status:** Approved (design); pending implementation plan

## Problem

The analyzer currently extracts products & prices only from **Kaufland digital
receipt PDFs** (text layer, read with pdfplumber — no OCR). The user has added
**43 Lidl receipts as PNG images** (`Файл_000 (N).png`) into the same source
folder. PNGs have no text layer, and Lidl's receipt layout differs from
Kaufland's. We need to extract the **same structured data** (store, date, UNP,
items with qty/unit_price/line_total/VAT, subtotal/total, payment) from these
images and feed it through the existing database/web pipeline.

## Decisions (locked)

- **Extraction method:** Tesseract OCR (`bul` language) → a new Lidl-specific
  regex parser. (Not a vision LLM, not cloud OCR.)
- **OCR runtime:** Tesseract runs **inside the Docker container** (Debian
  `python:3.12-slim` base → apt packages). Not installed on the Windows host.
- **Source files:** PNGs **stay in** `1Kaufland Receipts`; `build_db` routes by
  extension (`*.pdf` → Kaufland, `*.png` → Lidl).
- **Reuse:** Lidl parser returns the **same** `ParsedReceipt` / `LineItem`
  dataclasses, so `normalize`, `categorize`, `build_db`, search, and the API are
  reused unchanged.
- **Preview:** Store PNG bytes as a blob (self-contained like the PDFs); the web
  UI renders an `<img>` for image receipts (PDF.js cannot render PNG).

## Verified feasibility (2026-06-19)

Ran a throwaway `python:3.12-slim` container with the receipts folder mounted:
`apt-get install -y tesseract-ocr tesseract-ocr-bul` → Tesseract 5.5.0 with
`bul`. OCR of `Файл_000 (1).png` produced readable but **noisy** Cyrillic text.

Observed Lidl layout (from real OCR):

```
# Евро #                         ← item-region start; currency = EUR
2,00 x 0,97                       ← multi-qty line (qty x unit) PRECEDES the name
SCHWEPPES СОДА ВОДА 1,94 Б        ← name  line_total  VAT      (2,00*0,97 = 1,94)
НАЙЛОНОВА ТОРБИЧКА M 0,15 Б       ← single item: name  price  VAT  (qty 1)
...
МЕЖДИННА СУМА 21,98               ← subtotal
ОБЩА СУМА 21,98                   ← total
42,99 (лв)                        ← BGN equivalent (informational)
ОБМЕНЕН КУРС 1 EUR = 1.95583 ЛВ   ← exchange-rate line
КРЕДИТНА / ДЕБИТНА КАРТ 21,98     ← payment method
УНП: BN013286-0009-0559315        ← unique receipt number (dedupe key)
05.04.2026 18:14:45 13 АРТИКУЛА   ← date, time, item count (checksum)
```

### Key differences from Kaufland (drive the parser)

1. **Qty line precedes the name** (Kaufland: qty line *follows* the name).
2. **OCR noise**: digits confuse (`0↔д↔8↔9`), VAT `Б` often reads as `В`,
   Latin↔Cyrillic in codes (`BN`→`ВМ`). Parser must be tolerant; image
   preprocessing reduces this.
3. Currency header is `Евро` (EUR), totals are `МЕЖДИННА СУМА` / `ОБЩА СУМА`.

## Architecture

New code is additive; the Kaufland path is untouched.

```
extract/
  ocr.py         NEW  ocr_image(path) -> str   (Pillow preprocess + pytesseract bul)
  parse_lidl.py  NEW  parse_lidl(path) -> ParsedReceipt   (reuses parse.py dataclasses)
  parse.py            unchanged (Kaufland)
  build_db.py    EDIT parse_all() globs *.png too; route by extension; store PNG blob
config.py        EDIT RECEIPTS_DIR already covers the folder; no new dir
Dockerfile       EDIT apt-get tesseract-ocr + tesseract-ocr-bul
requirements.txt EDIT add pytesseract, Pillow
docker-compose.yml EDIT mount receipts folder read-only; set RECEIPTS_DIR=/receipts
api/main.py      EDIT serve blob with correct media type (or expose source ext)
web/             EDIT PdfView (or a wrapper) renders <img> for *.png receipts
```

### Components

- **`extract/ocr.py` — `ocr_image(path) -> str`**
  - Open with Pillow; preprocess: convert to grayscale, upscale (~2x), and
    binarize/threshold to sharpen thermal-print glyphs.
  - `pytesseract.image_to_string(img, lang="bul")`; return raw text.
  - Depends on: Pillow, pytesseract, the system `tesseract` binary + `bul` data.
  - Testable in isolation: feed a sample PNG, assert non-empty Cyrillic text.

- **`extract/parse_lidl.py` — `parse_lidl(path) -> ParsedReceipt`**
  - Calls `ocr_image`, sanitises text (reuse `_sanitize_text`/`_sanitize_name`
    from `parse.py`), then regex-parses.
  - **Metadata:** `УНП` (`УНП:\s*(\S+)`), date `(\d{2})\.(\d{2})\.(\d{4})`
    (ISO-normalised), `store_name` from the `Лидл …`/address lines (fallback
    constant `"Лидл"`), currency `EUR` (from `Евро`/`ОБМЕНЕН КУРС`), payment
    from `КАРТ`/`БРОЙ` lines, item-count checksum from `(\d+)\s+АРТИКУЛА`.
  - **Item region:** between the `Евро` header and `МЕЖДИННА СУМА`/`ОБЩА СУМА`.
  - **Line layouts** (tolerant to OCR noise; `,`/`.` decimals, `x`/`х`):
    1. **Multi-qty:** a `qty x unit` line immediately followed by a
       `name … line_total VAT` line → one `LineItem(qty, unit_price=unit,
       line_total)`.
    2. **Single:** `name … price VAT` (qty=1).
  - Returns the same `ParsedReceipt`; unmatched item-region lines go to
    `.unparsed` (no silent drops).
  - Depends on: `ocr.py`, `parse.py` dataclasses/helpers.

- **`extract/build_db.py` (edit)**
  - `parse_all()` collects `RECEIPTS_DIR.glob("*.pdf")` → `parse_receipt` and
    `RECEIPTS_DIR.glob("*.png")` → `parse_lidl`.
  - De-dup (by `unp`), mapping, meta, and DB write are unchanged.
  - Blob storage: store the source bytes regardless of type. Rename the table
    concept to hold any receipt media — keep `receipt_pdfs` table name for
    minimal churn but store PNG bytes for image receipts; add a `media_type`
    column (`application/pdf` | `image/png`) so the API/web can choose a
    renderer. (`source_pdf` column already records the filename incl. extension,
    which is sufficient to distinguish; `media_type` is the explicit signal.)

- **`api/main.py` (edit)** — the receipt-media endpoint returns the blob with the
  stored `media_type` (or derives it from the filename extension).

- **`web/` (edit)** — the receipt preview chooses its renderer by media type /
  extension: existing PDF.js canvas for `*.pdf`, a plain `<img>` for `*.png`.

## Data flow

```
PNG ─ ocr_image ─► raw text ─ parse_lidl ─► ParsedReceipt
                                              │ (same type as PDF path)
build_db.parse_all ──────────────────────────┘
   ├─ de-dup by unp
   ├─ build/extend product_mapping.csv  (normalize)
   ├─ brand/category (categorize)
   └─ write receipts / line_items / products / receipt_pdfs(blob+media_type)
API + web  ── serve data; preview <img> for image receipts
```

## Robustness (OCR is noisy — no silent drops)

- **Image preprocessing** in `ocr.py` to cut digit/letter confusion.
- **Per-receipt sanity checks** logged during build:
  - parsed item count vs the `N АРТИКУЛА` value;
  - `sum(line_total)` vs `ОБЩА СУМА`.
  - Mismatches are reported (stderr/log), not fatal.
- **`unparsed_lines.log`** captures any item-region line matching no layout,
  tagged with the source PNG — same mechanism as the PDF path. First place to
  look when adding receipts with a new quirk.

## Testing

- **`ocr.py`:** OCR a checked-in sample PNG → non-empty text containing expected
  anchors (`ОБЩА СУМА`, `АРТИКУЛА`).
- **`parse_lidl.py`:** unit tests over saved OCR-text fixtures (so tests don't
  require the tesseract binary): assert metadata, item count, and that
  `sum(line_total) ≈ total`. Cover both line layouts and a noisy-digit case.
- **Integration:** `docker compose exec dra python -m extract.build_db` →
  reports Lidl receipts + items; spot-check one via the API and the web `<img>`
  preview.

## Out of scope / non-goals

- No vision-LLM or cloud-OCR path.
- No change to the Kaufland PDF parser behaviour.
- No new store beyond Lidl in this iteration.
- No automatic image deskew beyond basic preprocessing unless OCR quality
  requires it (revisit if sanity checks fail widely).

## Risks

- **OCR accuracy on some receipts** may break item parsing (skew, low contrast).
  Mitigation: preprocessing + sanity checks + unparsed log; iterate on the
  worst offenders. Acceptable outcome: a small number flagged for manual review
  rather than silently wrong.
- **UNP OCR errors** could weaken de-dup. Low impact: these PNGs are not
  re-downloads, so collisions are unlikely; sanity logging will surface any.
- **Receipts-folder mount** adds a host path to compose. Read-only mount; no
  write risk to the source receipts.
