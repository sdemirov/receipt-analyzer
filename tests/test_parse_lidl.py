from pathlib import Path
from extract.parse_lidl import parse_lidl_text

FIX = Path(__file__).parent / "fixtures" / "lidl_sample_1.txt"


def _parsed():
    return parse_lidl_text(FIX.read_text(encoding="utf-8"), "lidl_sample_1.png")


def test_metadata():
    r = _parsed()
    assert r.unp == "BN013286-0009-0559315"
    assert r.purchase_date == "2026-04-05"
    assert r.currency == "EUR"
    assert r.total == 4.29
    assert r.subtotal == 4.29
    assert r.payment_method == "Карта"


def test_items():
    r = _parsed()
    assert len(r.items) == 3
    soda, bag, milk = r.items
    assert (soda.raw_name, soda.qty, soda.unit_price, soda.line_total, soda.vat_class) \
        == ("СОДА ВОДА", 2, 0.97, 1.94, "Б")
    assert (bag.qty, bag.unit_price, bag.line_total) == (1, 0.15, 0.15)
    assert (milk.qty, milk.unit_price, milk.line_total) == (2, 1.10, 2.20)
    assert not r.unparsed


def test_item_count_matches_checksum():
    r = _parsed()
    assert r.item_count_hint == 3
    assert len(r.items) == r.item_count_hint
