# Usage

## Prerequisites

- **Python 3.12** (installed at `C:\Users\s.demirov\AppData\Local\Programs\Python\Python312`
  on this machine).
- **Node.js** (for the React app only) — already present via `nvm4w`.
- The receipt PDFs, by default in `C:\Users\s.demirov\My Drive\1Kaufland Receipts`.

The project lives **outside** Google Drive (`C:\Users\s.demirov\projects\kaufland-receipts`)
so that `venv/` and `node_modules/` don't sync. Only the PDF folder is on Drive;
its path is configured in [`config.py`](../config.py).

## 1. One-time setup

```bash
cd C:/Users/s.demirov/projects/kaufland-receipts

# Python env
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt

# React app deps
cd web && npm install && cd ..
```

> On this machine `python` may resolve to the Windows Store stub. Use the full
> interpreter path if needed:
> `C:/Users/s.demirov/AppData/Local/Programs/Python/Python312/python.exe -m venv venv`.

### Pointing at a different PDF folder

`config.py` reads `RECEIPTS_DIR` from the `RECEIPTS_DIR` env var, else
defaults to `C:\Users\s.demirov\My Drive\1Kaufland Receipts`:

```bash
RECEIPTS_DIR="D:/some/other/folder" venv/Scripts/python.exe -m extract.build_db
```

## 2. Build the database

```bash
venv/Scripts/python.exe -m extract.build_db
```

This parses every PDF and writes `data/receipts.db`. Expected output (current data):

```
Parsed 135 receipts.
1750 line items -> 725 distinct products (mapping: ...product_mapping.csv).
brand/category suggested for 605/499 of 725 products (edit: ...product_meta.csv).
DB written: ...receipts.db
  receipts: 128  line_items: 1750  products: 725
  skipped 7 duplicate (re-downloaded) receipts
  unparsed lines: 0 (see ...unparsed_lines.log)
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

1. Drop the new PDF(s) into the receipts folder.
2. Re-run `venv/Scripts/python.exe -m extract.build_db`.
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
# spot-check one receipt end to end
venv/Scripts/python.exe -m extract.parse "C:/Users/s.demirov/My Drive/1Kaufland Receipts/20260531_101201.pdf"
# expect: 9 items, total 23.58, date 2023-11-25, branch 6500, Perrier x4 @ 2.75

# API smoke test (with uvicorn running)
curl -s http://localhost:8000/stats
curl -s "http://localhost:8000/products?brand=Olympus"
```
