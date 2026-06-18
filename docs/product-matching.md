# Product matching

Module: [`extract/normalize.py`](../extract/normalize.py).

## The problem

Line items carry **no barcode/SKU**, and the store truncates names to ~18 chars.
The same product appears under slightly different spellings across receipts:

```
Кроасан нуга
Кроасан нуга 90г
Кроасан с кайс.90г   ← different product (apricot), must NOT merge
```

So "the same product over time" has to be reconstructed from the text.

## The approach

1. **Normalize** each raw name into a comparison key (`normalize_name`):
   lowercase, split glued digits (`Добруджа250г` → `добруджа 250 г`), strip
   punctuation, collapse whitespace.
2. **Greedily cluster** names whose normalized forms have a rapidfuzz
   `token_set_ratio` ≥ `FUZZY_THRESHOLD` (88, in `config.py`). The most frequent
   raw spelling becomes the cluster's `canonical_name`.
3. **Size guard** (below) prevents merging different package sizes.
4. Persist `raw_name → (canonical_name, product_id)` to `product_mapping.csv`.

## Size-aware guard

Plain `token_set_ratio` over-merges sizes: `Olympus ПМ 3,7% 1л` vs
`Olympus ПМ 3,7% 1,5л` score ~90 because almost every token overlaps — the lone
`1` vs `1,5` isn't enough to fall below 88.

The fix: extract a **size signature** (`size_signature`) — the set of
volume/weight/percent/count tokens, with units canonicalised so spelling
variants match:

| Raw | Size signature |
|-----|----------------|
| `Olympus ПМ 3,7% 1л` | `{3.7%, 1л}` |
| `Olympus ПМ 3,7% 1,5л` | `{3.7%, 1.5л}` |
| `400г` / `400гр` | `{400г}` (units normalised: `гр`→`г`, `l`→`л`, `kg`→`кг`, …) |
| `Кроасан нуга` | `{}` (no size) |

Rule: **two names cannot be clustered if both have non-empty size signatures and
they differ.** If one side has no size (a truncation), merging is still allowed.

Effect on the current data:
- `Olympus ПМ 3,7% 1л` and `…1,5л` → **separate** products.
- `Кроасан нуга` ↔ `Кроасан нуга 90г` → **still merged** (one has no size).
- Groups mixing different sizes dropped from **27 → 0**; product count 699 → 725.

Each cluster locks onto the first non-empty size it sees; a name with a
*different* non-empty size starts its own cluster.

## Fixing groupings by hand

`data/product_mapping.csv` is the editable source of truth. After any edit,
re-run `build_db`.

### Split a wrongly-merged product
Give the offending `raw_name` a new, unused `product_id` (and a fitting
`canonical_name`):
```
# before
Кроасан нуга 80г,Кроасан нуга 90г,4
# after — move 80g to its own product
Кроасан нуга 80г,Кроасан нуга 80г,900
```

### Merge two products that should be one
Point both `raw_name`s at the same `product_id` and `canonical_name`:
```
Балкан Био КМ 3,6%,Балкан Био КМ 3,6%,10
Балкан БиоКМ 3,6%,Балкан Био КМ 3,6%,10
```

> Use a high, clearly-unused number (e.g. 900+) for new split products to avoid
> colliding with auto-assigned ids.

Then:
```bash
venv/Scripts/python.exe -m extract.build_db
```
Your rows are preserved; only genuinely new raw names get auto-clustered.

## Tuning the threshold

`FUZZY_THRESHOLD` in `config.py` (default 88):
- **Higher** (e.g. 92) → fewer merges, more duplicate products, fewer false merges.
- **Lower** (e.g. 82) → more merges, risk of merging distinct products.

Changing it only affects raw names not already in `product_mapping.csv`. To
re-cluster everything from scratch, delete the CSV first (this renumbers
`product_id`s — only do it before you've made manual edits).

## Auditing merges

List product groups that still mix different sizes (should be 0):

```bash
venv/Scripts/python.exe -c "
import csv; from collections import defaultdict
from config import MAPPING_CSV
from extract.normalize import size_signature
g=defaultdict(list)
for r in csv.DictReader(open(MAPPING_CSV, encoding='utf-8')): g[r['product_id']].append(r['raw_name'])
for pid,n in g.items():
    s={x for x in {size_signature(x) for x in n} if x}
    if len(s)>1: print(pid, n)
"
```
