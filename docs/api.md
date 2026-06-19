# API reference

Module: [`api/main.py`](../api/main.py). FastAPI over a **read-only** SQLite
connection (raw SQL, no ORM). CORS is open (local/personal use).

Run:
```bash
venv/Scripts/python.exe -m uvicorn api.main:app --reload --port 8000
```

Interactive docs (FastAPI built-in): <http://localhost:8000/docs>.

All money values are **EUR**; dates are ISO `YYYY-MM-DD`.

---

### `GET /stats`
Overview KPIs.
```json
{ "receipts":279, "products":1415, "line_items":4018,
  "first_date":"2021-06-19", "last_date":"2026-06-17",
  "total_spend":..., "card_savings":..., "promo_savings":... }
```

### `GET /branches`
Stores with receipt counts.
```json
[ { "branch_id":"6500", "store_name":"Хипермаркет София-Манастирски л", "receipts":114 } ]
```

### `GET /facets`
Distinct brands and categories (for filter dropdowns).
```json
{ "brands":[ {"name":"Olympus","products":7}, ... ],
  "categories":[ {"name":"Мляко и млечни","products":39}, ... ] }
```

### `GET /products`
Products with price range and purchase counts.

Query params:
| param | default | meaning |
|-------|---------|---------|
| `search` | `""` | **bilingual** substring match — query and names are reduced to a Latin phonetic skeleton (`translit.search_key`), so `кола`↔`cola`, `несквик`↔`Nesquik` both match |
| `min_dates` | `1` | only products bought on ≥ N distinct dates |
| `brand` | – | exact brand filter |
| `category` | – | exact category filter |

```json
[ { "id":5, "canonical_name":"Olympus Био ПМ 3,7%", "brand":"Olympus",
    "category":"Мляко и млечни", "purchases":18, "dates":18,
    "min_price":4.19, "max_price":5.29, "unit_measure":"pc" } ]
```

### `GET /products/{id}/prices`
Time series for the price chart.

Query params: `date_from`, `date_to` (ISO), `branch` (branch_id).
```json
{ "product": { "id":1, "canonical_name":"Торбичка" },
  "points": [ { "date":"2023-05-25", "unit_price":0.39, "line_total":0.39,
                "qty":1, "unit_measure":"pc", "raw_name":"Торбичка",
                "on_promo":0, "promo_saving":0.0, "regular_price":0.39,
                "receipt_id":3, "branch":"6900", "store_name":"Хипермаркет София-Ма…" } ] }
```
`on_promo`/`promo_saving` come from the receipt's `Вие спестявате` annotation;
`regular_price = unit_price + promo_saving/qty` (the implied pre-promo unit
price, correct for both piece and weighed items). `store_name` is used by the
price-chart tooltip (🏬 store per point).

### `GET /analytics/spend`
Aggregated spend. Query param `by`:

| `by` | buckets |
|------|---------|
| `month` | `YYYY-MM` (spend + receipt count) |
| `store` | branch (spend + receipts + store_name) |
| `vat` | VAT class (spend + item count) |
| `category` | product category, `(няма)` for blank |
| `brand` | product brand, `(няма)` for blank |
| `product` | top 30 products by spend |

```json
[ { "bucket":"2024-01", "spend":712.34, "receipts":6 }, ... ]
```

### `GET /receipts/{id}`
Full detail for one receipt — used by the click-to-open modal.
```json
{ "receipt": { "id":3, "store_name":"...", "purchase_date":"2023-10-27",
               "total":63.61, "payment_method":"...", ... },
  "items": [ { "raw_name":"...", "qty":1, "unit_price":1.09, "line_total":1.09,
               "vat_class":"Б", "unit_measure":"pc", "on_promo":0 } ],
  "text": "<full extracted receipt text>" }
```

### `GET /receipts/{id}/pdf`
Streams the original receipt media from the DB blob with `Content-Disposition: inline`,
using the **stored `media_type`** (`application/pdf` for Kaufland or `image/png` for
Lidl). The React modal renders PDFs in an `<iframe>` and Lidl images in an `<img>`
tag ("Снимка" tab) with zoom controls (−/+ 100–500%, click to cycle).

### `GET /receipts`
All receipts with metadata and item counts, newest first.
```json
[ { "id":1, "purchase_date":"2025-04-21", "branch_id":"6500",
    "store_name":"...", "total":42.13, "card_savings":0.0,
    "promo_savings":0.0, "payment_method":"Кредитна карта",
    "points":8, "n_items":14 } ]
```

---

## Notes
- The DB is opened per-request (`sqlite3.Row`), so the API always reflects the
  latest `build_db` run with no restart.
- Errors: `404` for an unknown product id; `400` for an invalid `by` value.
- The React dev server proxies `/api/*` here (see [frontend.md](frontend.md)).
