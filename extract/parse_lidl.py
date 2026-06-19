"""Parse a Lidl receipt PNG (via OCR) into the shared ParsedReceipt model.

Lidl layout differs from Kaufland: the quantity line ("2,00 x 0,97") PRECEDES
the item's name+total line, totals are "МЕЖДИННА СУМА"/"ОБЩА СУМА", currency is
EUR ("Евро" header). OCR is noisy (0<->д<->8, Б often read as В), so patterns are
tolerant and amounts accept both ',' and '.' decimals.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from extract.parse import (LineItem, ParsedReceipt, _sanitize_name,
                           _sanitize_text)

UNP_RE = re.compile(r"УНП[:\s]+([A-Za-zА-Яа-я0-9-]+)")
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b")
COUNT_RE = re.compile(r"(\d+)\s+АРТИКУЛ")
SUBTOTAL_RE = re.compile(r"МЕЖДИННА\s+СУМА\s+(\d+[.,]\d{2})")
TOTAL_RE = re.compile(r"ОБЩА\s+СУМА\s+(\d+[.,]\d{2})")
STORE_RE = re.compile(r"Лидл[^\n]*")

# item-region boundaries
ITEM_START_RE = re.compile(r"Евро")                       # currency header line
ITEM_END_RE = re.compile(r"^(МЕЖДИННА|ОБЩА)\s+СУМА")
# a qty line:  "2,00 x 0,97"  (x / х / *)
QTY_RE = re.compile(r"^(?P<qty>\d+)[.,]\d{2,3}\s*[xх*]\s*(?P<unit>\d+[.,]\d{2})$")
# an item line: "<name> <amount> <VAT-letter>"
ITEM_RE = re.compile(r"^(?P<name>.+?)\s+(?P<amt>\d+[.,]\d{2})\s+(?P<vat>[А-Я])$")
PAY_CARD_RE = re.compile(r"КАРТ", re.I)
PAY_CASH_RE = re.compile(r"В\s*БРОЙ", re.I)
VAT_FIX = {"В": "Б"}  # common OCR confusion: В read where Б was printed


def _money(s: str) -> float:
    return float(s.replace(",", "."))


def parse_lidl_text(text: str, source: str) -> ParsedReceipt:
    text = _sanitize_text(text)
    lines = [ln.strip() for ln in text.splitlines()]
    r = ParsedReceipt(source_pdf=source, raw_text=text,
                      currency="EUR", store_name="Лидл")

    if m := UNP_RE.search(text):
        r.unp = m.group(1)
    if m := DATE_RE.search(text):
        dd, mm, yy = m.groups()
        if 1 <= int(dd) <= 31 and 1 <= int(mm) <= 12:
            r.purchase_date = f"{yy}-{mm}-{dd}"
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

    # locate item region
    start = next((i for i, ln in enumerate(lines) if ITEM_START_RE.search(ln)), None)
    if start is None:
        return r
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if ITEM_END_RE.match(lines[i]):
            end = i
            break

    pending: Optional[tuple[int, float]] = None
    for line in lines[start + 1:end]:
        if not line:
            continue
        if m := QTY_RE.match(line):
            pending = (int(m.group("qty")), _money(m.group("unit")))
            continue
        if m := ITEM_RE.match(line):
            amt = _money(m.group("amt"))
            vat = VAT_FIX.get(m.group("vat"), m.group("vat"))
            name = _sanitize_name(m.group("name"))
            if pending:
                qty, unit = pending
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
