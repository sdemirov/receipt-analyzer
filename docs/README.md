# Documentation

Detailed docs for the **Digital Receipts Analyzer** project — extracting products and
prices from Bulgarian grocery receipts (Kaufland PDF + Lidl PNG) and exploring price
history and spending.

## Index

| Doc | What's inside |
|-----|---------------|
| [usage.md](usage.md) | Install, run extraction, run the two apps, add new receipts |
| [deployment.md](deployment.md) | Server install, rclone sync, hourly refresh, Lidl rename on Drive |
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
 Kaufland/*.pdf  ──pdfplumber──►┐
                                 ├─ ParsedReceipt (same model)
 Lidl/*.png  ──Tesseract OCR──►─┘      │
                                        │  rapidfuzz (size-aware) grouping
                                        │  + brand/category heuristics
                                        ▼
                            data/receipts.db  ◄── build_db.py
                                        │
                                        └──►  FastAPI (api/main.py)  ──►  React SPA (web/)
```

Two receipt sources: **Kaufland** digital PDFs (text, pdfplumber, no OCR) and
**Lidl** PNG photos (OCR'd with Tesseract `bul+eng` inside Docker). Both flow
through the same `ParsedReceipt`/`LineItem` model. Everything downstream is
rebuilt by a single idempotent command:
`docker compose run --rm app python -m extract.build_db`
(or `venv/Scripts/python.exe -m extract.build_db` on the host for Kaufland-only).

Two editable files let you correct the inevitable fuzziness:
- `data/product_mapping.csv` — which raw names form one product.
- `data/product_meta.csv` — each product's brand and category.

Start with [usage.md](usage.md).
