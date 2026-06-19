"""Real bul+eng OCR robustness tests for the Lidl parser.

These run against the 43 committed OCR fixtures in tests/fixtures/lidl_ocr/.
They assert the *robust invariants* (region found, items parsed, unp never None,
sane per-item fields) plus an aggregate sum-vs-total quality floor and two
exact-value locks on clean receipts.
"""
from pathlib import Path

import pytest

from extract.parse_lidl import parse_lidl_text

FIX_DIR = Path(__file__).parent / "fixtures" / "lidl_ocr"


def _load(name: str):
    """Parse a fixture by bare name (with or without .txt)."""
    if not name.endswith(".txt"):
        name += ".txt"
    path = FIX_DIR / name
    return parse_lidl_text(path.read_text(encoding="utf-8"), name.replace(".txt", ".png"))


def _all_fixtures():
    return sorted(p.name for p in FIX_DIR.glob("file_*.txt"))


def test_spaced_footer_date_and_time():
    """OCR sprinkles spaces in the footer timestamp ('#01 /04/23 12:46 :59#').
    The parser must still recover date + time."""
    r = _load("file_000_31")
    assert r.purchase_date == "2023-04-01"
    assert r.purchase_time == "12:46:59"


def test_ocr_misread_month_recovered():
    """OCR read the '0' of month 09 as 8 ('#22 /89/23 20 :31:16#'); the impossible
    month is corrected back to a leading-zero month."""
    r = _load("file_000_9")
    assert r.purchase_date == "2023-09-22"
    assert r.purchase_time == "20:31:16"


def test_currency_by_date():
    """Pre-2026 Lidl receipts are priced in BGN; 2026+ in EUR (euro adoption
    2026-01-01). build_db converts BGN -> EUR."""
    assert _load("file_000_9").currency == "BGN"    # 2023-09-22
    assert _load("file_000_1").currency == "EUR"    # 2026-04-05
    # every fixture gets one of the two, never empty
    for n in _all_fixtures():
        assert _load(n).currency in ("BGN", "EUR")


def test_date_coverage_high():
    """With the space-tolerant footer + month correction, every fixture yields
    a date and time."""
    parsed = [_load(n) for n in _all_fixtures()]
    with_date = sum(p.purchase_date is not None for p in parsed)
    with_time = sum(p.purchase_time is not None for p in parsed)
    assert with_date == 43          # was 39 before the footer fix
    assert with_time == 43          # time was previously never set for Lidl


# Receipts so degraded by OCR that they cannot yield a usable item region or
# >=1 item. Keep this as small as possible; each entry needs a documented reason.
DENYLIST: dict[str, str] = {
    # (currently empty: every fixture yields a region + >=1 item)
}


def _index_totals():
    out = {}
    for ln in (FIX_DIR / "_index.tsv").read_text(encoding="utf-8").splitlines():
        parts = ln.split("\t")
        name = parts[0]
        total = None
        for p in parts[1:]:
            if p.startswith("total="):
                total = float(p[len("total="):].replace(",", "."))
        out[name] = total
    return out


@pytest.mark.parametrize("name", _all_fixtures())
def test_region_and_items(name):
    r = _load(name)
    # unp is never None: УНП line if present, else filename fallback.
    assert r.unp is not None
    if name in DENYLIST:
        pytest.skip(f"denylisted: {DENYLIST[name]}")
    assert len(r.items) >= 1, f"{name}: no items parsed"
    for it in r.items:
        assert it.unit_price > 0, f"{name}: {it.raw_name} unit_price={it.unit_price}"
        assert it.line_total > 0, f"{name}: {it.raw_name} line_total={it.line_total}"
        assert it.vat_class in {"А", "Б", "Г"}, f"{name}: vat={it.vat_class}"


def test_unp_never_none():
    for name in _all_fixtures():
        assert _load(name).unp is not None, name


def test_aggregate_sum_quality():
    totals = _index_totals()
    within = 0
    for name in _all_fixtures():
        r = _load(name)
        total = totals.get(name)
        if total is None or not r.items:
            continue
        s = sum(it.line_total for it in r.items)
        if abs(s - total) <= max(0.05, 0.03 * total):
            within += 1
    # Soft floor from the brief; actual achieved number is higher (see report).
    assert within >= 25, f"only {within}/43 within sum tolerance"


def test_exact_file_1():
    r = _load("file_000_1")
    assert len(r.items) == 13
    first = r.items[0]
    assert first.raw_name == "SCHWEPPES СОДА ВОДА"
    assert first.qty == 2
    assert first.unit_price == 0.97
    assert first.line_total == 1.94
    assert first.vat_class == "Б"


def test_exact_file_12():
    r = _load("file_000_12")
    assert len(r.items) >= 24
    s = sum(it.line_total for it in r.items)
    # The receipt's own printed item amounts sum to 128.28 while it prints
    # ОБЩА СУМА 128.20 -- an 8-cent OCR slip on one item ("КАЙЗЕР ЗЕМЕЛ БЯЛ
    # д,38" reads as 0.38 where 2x0,15=0.30 was intended). The parser faithfully
    # reproduces what is printed, so we lock to 0.10 rather than 0.05 here.
    assert abs(s - 128.20) <= 0.10
