# Architecture

## Goal

Turn a folder of digital receipt PDFs (Bulgarian) into a queryable
dataset and two UIs that answer:

1. **How did a product's price change over time?**
2. **Where/what/when did I spend?**

## Data flow

```
                    extract/parse.py
 receipt.pdf  ─────────────────────────►  ParsedReceipt
                  pdfplumber + regex        ├─ metadata (UNP, date, branch, totals, savings)
                                            └─ LineItem[] (name, qty, unit_price, vat, measure)
                                                     │
                    extract/normalize.py             │  raw item names
                  fuzzy + size-aware  ◄──────────────┘
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
- **`parse.py`** — pure parser: one PDF → one `ParsedReceipt`. No DB, no I/O
  besides reading the PDF. Easy to unit-test / run standalone.
- **`normalize.py`** — name normalization + the size-aware fuzzy clustering that
  decides which raw names are the same product. Owns `product_mapping.csv`.
- **`categorize.py`** — heuristic brand & category guessing (pure functions).
- **`build_db.py`** — the orchestrator: parse all PDFs, dedupe, build/refresh
  the two CSVs, write SQLite. The only module that touches the database.

### Storage
- **`data/receipts.db`** — SQLite, the single source of truth for the apps.
- **`data/product_mapping.csv`**, **`data/product_meta.csv`** — editable inputs
  that survive rebuilds. See [data-model.md](data-model.md).

### Serving
- **`api/main.py`** — FastAPI over SQLite (raw SQL, no ORM). Mostly read-only;
  the one writer is `PUT /products/{id}/name` (rename), which updates
  `product_meta.csv` and re-applies names/search keys to the DB.
- **`web/`** — React SPA; talks to the API via a Vite dev proxy (`/api` → `:8000`).

## Key design decisions

- **Rebuild-from-source, not migrations.** The DB is disposable; the PDFs + the
  two CSVs are the durable inputs. Any change = re-run `build_db`.
- **Editable middle layer.** Item names have no barcode and are truncated, so
  product identity and brand/category are inherently fuzzy. Rather than hide
  that, the pipeline writes its best guess to CSV and lets you correct it; edits
  are preserved on every subsequent run.
- **Fail loud on unknown lines.** Any receipt line the parser can't classify is
  written to `data/unparsed_lines.log` rather than dropped silently.

## File layout

```
config.py              paths + fuzzy threshold
extract/
  parse.py             PDF -> ParsedReceipt
  normalize.py         product grouping (+ product_mapping.csv)
  categorize.py        brand/category heuristics
  build_db.py          orchestrate -> receipts.db (+ product_meta.csv)
  translit.py          BG<->EN search skeleton (note: project-root module)
api/main.py            FastAPI
web/                   React + Vite + Recharts
tools/rename_pdfs.py   rename PDFs to their receipt date
data/                  receipts.db, product_mapping.csv, product_meta.csv, unparsed_lines.log
docs/                  this documentation
```
