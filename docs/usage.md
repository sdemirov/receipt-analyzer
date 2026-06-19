# Usage

## Prerequisites

- **Python 3.12** (installed at `C:\Users\s.demirov\AppData\Local\Programs\Python\Python312`
  on this machine).
- **Node.js** (for the React app only) — already present via `nvm4w`.
- **Docker** (for the full build including Lidl PNGs — Tesseract runs in the container).
- The receipts, organised in per-store subfolders under
  `C:\Users\s.demirov\My Drive\DigitalReceipts`:
  - `Kaufland/*.pdf` — digital text PDFs (no OCR)
  - `Lidl/*.png` — PNG photos (OCR'd with Tesseract `bul+eng`)

The project lives **outside** Google Drive (`C:\Users\s.demirov\projects\receipts-analyzer`)
so that `venv/` and `node_modules/` don't sync. Only the receipts folder is on Drive;
its path is configured in [`config.py`](../config.py) and overridable with
`RECEIPTS_DIR` env var (Docker sets this to `/receipts` automatically).

## 1. One-time setup

```bash
cd C:/Users/s.demirov/projects/receipts-analyzer

# Python env (for Kaufland-only builds and host-side testing)
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt

# React app deps
cd web && npm install && cd ..
```

> On this machine `python` may resolve to the Windows Store stub. Use the full
> interpreter path if needed:
> `C:/Users/s.demirov/AppData/Local/Programs/Python/Python312/python.exe -m venv venv`.

### Pointing at a different receipts folder

`config.py` reads `RECEIPTS_DIR` from the `RECEIPTS_DIR` env var, else defaults to
`C:\Users\s.demirov\My Drive\DigitalReceipts`. `docker-compose.yml` overrides this
with `/receipts` (the container mount point). To use a custom path:

```bash
RECEIPTS_DIR="D:/some/other/folder" venv/Scripts/python.exe -m extract.build_db
```

## 2. Build the database

**Full build** (Kaufland PDFs + Lidl PNGs) — Tesseract must be available. The
easiest way is to run inside Docker:

```bash
docker compose run --rm app python -m extract.build_db
```

**Kaufland-only** (no Docker / no tesseract needed):

```bash
venv/Scripts/python.exe -m extract.build_db
```

The command parses every `*.pdf` and `*.png` under `RECEIPTS_DIR`, routes by
extension, and writes `data/receipts.db`. Expected output (current data, 2026-06-19):

```
Parsed 286 receipts.
4018 line items -> 1415 distinct products (mapping: ...product_mapping.csv).
brand/category suggested for ... of 1415 products (edit: ...product_meta.csv).
DB written: ...receipts.db
  receipts: 279  line_items: 4018  products: 1415
  skipped N duplicate (re-downloaded) receipts
  unparsed lines: 11 (see ...unparsed_lines.log)
```

It is **idempotent** and safe to re-run. Re-running:
- de-duplicates re-downloaded receipts by their unique number (UNP);
- preserves your manual edits in both CSV files (see below);
- regenerates `data/receipts.db` from scratch.

## 3. Run the app (React + FastAPI)

Two processes (two terminals):

```bash
# API on :8000
venv/Scripts/python.exe -m uvicorn api.main:app --reload --port 8000

# Web (proxies /api -> :8000); we run it on :5180
cd web && npm run dev -- --port 5180
```

Open <http://localhost:5180>. Note: Vite binds to `localhost` (IPv6); if a tool
can't reach `127.0.0.1`, use `localhost` instead.

## 4. Adding new receipts

1. Drop the new PDF(s) into `DigitalReceipts/Kaufland/` and/or PNG(s) into
   `DigitalReceipts/Lidl/`.
2. Re-run the build (use Docker for Lidl PNGs):
   `docker compose run --rm app python -m extract.build_db`
3. Refresh the browser. The API reads the DB live (no restart needed); a renamed
   `display_name`, brand/category and other edits are preserved.

## 4b. Renaming PDFs to their receipt date

`tools/rename_pdfs.py` renames each PDF to `YYYY-MM-DD.pdf` using the date parsed
from the receipt body. Same-day receipts get `_2`, `_3`… (ordered by purchase
time). It's safe (dry-run by default, idempotent, never clobbers):

```bash
venv/Scripts/python.exe -m tools.rename_pdfs            # preview the mapping
venv/Scripts/python.exe -m tools.rename_pdfs --apply    # rename
```

Renaming does **not** affect extraction (the date comes from the PDF content, not
the filename). Re-run `build_db` afterwards so `source_pdf` reflects the new names.

## 5. Correcting the data

Two editable CSVs in `data/` (UTF-8). After editing, re-run `build_db`.

- **`product_mapping.csv`** — merge/split products. See [product-matching.md](product-matching.md).
- **`product_meta.csv`** — fix brand/category. See [brand-category.md](brand-category.md).

## Verifying things work

```bash
# spot-check a Kaufland PDF end to end (host venv)
venv/Scripts/python.exe -m extract.parse "C:/Users/s.demirov/My Drive/DigitalReceipts/Kaufland/2026-05-31.pdf"
# expect: 9 items, total 23.58, date 2023-11-25, branch 6500, Perrier x4 @ 2.75

# run the test suite (55 tests, no tesseract needed)
./venv/Scripts/python.exe -m pytest -q

# API smoke test (with uvicorn running)
curl -s http://localhost:8000/stats
curl -s "http://localhost:8000/products?brand=Olympus"
```
