# Extraction

Module: [`extract/parse.py`](../extract/parse.py). Input: one **Kaufland** receipt PDF.
Output: a `ParsedReceipt` dataclass. No OCR — the PDFs are digital text read with
**pdfplumber** (`page.extract_text()`); Cyrillic comes through as UTF-8.

> **Lidl PNG receipts** take a different front end but the SAME `ParsedReceipt`
> output: [`extract/ocr.py`](../extract/ocr.py) OCRs the photo with Tesseract
> (`lang="bul+eng"`, run inside the Docker container) and
> [`extract/parse_lidl.py`](../extract/parse_lidl.py) parses the (noisy) text.
> Key layout differences from Kaufland:
>
> - **qty line precedes the item name** (opposite of Kaufland): `2,000 x 0,97` comes
>   before the product name + line total.
> - **Item region** runs from the `Касиер` header line to `МЕЖДИННА СУМА` / `ОБЩА СУМА`.
> - **Currency keys off the date** (the OCR'd header is unreliable): pre-2026 receipts
>   are BGN (converted to EUR by `build_db` at `BGN_PER_EUR` = 1.9558); 2026+ are EUR.
> - **UNP falls back to the filename** when the `УНП:` line is OCR-dropped (38 of 43
>   receipts); without this, dedup would discard the receipt.
> - **Weighed items**: qty is recomputed from `line_total / unit_price` when the OCR'd
>   figure is inconsistent; a fractional result → `unit_measure="kg"`, `unit_price` is
>   the price per kg.
> - The parser tolerates space-in-price (`3, 06`), trailing extra digits, optional
>   embedded product codes, and `В→Б` OCR VAT confusion.
> - `build_db` prints `[check]` lines (item count vs `N АРТИКУЛА` hint; line-total sum
>   vs total) for PNGs and logs unmatched lines to `data/unparsed_lines.log`.
>
> See the design + plan under `docs/superpowers/`.

## Anatomy of a receipt

```
You saved 0,66 BGN with Loyalty Card          ← loyalty savings (header)
You earned 4 points for this purchase.         ← points
Receipt Copy
 Хипермаркет София-Манастирски л       ← store name (Хипермаркет ...)
 УНП                 BN018464-0166-000968       ← unique receipt number (dedupe key)
 Цена BGN                                        ← start of item region
 Торбичка            0,39 Б            ← single-line item
 Закуска с клен.сироп                            ← qty item (name line) ...
  2 * 1,29                2,58 Б                 ← ... qty * unit_price  line_total  VAT
 Perrier вода 0,33л
  4 * 2,75               11,00 Б
 Маджаров Луканка                                ← weighed item (name line) ...
  0,230 KG 11,50 Б                               ← ... weight KG  line_total  VAT
 Мляно от св. плешка 3,23 Б
 Вие спестявате 40% или 2,16 BGN!               ← item-level promo annotation
 Междинна сума           24,24                   ← end of item region
 ----------------Промоция---------------
 Loyalty Card           -0,66
 Сума                    23,58                   ← total paid
 В брой BGN              24,00                    ← payment method
 ...
 Дата: 25.11.23 Час: 12:14:16 Бон:15458         ← purchase date/time (DD.MM.YY)
 Филиал: 6500 Каса: 7 Касиер: 166               ← branch id
```

## What gets extracted

### Metadata (regex over the whole text)
| Field | Source | Notes |
|-------|--------|-------|
| `unp` | `УНП  <code>` | Unique per receipt; the **dedupe key**. |
| `purchase_date` | `Дата: DD.MM.YY` | Converted to ISO `20YY-MM-DD`. **From the PDF**, not the filename. |
| `purchase_time` | `Час: HH:MM:SS` | |
| `branch_id` | `Филиал: <n>` | Store code (e.g. 6500). |
| `store_name` | line starting `Хипермаркет` | Full store name. |
| `subtotal` / `total` | `Междинна сума` / `Сума` | `subtotal` falls back to `total` when there's no discount block. |
| `card_savings` | `You saved X BGN` | Loyalty-card savings. |
| `promo_savings` | sum of `Вие спестявате … BGN` | Item-level price promotions. |
| `payment_method` | `В брой` / `Кредитна карта` / `Дебитна карта` | |
| `points` | `You earned N points` | |

### Items
The **item region** is the lines between `Цена BGN` and the first of
`Междинна сума` / `Сума` / `Промоция` / `Позиции`.

Each `LineItem` has: `raw_name`, `qty`, `unit_price`, `line_total`, `vat_class`,
`unit_measure` (`pc` or `kg`).

## The three line layouts

Patterns are tried in this order (order matters — earlier patterns are more
specific):

1. **Quantity multipack** (`QTY_RE`): a name line followed by
   `qty * unit_price  line_total  VAT`.
   ```
   Закуска с клен.сироп
    2 * 1,29                2,58 Б     → qty=2, unit_price=1.29, line_total=2.58
   ```
   `unit_price` (1.29) is what we chart, not the line total.

2. **Weighed** (`WEIGHT_RE`): a name line followed by `weight KG  line_total  VAT`.
   ```
   Маджаров Луканка
    0,230 KG 11,50 Б                   → qty=0.230 (kg), line_total=11.50
   ```
   For weighed items `unit_price = line_total / weight` = **price per kg**, and
   `unit_measure = "kg"`. (Verified: the numbers after `KG` are line totals —
   they sum exactly to the receipt's VAT subtotal.)

3. **Single line** (`SINGLE_RE`): `name  unit_price  VAT` (qty = 1).
   ```
   Торбичка            0,39 Б  → qty=1, unit_price=0.39
   ```

> Why order matters: `2 * 1,29 2,58 Б` and `0,230 KG 11,50 Б` both *also* match
> the single-line pattern (`<text> <number> <letter>`), so the qty and weight
> patterns must be checked first.

## Edge cases handled

- **Character sanitization** — the extracted text and every product name are run
  through `_sanitize_text` / `_sanitize_name`, which drop lone surrogates and
  control/format/private/unassigned characters (a misdecoded PDF glyph can't leak
  into a name or the API JSON). Text keeps its newline layout; names also collapse
  whitespace. It's a no-op on clean data.
- **Decimal comma** — `1,29` parsed via `float(s.replace(",", "."))`.
- **VAT classes** — `А` (0%, bread), `Б` (20%), `Г` (9%). The pattern accepts any
  single Cyrillic uppercase letter to be future-proof; rates map in `build_db.py`.
- **Item-level promos** — `Вие спестявате 40% или 2,16 BGN!` lines are attributed
  to the **preceding** line item (`on_promo=True`, `promo_saving=amount`) and also
  summed into the receipt's `promo_savings`. The printed price is already net, so
  the implied regular price is `unit_price + promo_saving/qty`. (Currently 3 such
  promo line items in the dataset.)
- **Name precursor lines** — a bare product-name line (precursor to a qty/weight
  line) is not logged as unparsed; it's consumed when its qty/weight line is read.
- **Duplicate downloads** — same `unp` appearing in multiple PDFs is de-duplicated
  in `build_db` (see below).

## Nothing is dropped silently

Any item-region line that matches none of the three patterns (and isn't a name
precursor) is appended to `ParsedReceipt.unparsed` and written to
`data/unparsed_lines.log` with its source filename. On the current dataset there are
**11 unparsed lines** (across 286 source files — mostly OCR noise from Lidl PNGs). If
you add receipts with a new layout (e.g. a different weight unit or a new Lidl
layout), check this log first.

## Run the parser standalone

```bash
# Kaufland PDF
venv/Scripts/python.exe -m extract.parse "C:/Users/s.demirov/My Drive/DigitalReceipts/Kaufland/2026-05-30.pdf"

# Lidl PNG (needs tesseract → run in the container; parse_lidl has no CLI, use -c)
docker compose run --rm app python -c "from extract.parse_lidl import parse_lidl; r=parse_lidl('/receipts/Lidl/Файл_000 (1).png'); print(r.unp, r.purchase_date, r.total, len(r.items))"
```

Prints metadata + every parsed line item — handy when debugging a new receipt
format.

## De-duplication (in `build_db.py`)

`build_db` keeps the first occurrence of each `unp` and skips the rest **before**
inserting items, so a re-download never doubles a basket. Critically, the product
mapping is also built only from the kept receipts, keeping product counts consistent.
For Lidl PNGs where the `УНП:` line was OCR-dropped, the filename is used as the
dedup key (each PNG is a unique photo, so there are no true duplicates there).
