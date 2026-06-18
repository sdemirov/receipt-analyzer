# Digital Receipts Analyzer

Extract products and prices from digital receipt PDFs (Bulgarian) and
explore how prices changed over time, plus spending analytics.

> 📚 **Detailed documentation lives in [`docs/`](docs/README.md)** — architecture,
> the parser, data model, product matching, brand/category, API and front-ends.

The receipts are **digital text** (no OCR). A Python pipeline parses every PDF
into SQLite; a **React + FastAPI** app reads the database — a polished SPA with a
JSON API (price-over-time charts, spending analytics, receipt preview, renaming).

```
config.py            paths (RECEIPTS_DIR -> the PDF folder, DB_PATH, ...)
translit.py          BG<->EN bilingual search skeleton
extract/
  parse.py           pdfplumber receipt parser (handles qty, weighed kg, promos)
  normalize.py       rapidfuzz product-name grouping + editable mapping CSV
  categorize.py      brand/category heuristics
  build_db.py        parse all PDFs -> data/receipts.db (idempotent)
api/main.py          FastAPI backend
web/                 React + Vite + Recharts SPA
tools/rename_pdfs.py rename PDFs to their receipt date
data/
  receipts.db        SQLite (generated)
  product_mapping.csv  raw_name -> canonical product (EDIT to fix groupings)
  product_meta.csv     product_id -> brand, category (EDIT to fix labels)
  unparsed_lines.log   any receipt line the parser didn't recognise
docs/                detailed documentation
```

## 1. Setup

Python (3.12) and Node (for the React app) are required.

```bash
# from the project root
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# (macOS/Linux: source venv/bin/activate && pip install -r requirements.txt)

cd web && npm install && cd ..
```

The PDF folder is set in `config.py` (`RECEIPTS_DIR`, default
`C:\Users\s.demirov\My Drive\1Kaufland Receipts`). Override with the `RECEIPTS_DIR`
environment variable.

## 2. Extract the data

```bash
venv/Scripts/python.exe -m extract.build_db
```

Rebuilds `data/receipts.db` from every PDF. Re-run any time you add new
receipts — it is idempotent and de-duplicates re-downloaded receipts by their
unique number (UNP).

**Fixing product groupings.** Items have no barcode and names are truncated, so
the same product can appear under slightly different names. `build_db` auto-groups
them (rapidfuzz) into `data/product_mapping.csv`:

```
raw_name,canonical_name,product_id
Кроасан нуга,Кроасан нуга 90г,2
Кроасан нуга 90г,Кроасан нуга 90г,2
```

To merge/split products, edit the `canonical_name` / `product_id` columns and
re-run `build_db`. Your edits are preserved on subsequent runs; only newly-seen
raw names are added.

## 3. Run the app (React + FastAPI)

Two processes:

```bash
# terminal 1 — API on :8000
venv/Scripts/python.exe -m uvicorn api.main:app --reload --port 8000

# terminal 2 — web on :5180 (proxies /api -> :8000)
cd web && npm run dev -- --port 5180
```

Open http://localhost:5180. Tabs: **Цени във времето** (price-over-time +
click a point for the receipt/PDF), **Разходи** (spending), **✏️ Преименуване**
(rename products).

## Run with Docker

A single image builds the React SPA and serves it together with the API
(`server.py` mounts the API under `/api`, the SPA at `/`). It bakes in the
prebuilt `data/` (receipts.db with PDF blobs + the CSVs) — the receipt-PDF
source folder is **not** needed at runtime.

### Docker Compose (recommended)

`docker-compose.yml` already bind-mounts `./data` (so renames/basket edits
persist) and adds a healthcheck:

```bash
docker compose up -d --build      # builds + starts on http://localhost:8090
docker compose ps                 # shows "healthy"
docker compose logs -f            # follow logs
docker compose down               # stop & remove
```

### Plain Docker

```bash
docker build -t digital-receipts-analyzer .
docker run -d --name dra -p 8090:8000 \
  -v "C:/Users/s.demirov/projects/kaufland-receipts/data:/app/data" \
  digital-receipts-analyzer
# open http://localhost:8090
```

To re-extract inside the container (after adding PDFs), also mount the PDF folder
and run the builder:

```bash
docker run --rm -v "C:/path/to/receipts:/pdfs" -v "$(pwd)/data:/app/data" \
  -e RECEIPTS_DIR=/pdfs digital-receipts-analyzer \
  python -m extract.build_db
```

### API endpoints
- `GET /stats` — totals overview
- `GET /branches` / `GET /facets` — stores / brands & categories
- `GET /products?search=&min_dates=&brand=&category=` — products (bilingual search)
- `GET /products/{id}/prices?date_from=&date_to=&branch=` — price points over time
- `GET /products/meta?search=` + `PUT /products/{id}/name` — list/rename products
- `GET /analytics/spend?by=month|store|vat|category|brand|product` — aggregated spend
- `GET /receipts`, `GET /receipts/{id}`, `GET /receipts/{id}/pdf` — receipts + PDF

## Notes on the data
- Prices use a decimal comma; dates come from the `Дата:` line inside each PDF
  (the filename is only the download time).
- VAT classes: `А` 0% (bread), `Б` 20%, `Г` 9%.
- Weighed items (`кг`) store **price per kg** as the unit price; piece items
  store price per piece (`unit_measure` column distinguishes them).
- Printed item prices are already net of card/promo discounts; total card and
  promo savings are kept per receipt.
