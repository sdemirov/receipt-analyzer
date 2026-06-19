"""Parse a Lidl receipt PNG (via bul+eng OCR) into the shared ParsedReceipt model.

Lidl layout differs from Kaufland: the quantity line ("2,000 x 0,97") PRECEDES
the item's name+total line, totals are "МЕЖДИННА СУМА"/"ОБЩА СУМА", currency is
EUR. Real OCR is noisy, so this module is deliberately tolerant:

  * UNP is normalized (`@`->`0`, Cyrillic `ВМ`->Latin `BN`) and, when the `УНП:`
    line is missing (it is dropped on ~38/43 receipts), falls back to the source
    filename so the receipt is never lost by build_db's dedup.
  * The item region is anchored on the cashier header line (always contains
    "Касиер"/"Kacuep") and ends at "МЕЖДИННА СУМА" / "ОБЩА СУМА".
  * Prices accept ',' or '.', one optional space after the separator, trailing
    extra digits, and leading OCR confusions (д/й/@ -> 0).
  * VAT letters are normalized to canonical Cyrillic classes (В/B -> Б, etc).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from extract.parse import (LineItem, ParsedReceipt, _sanitize_name,
                           _sanitize_text)

# --- money helper ------------------------------------------------------------
# A price/total: 1-4 digits, separator, ONE optional space, 2 digits, then any
# extra digits (e.g. "2,990" -> 2.99). Leading digit may be an OCR'd д/й/@ = 0.
_MONEY = r"[\dдй@]\d{0,3}[.,]\s?\d{2}\d*"


def _money(s: str) -> float:
    """Parse a noisy OCR amount string into a float."""
    s = (s.replace(" ", "")
          .replace("д", "0").replace("й", "0").replace("@", "0")
          .replace(",", "."))
    # collapse "2.990" style (3+ fractional digits) back to 2 decimals
    if "." in s:
        whole, frac = s.split(".", 1)
        s = f"{whole}.{frac[:2]}"
    return float(s)


# --- metadata patterns -------------------------------------------------------
UNP_RE = re.compile(r"УНП[:\s]+([A-Za-zА-Яа-я0-9@-]+)")
DATE_RE = re.compile(
    r"\b(\d{2})\.(\d{2})\.(20\d{2})(?:\s+(\d{2})\s*:\s*(\d{2})\s*:\s*(\d{2}))?")
# footer line: "#05/04/26 18:14:35#" (2-digit year, has the time). OCR sprinkles
# stray spaces around the slashes/colons ("01 /04/23 12:46 :59"), so tolerate them.
DATE_FOOTER_RE = re.compile(
    r"(\d{2})\s*/\s*(\d{2})\s*/\s*(\d{2})\s+(\d{2})\s*:\s*(\d{2})\s*:\s*(\d{2})")
COUNT_RE = re.compile(r"(\d+)\s+АРТИКУЛ")
SUBTOTAL_RE = re.compile(r"МЕЖДИННА\s+СУМА\s+(" + _MONEY + r")")
TOTAL_RE = re.compile(r"ОБЩА\s+СУМА\s+(" + _MONEY + r")")
STORE_RE = re.compile(r"Лидл[^\n]*")
PAY_CARD_RE = re.compile(r"КАРТ", re.I)
PAY_CASH_RE = re.compile(r"В\s*БРОЙ", re.I)

# --- item-region patterns ----------------------------------------------------
# Cashier header line, robust to OCR: "Касиер:9" / "Kacuep :84" (mixed scripts).
CASHIER_RE = re.compile(r"[КK][аa][сc][иu][еe][рp]")
# Old currency-header fallback (only used if no cashier line is found).
CURRENCY_HDR_RE = re.compile(r"Евро|EBpo|BGN|EUR|Всм")
ITEM_END_RE = re.compile(r"^(МЕЖДИННА|ОБЩА)\s+СУМА")

# qty/multipack line: "2,000 x 0,97", "д,306 x 31,89", "@,223 x 31,89".
# x may be Latin x, Cyrillic х, or *.
QTY_RE = re.compile(
    r"^(?P<qty>[\dдй@]{1,5}[.,]\s?\d{2,5})\s*[xх*]\s*(?P<unit>" + _MONEY + r")\s*$")
# item line: name, optional embedded product code (5-7 digits, maybe quoted),
# price, optional trailing VAT letter.
ITEM_RE = re.compile(
    r"^(?P<name>.+?)\s+(?:[\"']?\d{5,7}\s+)?(?P<amt>" + _MONEY + r")"
    r"(?:\s+(?P<vat>[А-ЯA-Zа-я]))?\s*$")
# trailing product-code run to strip from a name
CODE_TAIL_RE = re.compile(r"[\"']?\d{5,7}\s*$")
# lines inside the region that are NOT items
DECOR_RE = re.compile(r"^#")                       # "# Евро #", "#1191 ..."
PROMO_RE = re.compile(r"промоци|ОТСТЪПК|Plus|купон", re.I)

# VAT normalization: map OCR/letter variants to canonical Cyrillic classes.
# Lidl's dominant class is Б (20%); anything unrecognised defaults to it.
VAT_MAP = {
    "Б": "Б", "А": "А", "Г": "Г",
    "В": "Б",            # OCR confuses printed Б as Cyrillic В
    "B": "Б", "A": "А",  # Latin look-alikes
}


def _norm_vat(letter: Optional[str]) -> str:
    if not letter:
        return "Б"
    return VAT_MAP.get(letter.upper(), "Б")


def _norm_unp(raw: str) -> str:
    v = raw.replace("@", "0")
    # leading Cyrillic ВМ / Вм / ВN (OCR of Latin BN) -> BN
    v = re.sub(r"^[ВвB][МмNn]", "BN", v)
    return v


def _fix_month(mm: str) -> Optional[str]:
    """Return a valid 2-digit month or None. OCR often misreads the leading 0 of a
    single-digit month (01-09) as 8/9/6 on thermal print ('09'->'89'). When the
    month is otherwise impossible, assume the leading digit was a misread zero."""
    if 1 <= int(mm) <= 12:
        return mm
    if mm[1] in "123456789":     # "89"->"09", "85"->"05"
        return "0" + mm[1]
    return None


def parse_lidl_text(text: str, source: str) -> ParsedReceipt:
    text = _sanitize_text(text)
    lines = [ln.strip() for ln in text.splitlines()]
    r = ParsedReceipt(source_pdf=source, raw_text=text, store_name="Лидл")

    # --- UNP (never None) ---
    if m := UNP_RE.search(text):
        r.unp = _norm_unp(m.group(1))
    else:
        r.unp = source  # filename fallback: PNGs are unique photos

    # --- date/time: prefer the footer "#DD/MM/YY HH:MM:SS#" (present on nearly
    #     all receipts and the only place with the time); fall back to the
    #     dot-format "DD.MM.20YY" summary line for the date. ---
    if m := DATE_FOOTER_RE.search(text):
        dd, mm, yy, hh, mi, ss = m.groups()
        mm = _fix_month(mm)
        if mm and 1 <= int(dd) <= 31:
            r.purchase_date = f"20{yy}-{mm}-{dd}"
            r.purchase_time = f"{hh}:{mi}:{ss}"
    if r.purchase_date is None and (m := DATE_RE.search(text)):
        dd, mm, yy, hh, mi, ss = m.groups()
        mm = _fix_month(mm)
        if mm and 1 <= int(dd) <= 31:
            r.purchase_date = f"{yy}-{mm}-{dd}"
            if hh is not None:
                r.purchase_time = f"{hh}:{mi}:{ss}"

    # --- currency: Bulgaria adopted the euro 2026-01-01. Pre-2026 Lidl receipts
    #     print amounts in BGN (with a EUR equivalent in parens); from 2026 they
    #     print EUR. The OCR'd "# BGN #/# Евро #" header is unreliable, so key off
    #     the date. build_db converts BGN amounts to EUR at BGN_PER_EUR. Unknown
    #     date (no parse) defaults to EUR (only recent receipts lack a date). ---
    r.currency = "EUR" if (r.purchase_date is None
                           or r.purchase_date >= "2026-01-01") else "BGN"

    if m := COUNT_RE.search(text):
        r.item_count_hint = int(m.group(1))
    if m := STORE_RE.search(text):
        r.store_name = _sanitize_name(m.group(0))
        if b := re.search(r"(\d{2,4})\s*$", r.store_name):
            r.branch_id = b.group(1)
    if m := SUBTOTAL_RE.search(text):
        r.subtotal = _money(m.group(1))
    if m := TOTAL_RE.search(text):
        r.total = _money(m.group(1))
    if r.subtotal is None:
        r.subtotal = r.total
    if PAY_CARD_RE.search(text):
        r.payment_method = "Карта"
    elif PAY_CASH_RE.search(text):
        r.payment_method = "В брой"

    # --- locate item region ---
    start = next((i for i, ln in enumerate(lines) if CASHIER_RE.search(ln)), None)
    if start is None:
        # fall back to old currency-header anchor so nothing regresses
        start = next((i for i, ln in enumerate(lines)
                      if CURRENCY_HDR_RE.search(ln)), None)
    if start is None:
        return r
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if ITEM_END_RE.match(lines[i]):
            end = i
            break

    pending: Optional[tuple[float, float]] = None
    for line in lines[start + 1:end]:
        if not line:
            continue                       # blank: keep pending (qty -> blank -> item)
        if DECOR_RE.match(line):
            continue                       # currency header / "#..." decoration
        if PROMO_RE.search(line):
            pending = None                 # promo/discount: not an item, drop pairing
            continue
        if m := QTY_RE.match(line):
            pending = (_money(m.group("qty")), _money(m.group("unit")))
            continue
        if m := ITEM_RE.match(line):
            amt = _money(m.group("amt"))
            vat = _norm_vat(m.group("vat"))
            name = CODE_TAIL_RE.sub("", m.group("name"))
            name = _sanitize_name(name).strip(' "\'')
            if pending:
                qty, unit = pending
                # printed amount is the line total; keep parsed qty/unit
                r.items.append(LineItem(name, qty, unit, amt, vat))
            else:
                r.items.append(LineItem(name, 1, amt, amt, vat))
            pending = None
            continue
        pending = None
        r.unparsed.append(line)
    return r


def parse_lidl(path: str | Path) -> ParsedReceipt:
    from extract.ocr import ocr_image  # lazy: only needs tesseract at call time
    return parse_lidl_text(ocr_image(path), Path(path).name)
