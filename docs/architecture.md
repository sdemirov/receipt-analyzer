# Architecture

## Goal

Turn a folder of Bulgarian grocery receipts (Kaufland PDFs + Lidl PNGs) into a
queryable dataset and two UIs that answer:

1. **How did a product's price change over time?**
2. **Where/what/when did I spend?**

## Data flow

```
                    extract/parse.py
 Kaufland/*.pdf  ──────────────────────►┐
                   pdfplumber + regex    │  ParsedReceipt
                    extract/ocr.py      ├──  ├─ metadata (UNP, date, branch, totals, savings)
 Lidl/*.png  ──── Tesseract bul+eng ──►┘    └─ LineItem[] (name, qty, unit_price, vat, measure)
                    extract/parse_lidl.py                    │
                                                             │  raw item names
                    extract/normalize.py                     │
                  fuzzy + size-aware  ◄──────────────────────┘
                  grouping                  product_mapping.csv  (raw_name → product_id)
                                                     │
                    extract/categorize.py            │
                  brand/category guesses  ──────────►  product_meta.csv  (product_id → brand, category)
                                                     │
                    extract/build_db.py              ▼
                  orchestrate + dedupe   ─────►  data/receipts.db  (SQLite)
                                                     │
                                                     ▼
                                            api/main.py (FastAPI)
                                                     │
                                                     ▼
                                       web/ (React + Vite + Recharts)
```

## Components

### Extraction (`extract/`)
- **`parse.py`** — pure parser: one Kaufland PDF → one `ParsedReceipt`. No DB, no
  I/O besides reading the PDF. Easy to unit-test / run standalone.
- **`ocr.py`** — Pillow preprocessing + `pytesseract` (`lang="bul+eng"`) to turn a
  Lidl PNG photo into text. Requires the system `tesseract` binary (installed in the
  Docker image; not needed on the host for tests or Kaufland-only builds).
- **`parse_lidl.py`** — noisy-OCR-tolerant parser for Lidl text → same
  `ParsedReceipt`/`LineItem` model as `parse.py`. Handles the inverted qty-before-name
  layout, `МЕЖДИННА СУМА` region anchors, filename-based UNP fallback, and weighed items.
- **`normalize.py`** — name normalization + the size-aware fuzzy clustering that
  decides which raw names are the same product. Owns `product_mapping.csv`.
- **`categorize.py`** — heuristic brand & category guessing (pure functions).
- **`build_db.py`** — the orchestrator: `rglob`s `*.pdf` and `*.png`, routes by
  extension, dedupe, build/refresh the two CSVs, write SQLite. The only module that
  touches the database.

### Storage
- **`data/receipts.db`** — SQLite, the single source of truth for the apps.
- **`data/product_mapping.csv`**, **`data/product_meta.csv`** — editable inputs
  that survive rebuilds. See [data-model.md](data-model.md).

### Serving
- **`api/main.py`** — FastAPI over SQLite (raw SQL, no ORM). Mostly read-only;
  the one writer is `PUT /products/{id}/name` (rename), which updates
  `product_meta.csv` and re-applies names/search keys to the DB.
  `GET /receipts/{id}/pdf` serves the `receipt_pdfs` blob with its stored
  `media_type` (`application/pdf` or `image/png`).
- **`web/`** — React SPA; talks to the API via a Vite dev proxy (`/api` → `:8000`).

## Key design decisions

- **Rebuild-from-source, not migrations.** The DB is disposable; the receipts + the
  two CSVs are the durable inputs. Any change = re-run `build_db`.
- **Shared model across sources.** Both parsers output `ParsedReceipt`/`LineItem`,
  so normalize, categorize, build_db, and the API are completely source-agnostic.
- **OCR in Docker, not on the host.** Tesseract is only installed in the container
  (`Dockerfile` apt-installs `tesseract-ocr` + `tesseract-ocr-bul`). The host venv
  runs Kaufland extraction and all tests (which use pre-saved OCR text fixtures) fine
  without Tesseract. Run the full build with
  `docker compose run --rm app python -m extract.build_db`.
- **Server: Drive → sync → DB.** Production uses `deploy/refresh.sh` (hourly via
  systemd): Lidl PNG name dedupe on Drive → `rclone sync` → `build_db`. See
  [deployment.md](deployment.md).
- **Editable middle layer.** Item names have no barcode and are truncated, so
  product identity and brand/category are inherently fuzzy. Rather than hide
  that, the pipeline writes its best guess to CSV and lets you correct it; edits
  are preserved on every subsequent run.
- **Fail loud on unknown lines.** Any receipt line the parser can't classify is
  written to `data/unparsed_lines.log` rather than dropped silently. For Lidl PNGs,
  `build_db` also prints `[check]` lines when the parsed item count or line-total
  sum diverges from the receipt's own hints.

## File layout

```
config.py              paths + fuzzy threshold + BGN_PER_EUR
translit.py            BG<->EN search skeleton (project-root module)
extract/
  parse.py             Kaufland PDF -> ParsedReceipt (pdfplumber)
  ocr.py               Lidl PNG -> text (Tesseract bul+eng, Pillow preprocess)
  parse_lidl.py        noisy OCR text -> ParsedReceipt (same model as parse.py)
  normalize.py         product grouping (+ product_mapping.csv)
  categorize.py        brand/category heuristics
  build_db.py          orchestrate -> receipts.db (+ product_meta.csv)
api/main.py            FastAPI
web/                   React + Vite + Recharts
tools/rename_pdfs.py   rename Kaufland PDFs to their receipt date
tools/rename_lidl_pngs.py  dedupe Lidl PNG names on Google Drive (before rclone sync)
tests/                 pytest suite (55 tests, host-runnable, no tesseract needed)
  fixtures/lidl_ocr/   43 pre-saved OCR-text fixtures for Lidl parser tests
data/                  receipts.db, product_mapping.csv, product_meta.csv, unparsed_lines.log
docs/                  this documentation
```
