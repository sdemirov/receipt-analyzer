"""Parse a Kaufland digital receipt PDF into structured data.

The receipts are digital text (no OCR needed). Two line-item layouts exist:

    Торбичка Кауфланд            0,39 Б      single line: name, unit price, VAT class
    Закуска с клен.сироп                     quantity item: name on its own line ...
     2 * 1,29                2,58 Б          ... then  qty * unit_price  line_total  VAT

Everything between the "Цена BGN" header and the totals block (Междинна сума /
Сума / Промоция) is treated as the item region. Lines that match neither layout
are reported via ``ParsedReceipt.unparsed`` so nothing is silently dropped.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber


def _is_odd(ch: str) -> bool:
    """True for lone surrogates and control/format/private/unassigned chars."""
    return (0xD800 <= ord(ch) <= 0xDFFF) or unicodedata.category(ch)[0] == "C"


def _sanitize_text(s: str) -> str:
    """Strip invalid glyphs from the receipt text but keep its layout."""
    return "".join(ch for ch in s if ch in "\n\t" or not _is_odd(ch))


def _sanitize_name(s: str) -> str:
    """Clean a product name: drop odd glyphs, collapse whitespace."""
    s = "".join(ch for ch in s if not _is_odd(ch))
    return re.sub(r"\s+", " ", s).strip()


# --- line patterns -----------------------------------------------------------
# VAT classes seen on receipts: А (0%), Б (20%), Г (9%). Allow any Cyrillic
# uppercase letter to be future-proof.
# Order matters: qty and weight patterns must be tried before the single
# pattern, because e.g. "2 * 1,29 2,58 Б" / "0,230 KG 11,50 Б" also satisfy it.
QTY_RE = re.compile(r"^(?P<qty>\d+)\s*[*xX]\s*(?P<unit>\d+,\d{2})\s+(?P<total>\d+,\d{2})\s+(?P<vat>[А-Я])$")
WEIGHT_RE = re.compile(r"^(?P<weight>\d+,\d{2,3})\s*[Kk][Gg]\s+(?P<total>\d+,\d{2})\s+(?P<vat>[А-Я])$")
SINGLE_RE = re.compile(r"^(?P<name>.+?)\s+(?P<price>\d+,\d{2})\s+(?P<vat>[А-Я])$")

UNP_RE = re.compile(r"УНП\s+(\S+)")
BRANCH_RE = re.compile(r"Филиал:\s*(\d+)")
DATE_RE = re.compile(r"Дата:\s*(\d{2})\.(\d{2})\.(\d{2})\s+Час:\s*(\d{2}:\d{2}:\d{2})")
POINTS_RE = re.compile(r"You earned\s+(\d+)\s+points")
SAVED_RE = re.compile(r"You saved\s+(\d+,\d{2})\s+(?:BGN|EUR)")
MONEY_TAIL_RE = re.compile(r"(\d+,\d{2})\s*$")

# Item region starts at the price header, whose currency switched from BGN to
# EUR on 2026-01-01 ("Цена BGN" / "Цена EUR").
CURRENCY_HDR_RE = re.compile(r"^Цена\s+(BGN|EUR)\b")
TOTAL_MARKERS = ("Междинна сума", "Сума", "Промоция")
PAYMENT_METHODS = ("В брой", "Кредитна карта", "Дебитна карта")


def _money(s: str) -> float:
    return float(s.replace(",", "."))


@dataclass
class LineItem:
    raw_name: str
    qty: float          # piece count, or weight in kg for weighed items
    unit_price: float   # price per piece, or price per kg for weighed items
    line_total: float
    vat_class: str      # "А" (0%), "Б" (20%) or "Г" (9%)
    unit_measure: str = "pc"  # "pc" or "kg"
    on_promo: bool = False     # bought on a price promotion ("Вие спестявате")
    promo_saving: float = 0.0  # amount saved on this line vs the regular price


@dataclass
class ParsedReceipt:
    source_pdf: str
    unp: Optional[str] = None
    purchase_date: Optional[str] = None  # ISO YYYY-MM-DD
    purchase_time: Optional[str] = None
    branch_id: Optional[str] = None
    store_name: Optional[str] = None
    subtotal: Optional[float] = None
    total: Optional[float] = None
    card_savings: float = 0.0      # loyalty-card savings ("You saved X ...")
    promo_savings: float = 0.0     # item-level price-promo savings ("Вие спестявате")
    currency: str = "BGN"          # receipt currency ("BGN" pre-2026, else "EUR")
    payment_method: Optional[str] = None
    points: Optional[int] = None
    raw_text: str = ""           # full extracted receipt text
    items: List[LineItem] = field(default_factory=list)
    unparsed: List[str] = field(default_factory=list)


def _extract_text(pdf_path: Path) -> str:
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_receipt(pdf_path: Path) -> ParsedReceipt:
    text = _sanitize_text(_extract_text(pdf_path))
    lines = [ln.strip() for ln in text.splitlines()]
    receipt = ParsedReceipt(source_pdf=Path(pdf_path).name, raw_text=text)

    # --- metadata (search whole text) ---
    if m := UNP_RE.search(text):
        receipt.unp = m.group(1)
    if m := BRANCH_RE.search(text):
        receipt.branch_id = m.group(1)
    if m := DATE_RE.search(text):
        dd, mm, yy, hhmmss = m.groups()
        receipt.purchase_date = f"20{yy}-{mm}-{dd}"
        receipt.purchase_time = hhmmss
    if m := POINTS_RE.search(text):
        receipt.points = int(m.group(1))
    if m := SAVED_RE.search(text):
        receipt.card_savings = _money(m.group(1))
    for ln in lines:
        if ln.startswith("Хипермаркет"):
            receipt.store_name = ln
            break

    # --- locate item region (and detect currency from the price header) ---
    start = None
    for i, ln in enumerate(lines):
        if m := CURRENCY_HDR_RE.match(ln):
            start, receipt.currency = i, m.group(1)
            break
    if start is None:
        # No price header (rare) — infer currency from the date as a fallback.
        if receipt.purchase_date and receipt.purchase_date >= "2026-01-01":
            receipt.currency = "EUR"
        return receipt
    end = len(lines)
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if any(ln.startswith(mk) for mk in TOTAL_MARKERS) or "Промоция" in ln or ln.startswith("Позиции"):
            end = i
            break
    region = lines[start + 1 : end]

    # --- parse items ---
    i = 0
    while i < len(region):
        line = region[i]
        if not line:
            i += 1
            continue

        # Item-level price-promo annotation, printed right after the discounted
        # item. The item's price is already net, so flag the preceding line item
        # as on-promo and record the saving (also rolled into the receipt total).
        if line.startswith("Вие спестявате"):
            amt = _money(m.group(1)) if (m := re.search(r"(\d+,\d{2})\s*(?:BGN|EUR)", line)) else 0.0
            receipt.promo_savings += amt
            if receipt.items:
                receipt.items[-1].on_promo = True
                receipt.items[-1].promo_saving += amt
            i += 1
            continue

        if m := QTY_RE.match(line):
            name = _sanitize_name(region[i - 1]) if i > 0 else "?"
            receipt.items.append(
                LineItem(
                    raw_name=name,
                    qty=int(m.group("qty")),
                    unit_price=_money(m.group("unit")),
                    line_total=_money(m.group("total")),
                    vat_class=m.group("vat"),
                )
            )
            i += 1
            continue

        if m := WEIGHT_RE.match(line):
            name = _sanitize_name(region[i - 1]) if i > 0 else "?"
            weight = _money(m.group("weight"))
            total = _money(m.group("total"))
            receipt.items.append(
                LineItem(
                    raw_name=name,
                    qty=weight,
                    unit_price=round(total / weight, 2) if weight else total,
                    line_total=total,
                    vat_class=m.group("vat"),
                    unit_measure="kg",
                )
            )
            i += 1
            continue

        if m := SINGLE_RE.match(line):
            price = _money(m.group("price"))
            receipt.items.append(
                LineItem(
                    raw_name=_sanitize_name(m.group("name")),
                    qty=1,
                    unit_price=price,
                    line_total=price,
                    vat_class=m.group("vat"),
                )
            )
            i += 1
            continue

        # Neither pattern. If the next line is a qty/weight line, this is its
        # name -> skip (it gets consumed on the next iteration).
        nxt = region[i + 1] if i + 1 < len(region) else ""
        if QTY_RE.match(nxt) or WEIGHT_RE.match(nxt):
            i += 1
            continue
        receipt.unparsed.append(line)
        i += 1

    # --- totals & payment (scan lines after the item region) ---
    for ln in lines[end:]:
        if ln.startswith("Междинна сума") and (m := MONEY_TAIL_RE.search(ln)):
            receipt.subtotal = _money(m.group(1))
        elif ln.startswith("Сума") and (m := MONEY_TAIL_RE.search(ln)):
            receipt.total = _money(m.group(1))
        if receipt.payment_method is None:
            for pm in PAYMENT_METHODS:
                if ln.startswith(pm):
                    receipt.payment_method = pm
                    break
    if receipt.subtotal is None:
        receipt.subtotal = receipt.total

    return receipt


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    r = parse_receipt(Path(sys.argv[1]))
    print(f"PDF: {r.source_pdf}")
    print(f"UNP: {r.unp}  date: {r.purchase_date} {r.purchase_time}  branch: {r.branch_id}")
    print(f"store: {r.store_name}")
    print(f"subtotal: {r.subtotal}  total: {r.total}  saved: {r.card_savings}  pay: {r.payment_method}  pts: {r.points}")
    print(f"items ({len(r.items)}):")
    for it in r.items:
        print(f"  {it.raw_name!r:40} qty={it.qty} unit={it.unit_price} total={it.line_total} vat={it.vat_class}")
    if r.unparsed:
        print(f"UNPARSED ({len(r.unparsed)}): {r.unparsed}")
