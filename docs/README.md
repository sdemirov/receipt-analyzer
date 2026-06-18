# Documentation

Detailed docs for the **Digital Receipts Analyzer** project — extracting products and
prices from Bulgarian digital receipt PDFs and exploring price history
and spending.

## Index

| Doc | What's inside |
|-----|---------------|
| [usage.md](usage.md) | Install, run extraction, run the two apps, add new receipts |
| [architecture.md](architecture.md) | High-level design, data flow, components, file layout |
| [extraction.md](extraction.md) | Receipt PDF format, the parser, every line type & edge case |
| [data-model.md](data-model.md) | SQLite schema + the two editable CSV files |
| [product-matching.md](product-matching.md) | Fuzzy + size-aware grouping; how to fix groupings |
| [brand-category.md](brand-category.md) | Auto brand/category heuristics; how to correct them |
| [api.md](api.md) | FastAPI endpoint reference |
| [frontend.md](frontend.md) | React (Vite + Recharts) SPA |
| [troubleshooting.md](troubleshooting.md) | Common issues and fixes |

## 30-second overview

```
store receipt PDFs  ──pdfplumber──►  parsed line items + metadata
        │                                         │
        │                          rapidfuzz (size-aware) grouping
        │                          + brand/category heuristics
        ▼                                         ▼
   data/receipts.db  ◄────────────────────  build_db.py
        │
        └──►  FastAPI (api/main.py)  ──►  React SPA (web/)
```

The PDFs are **digital text** (no OCR). Everything downstream is rebuilt from
them by a single idempotent command: `python -m extract.build_db`.

Two editable files let you correct the inevitable fuzziness:
- `data/product_mapping.csv` — which raw names form one product.
- `data/product_meta.csv` — each product's brand and category.

Start with [usage.md](usage.md).
