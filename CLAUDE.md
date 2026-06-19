# CLAUDE.md — Digital Receipts Analyzer

Guidance for future Claude sessions working on this project.

## What this is
Extracts products & prices from Bulgarian grocery-store receipts into SQLite, and
serves a **React + FastAPI** web app: price-over-time charts, spending analytics,
click-a-point → receipt modal (items / extracted text / in-app PDF or image),
bilingual search, and a product-rename editor.

Two receipt sources:
- **Kaufland** — **digital receipt PDFs** (text, no OCR), parsed by `extract/parse.py`.
- **Lidl** — **PNG photos** (`*.png` in the same `RECEIPTS_DIR`), OCR'd with Tesseract
  (`bul+eng`) **inside the Docker container** and parsed by `extract/parse_lidl.py`.
  See the "Lidl PNG receipts" section below.

There is **no Streamlit app** — it was removed on 2026-06-18. The single front-end
is `web/` (React). Don't re-introduce Streamlit/Plotly/Altair/pandas unless asked.

## Where things live (important)
- **Code is on `C:`**: `C:\Users\s.demirov\projects\receipts-analyzer` (kept off
  Google Drive so `venv/` and `node_modules/` don't sync). Always run commands from
  here.
- **The receipt PDFs are on Google Drive**: `C:\Users\s.demirov\My Drive\1Kaufland Receipts`
  (`RECEIPTS_DIR` in `config.py`; was `G:\My Drive\…` — moved 2026-06-18). It's still
a Google-Drive virtual folder, so it can **transiently unmount** (you may see
  "folder deleted" / 0 PDFs) — a mount glitch, NOT data loss. Only `build_db.main()`
  and `tools/rename_pdfs.py` read the PDFs; everything else (API, rename, search,
  receipt preview) uses files in the project `data/` on `C:` and works regardless.
- Git repo **does** exist here (GitHub `origin` = sdemirov/receipt-analyzer; default
  branch `main`). The Lidl-PNG work was done on `feature/lidl-png-extraction`.

## Layout
```
config.py            RECEIPTS_DIR, DB_PATH, the data/ CSV paths, FUZZY_THRESHOLD
translit.py          BG<->EN search skeleton (PROJECT-ROOT module: `from translit import search_key`)
extract/
  parse.py           PDF -> ParsedReceipt (metadata + LineItems); sanitises text/names
  normalize.py       size-aware fuzzy grouping -> product_mapping.csv
  categorize.py      brand/category heuristics
  build_db.py        orchestrate -> data/receipts.db; also apply_meta_to_db(), set_display_name()
api/main.py          FastAPI (raw SQL; one writer: PUT /products/{id}/name)
web/                 React + Vite + Recharts SPA (the only UI)
tools/rename_pdfs.py rename PDFs to YYYY-MM-DD[_n].pdf
data/                receipts.db (gen), product_mapping.csv, product_meta.csv, unparsed_lines.log
docs/                detailed docs (start at docs/README.md)
```

## Run it
Python is at `C:\Users\s.demirov\AppData\Local\Programs\Python\Python312\` (the bare
`python` on PATH is the Windows Store stub — don't use it). Always use the venv:
```bash
# from project root
./venv/Scripts/python.exe -m uvicorn api.main:app --port 8000      # API
cd web && (PATH=/c/nvm4w/nodejs:$PATH npm run dev -- --port 5180)   # web (Node via nvm4w)
```
App: http://localhost:5180  (Vite proxies `/api/*` -> `127.0.0.1:8000`; Vite binds
`localhost`/IPv6, so use `localhost`, not `127.0.0.1`). Rebuild data after adding
PDFs or editing CSVs: `./venv/Scripts/python.exe -m extract.build_db`.

## Data model (SQLite, rebuilt from source — disposable)
- `receipts` (one per unique receipt, dedup by `unp`): metadata + totals +
  `card_savings`/`promo_savings` + `raw_text` + `source_pdf`.
- `products`: `canonical_name` (the EFFECTIVE display name), `brand`, `category`,
  `search_key` (Latin phonetic skeleton for search).
- `line_items`: name, qty, unit_price (per-kg for weighed), line_total, vat,
  `unit_measure` (pc/kg), `on_promo`, `promo_saving`.
- `receipt_pdfs(receipt_id, pdf BLOB)`: original PDF bytes (self-contained;
  PDF chosen over image — smallest faithful format).

## Editable inputs (durable; preserved across rebuilds — DON'T delete or ids renumber)
- `data/product_mapping.csv` — `raw_name -> canonical_name, product_id`. Edit to
  merge/split products.
- `data/product_meta.csv` — `product_id, canonical_name(auto, read-only ref),
  display_name(rename override), brand, category`. Effective name = display_name or
  auto canonical; folded into search_key (the original short form stays searchable).

## Key mechanisms
- **Bilingual search** (`translit.search_key`): query + names reduced to a Latin
  skeleton (c→k, qu→kv, x→ks, w→v, y→i), so `кола`↔`cola`, `несквик`↔`Nesquik`.
  API matches `WHERE products.search_key LIKE ?`.
- **Rename**: `PUT /products/{id}/name {display_name}` → `set_display_name()` writes
  the CSV → `apply_meta_to_db()` updates `products.canonical_name`+`search_key`
  (fast, no PDF re-parse). React: "✏️ Преименуване" tab.
- **Receipt preview**: React renders the stored PDF blob on a canvas via **PDF.js**
  (`web/src/components/PdfView.jsx`) — never downloads. A plain iframe/inline
  `Content-Disposition` will DOWNLOAD in headless/plugin-less browsers; keep PDF.js.
- **Character sanitisation** (`parse._sanitize_*`): drops surrogates/control chars
  from names and text; no-op on clean data.
- **Currency (EUR)**: Bulgaria adopted the euro 2026-01-01. Receipts print
  `Цена BGN` (pre-2026) or `Цена EUR` — the parser detects this (`CURRENCY_HDR_RE`,
  sets `receipt.currency`) and that header is ALSO the item-region start, so not
  handling the EUR variant means 0 items parsed for those receipts. `build_db`
  stores **all amounts in EUR**, converting BGN receipts at `config.BGN_PER_EUR`
  (1.9558). UI shows `€` only. `SAVED_RE` + promo regex accept BGN|EUR.
- **Promo**: from `Вие спестявате` receipt lines → per-line `on_promo`; gold "%"
  markers on the chart.

## Lidl PNG receipts (added 2026-06-19)
- **Source**: `*.png` photos in the same `RECEIPTS_DIR` as the Kaufland PDFs;
  `build_db.parse_all()` routes by extension (`.pdf`→`parse_receipt`, `.png`→`parse_lidl`).
- **OCR runs in Docker**: `Dockerfile` installs `tesseract-ocr` + `tesseract-ocr-bul`;
  `extract/ocr.py` (`Pillow` preprocess + `pytesseract`, **`lang="bul+eng"`** — receipts
  mix Cyrillic and Latin brand names like `SCHWEPPES`/`NESPRESSO`, so bul-only mangles
  them). `docker-compose.yml` mounts the receipts folder read-only at `/receipts` and
  sets `RECEIPTS_DIR=/receipts`. **Run the build in the container**:
  `docker compose run --rm app python -m extract.build_db`.
- **Parser** (`extract/parse_lidl.py`) returns the SAME `ParsedReceipt`/`LineItem`
  as the PDF path. Lidl layout vs Kaufland: qty line (`2,00 x 0,97`) **precedes** the
  item; item region is between the `Касиер` header line and `МЕЖДИННА СУМА`; totals are
  `МЕЖДИННА/ОБЩА СУМА`; currency is EUR. OCR is noisy, so the parser is tolerant
  (space-in-price `3, 06`, trailing digits, optional product code + VAT letter,
  `В→Б` VAT fixups) and **falls back to the filename as the UNP** when OCR drops the
  `УНП:` line (else dedup would drop the receipt — 38/43 lack a clean УНП line).
- **Preview**: PNG bytes are stored in `receipt_pdfs` with a `media_type` column;
  the API serves them with that type and the React modal shows an `<img>` ("Снимка"
  tab) instead of the PDF `<iframe>`.
- **Quality**: OCR is imperfect; `build_db` prints `[check]` lines (parsed item count
  vs the `N АРТИКУЛА` hint; line-total sum vs total — **PNG-only**) and unmatched item
  lines go to `data/unparsed_lines.log`. Tests: `tests/test_parse_lidl*.py` run on the
  host against 43 real OCR-text fixtures in `tests/fixtures/lidl_ocr/` (no tesseract
  needed). Design/plan: `docs/superpowers/specs|plans/2026-06-19-lidl-png-*`.

## Gotchas / conventions
- Use **git bash** (Bash tool) for shell work per the user's global CLAUDE.md;
  PowerShell only for Windows-native needs (e.g. `Get-NetTCPConnection` to free a
  port, killing a stuck process).
- **Windows UTF-8**: scripts that print Cyrillic must `sys.stdout.reconfigure(
  encoding="utf-8")` or you get a cp1252 `UnicodeEncodeError`. Don't send Cyrillic
  JSON via `curl --data` from bash (it mangles to `?`) — use Python `urllib`/file,
  or just rely on the React `fetch` (proper UTF-8).
- **Background servers**: launch a server as the foreground command of a
  `run_in_background` Bash call (no trailing `&` + echo — that makes the harness
  reap it). Free a port with PowerShell `Get-NetTCPConnection -LocalPort N` →
  `Stop-Process` before restarting. The API reads the DB per request, so data
  changes need no API restart (just refresh the browser); CODE changes need a
  restart.
- The current dataset (2026-06-19): 243 Kaufland PDFs + 43 Lidl PNGs → **279
  receipts, 4018 line_items, 1415 products**, 11 unparsed (spans 2021-06-19 →
  2026-06-17). Counts grow as receipts are added. (EUR receipts were 0-items until
  the `Цена EUR` fix; the 43 Lidl PNGs add ~896 line_items.)

## Verifying changes
- Pipeline: `./venv/Scripts/python.exe -m extract.build_db` (expect counts above,
  0 unparsed) and spot-check a receipt with `python -m extract.parse <pdf>`.
- API: `curl http://localhost:8000/stats`, `/products?search=...`, etc.
- UI: drive the React app at :5180 (Playwright). Note: vega/canvas and glide-grid
  widgets are hard to click in automation; verify the underlying API/data when the
  UI can't be driven.

See `docs/` for full detail (architecture, extraction, data-model,
product-matching, brand-category, api, frontend, troubleshooting).
