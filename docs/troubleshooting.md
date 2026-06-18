# Troubleshooting

## `python` opens the Microsoft Store / "Python was not found"
The `python` alias is the Windows Store stub. Use the real interpreter or the
venv directly:
```bash
C:/Users/s.demirov/AppData/Local/Programs/Python/Python312/python.exe --version
venv/Scripts/python.exe -m extract.build_db
```

## Cyrillic prints as `???` or raises `UnicodeEncodeError`
Windows consoles default to cp1252. Every entry point calls
`sys.stdout.reconfigure(encoding="utf-8")`; if you write your own script, do the
same at the top, or set `PYTHONUTF8=1`.

## App shows stale data after re-running `build_db`
The FastAPI app reads the DB per request, so just refresh the browser — no
restart needed.

## Can't reach the web app at `127.0.0.1:5173`
Vite binds to `localhost` (IPv6 `::1`). Use `http://localhost:5173`. If `:5173`
is taken, Vite picks the next port — check its console output.

## API returns empty / connection refused
- Ensure uvicorn is on `:8000` (the Vite proxy targets `127.0.0.1:8000`).
- Test directly: `curl http://localhost:8000/stats`.

## `unparsed_lines.log` is non-empty after adding receipts
A new receipt has a layout the parser doesn't recognise (e.g. a different weight
unit or a new promo line). Open `data/unparsed_lines.log`, find the offending
lines, and extend the patterns in `extract/parse.py`
(`QTY_RE` / `WEIGHT_RE` / `SINGLE_RE`, or the skip rules). See
[extraction.md](extraction.md).

## Two sizes of the same product are merged into one
The size-aware guard should prevent this, but odd spellings can slip through.
Split them in `data/product_mapping.csv` (give one a new `product_id`) and re-run
`build_db`. See [product-matching.md](product-matching.md).

## Product / brand counts changed unexpectedly after a rebuild
You likely deleted `product_mapping.csv` or `product_meta.csv`, which regenerates
ids from scratch. Don't delete them once you've edited them — edit in place so
ids stay stable.

## A product has the wrong brand/category
Edit `data/product_meta.csv` (`brand` / `category` columns, keyed by
`product_id`) and re-run `build_db`. See [brand-category.md](brand-category.md).

## Totals don't match my mental math
- Printed item prices are **net** of card/promo discounts and sum to `Сума`.
- Weighed items store **price per kg** as `unit_price`; `line_total` is the
  actual amount, so spend sums use `line_total`, not `unit_price`.
- `card_savings` (loyalty) and `promo_savings` (price promos) are separate.

## Rebuild from absolute scratch
```bash
rm -f data/receipts.db data/product_mapping.csv data/product_meta.csv data/unparsed_lines.log
venv/Scripts/python.exe -m extract.build_db
```
> This re-clusters and re-guesses everything (new `product_id`s). Only do it if
> you have **no** manual CSV edits to keep.
