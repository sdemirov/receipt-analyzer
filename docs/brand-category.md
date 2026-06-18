# Brand & category

Module: [`extract/categorize.py`](../extract/categorize.py).

Receipts print **neither** a brand nor a category, so both are *heuristic
guesses* written to `data/product_meta.csv` as a starting point — you correct
them, and your edits survive rebuilds.

## How brand is guessed (`guess_brand`)

1. **Known-brand match** — the name is lowercased and checked for any substring
   in the `BRANDS` list (Olympus, Devin, Coca Cola, Активиа, Балкан, KLC, K-Bio,
   Маджаров, Саяна, Zewa, Pampers, …). First match wins.
2. **First-token fallback** — if no known brand matches, the first token is used
   **only if** it's capitalised and not a generic noun (the `_GENERIC` blacklist:
   хляб, мляко, сирене, вода, банани, био, кн, …). This catches brands not in the
   list while avoiding category words.
3. Otherwise brand is empty (`""`).

Coverage on the current data: **605 / 725** products get a brand guess.

## How category is guessed (`guess_category`)

Ordered keyword rules in `CATEGORY_RULES`; the **first matching rule wins** (more
specific categories are listed first). Categories:

```
Яйца · Сирене и кашкавал · Мляко и млечни · Месо и колбаси · Хляб и тестени ·
Плодове и зеленчуци · Вода · Напитки · Кафе и чай · Захарни и снакс ·
Основни храни · Бебешко · Хигиена и козметика · Дом и бит
```

Each rule matches Bulgarian keyword substrings, e.g.:
- `Месо и колбаси` ← пиле, свинск, телешк, кайма, луканка, шунка, салам, …
- `Плодове и зеленчуци` ← банан, ябълк, домат, краставиц, лук, морков, …
- `Дом и бит` ← торбичка, салфетк, хартия, препарат, батери, …

Coverage: **499 / 725** products get a category; the rest are empty for you to
fill (shown as `(няма)` in spend charts).

## Editing `product_meta.csv`

```
product_id,canonical_name,brand,category
5,Olympus Био ПМ 3,7%,Olympus,Мляко и млечни
18,Olympus ПМ 3,7% 1л,Olympus,Мляко и млечни
20,Olympus ПМ 3,7% 1,5л,Olympus,Мляко и млечни
```

- The join key is **`product_id`**; `canonical_name` is just for readability.
- Edit `brand` and/or `category` freely. Blank is valid.
- You can introduce **new categories** simply by typing them — they'll appear as
  filters automatically.
- Re-run `build_db` to apply. Existing `product_id`s keep your values; only new
  products get fresh guesses.

```bash
venv/Scripts/python.exe -m extract.build_db
```

## Where they show up

- **App** — "Категория" and "Марка" dropdowns above the product search (filter
  the product list); a "Разходи по категория" chart on the Spending tab.
- **API** — `GET /facets` (lists brands & categories with counts),
  `GET /products?brand=…&category=…`, `GET /analytics/spend?by=category|brand`.

## Improving the heuristics

Edit `extract/categorize.py`:
- Add brands to `BRANDS` (lowercase substrings).
- Add/extend rules in `CATEGORY_RULES` (remember: order = priority).
- Add false-positive brand words to `_GENERIC`.

Then regenerate. Note: because existing `product_meta.csv` rows are preserved,
improvements to the heuristics only affect **new** products. To re-guess
everything, delete `product_meta.csv` first (safe only if you haven't hand-edited
it) and re-run `build_db`.

### Quick distribution check
```bash
venv/Scripts/python.exe -c "
import sqlite3; from config import DB_PATH
c=sqlite3.connect(DB_PATH)
for cat,n in c.execute(\"SELECT COALESCE(NULLIF(category,''),'(няма)'),COUNT(*) FROM products GROUP BY category ORDER BY 2 DESC\"):
    print(f'{n:4}  {cat}')
"
```
