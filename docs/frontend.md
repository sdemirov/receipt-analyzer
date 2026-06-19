# Front-end

A single React SPA (`web/`) talks to the FastAPI backend and reads everything
from `data/receipts.db`.

## React + Vite + Recharts (`web/`)

### Run
```bash
# API (terminal 1)
venv/Scripts/python.exe -m uvicorn api.main:app --reload --port 8000
# Web (terminal 2)
cd web && npm run dev
```
Vite serves on `:5173` by default (we've been running it on `:5180`) and proxies
`/api/*` → `http://127.0.0.1:8000` (config in [`web/vite.config.js`](../web/vite.config.js)).
Open the URL Vite prints — use `localhost` (Vite binds IPv6).

### Structure
```
web/
  index.html
  vite.config.js          dev server + /api proxy
  src/
    main.jsx              React root
    api.js                fetch wrapper (get + put; all endpoints)
    App.jsx               header KPIs + tab switch
    components/
      PriceExplorer.jsx   price-over-time tab
      SpendDashboard.jsx  spending tab
      RenameEditor.jsx    rename products tab
      ReceiptsList.jsx    receipts list tab (all receipts, filterable by store)
      ReceiptModal.jsx    receipt detail modal (items / text / PDF iframe or image)
    styles.css
```

### Цени във времето tab (`PriceExplorer.jsx`)
- Left panel: search box + **Категория** / **Марка** dropdowns (from `/facets`) +
  a scrollable product list (date count, price range, unit, category). Search is
  **bilingual BG↔EN** (`/products` matches on a Latin phonetic skeleton), so `кола`
  finds `Coca Cola` and `nesquik` finds `Nesquik`. The idle list shows products
  with ≥2 dates; any search/filter reveals all (incl. single-purchase items).
- Selecting products fetches `/products/{id}/prices` for each and merges them by
  date into one Recharts `LineChart` (one line per product, `connectNulls`).
- Filters: date range (`От`/`До`) and store (`Магазин`) re-query the series.
- **Weighed items** (`unit_measure="kg"`) are plotted by **amount paid**
  (`line_total`) rather than per-unit price; the tooltip shows `qty кг @ €/кг`.
  Piece items plot the per-unit price as before.
- **Promo points** are drawn with a gold „%" ringed marker; the tooltip shows the
  saving and the implied regular price (`makeDot` + `PriceTooltip`).
- **Store in tooltip** — each point shows the store name (🏬) from `store_name` in
  the `/products/{id}/prices` response, so Kaufland vs Lidl purchases are visually
  distinguishable.
- **Clickable points** — clicking a point opens `ReceiptModal` for that purchase,
  with tabs **Продукти** (line items), **Извлечен текст** (raw text), and **PDF**
  (Kaufland: `<iframe>`; Lidl: `<img>` — tab label changes to **Снимка**). Both come
  from the DB (`/receipts/{id}` and `/receipts/{id}/pdf`).

### Бележки tab (`ReceiptsList.jsx`)
All receipts in a sortable paginated table (date, store, item count, total, payment,
savings). A **free-text store filter** (`Филтър по магазин…`) lets you type e.g.
"Лидл" to see only Lidl receipts. Clicking a row opens `ReceiptModal`.

### Разходи tab (`SpendDashboard.jsx`)
Charts from `/analytics/spend`: spend by month (line), by store (bar), by VAT
(pie), by category (bar), and top-15 products (bar).

### Receipt modal (`ReceiptModal.jsx`)
Three tabs: **Продукти** (line items — kg items show `qty кг` in the quantity column),
**Извлечен текст** (raw OCR or PDF text), and **PDF / Снимка** (the tab label adapts
to the source type). For Kaufland PDFs the blob is shown in an `<iframe>`.
For Lidl PNGs an `<img>` is shown with zoom controls: −/+ buttons (100–500% in 50%
steps) and click-to-cycle (zoom in to 3× then reset). The modal is draggable so you
can keep it open while navigating the chart.

### ✏️ Преименуване tab (`RenameEditor.jsx`)
Rename products so shortened names read the way you want (e.g. expand
`КМ`→`кисело мляко`). A bilingual search box (`/products/meta`) lists matches with
the current name and an editable "Ново име" field. Saving calls
`PUT /products/{id}/name`, which writes `display_name` to `product_meta.csv` and
runs `build_db.apply_meta_to_db()` (updates `products.canonical_name` +
`search_key` with no PDF re-parse). The new name then shows everywhere and is
searchable (the original short form stays searchable too); it survives rebuilds.
Clear the field and save to revert to the auto name.

### Build
```bash
cd web && npm run build      # outputs web/dist/
npm run preview              # serve the built bundle
```
(The bundle-size warning is benign for a local single-page app.)

### Adding an endpoint to the UI
1. Add a method in `src/api.js` (`get`/`put` helpers).
2. Call it from a component with `useEffect`/`useState`.
The proxy means you always use relative `/api/...` URLs.
