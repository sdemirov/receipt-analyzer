"""Parse every receipt PDF and (re)build the SQLite database.

Run:  python -m extract.build_db

Idempotent: the DB is rebuilt from scratch each run, but the product mapping
CSV is preserved and only extended, so manual corrections survive re-runs.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from config import (BGN_PER_EUR, DB_PATH, MAPPING_CSV, PRODUCT_META_CSV,
                    RECEIPTS_DIR, UNPARSED_LOG)
from extract.categorize import guess_brand, guess_category
from extract.normalize import build_mapping, load_mapping, save_mapping
from extract.parse import ParsedReceipt, parse_receipt
from translit import search_key

VAT_RATES = {"А": 0.0, "Б": 20.0, "Г": 9.0}

SCHEMA = """
DROP TABLE IF EXISTS line_items;
DROP TABLE IF EXISTS receipt_pdfs;
DROP TABLE IF EXISTS receipts;
DROP TABLE IF EXISTS products;

CREATE TABLE receipts (
    id              INTEGER PRIMARY KEY,
    unp             TEXT UNIQUE,
    purchase_date   TEXT,
    purchase_time   TEXT,
    branch_id       TEXT,
    store_name      TEXT,
    subtotal        REAL,
    total           REAL,
    card_savings    REAL,
    promo_savings   REAL,
    payment_method  TEXT,
    points          INTEGER,
    source_pdf      TEXT,
    raw_text        TEXT
);

CREATE TABLE receipt_pdfs (
    receipt_id      INTEGER PRIMARY KEY REFERENCES receipts(id),
    pdf             BLOB,
    media_type      TEXT
);

CREATE TABLE products (
    id              INTEGER PRIMARY KEY,
    canonical_name  TEXT,
    brand           TEXT,
    category        TEXT,
    search_key      TEXT,  -- Latin phonetic skeleton for BG<->EN search
    in_basket       INTEGER DEFAULT 0  -- "Потребителска кошница" membership
);

CREATE TABLE line_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id      INTEGER REFERENCES receipts(id),
    product_id      INTEGER REFERENCES products(id),
    raw_name        TEXT,
    qty             REAL,
    unit_price      REAL,
    line_total      REAL,
    vat_class       TEXT,
    vat_rate        REAL,
    unit_measure    TEXT,
    on_promo        INTEGER,
    promo_saving    REAL
);

CREATE INDEX idx_items_product ON line_items(product_id);
CREATE INDEX idx_items_receipt ON line_items(receipt_id);
CREATE INDEX idx_receipts_date ON receipts(purchase_date);
"""


META_FIELDS = ["product_id", "canonical_name", "display_name", "brand", "category", "in_basket"]


def load_meta() -> dict[int, dict]:
    if not PRODUCT_META_CSV.exists():
        return {}
    out = {}
    with PRODUCT_META_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out[int(row["product_id"])] = {
                "brand": row.get("brand", "") or "",
                "category": row.get("category", "") or "",
                "display_name": (row.get("display_name", "") or "").strip(),
                "in_basket": (row.get("in_basket", "") or "").strip(),
            }
    return out


def effective_name(auto_canonical: str, meta_row: dict) -> str:
    """User-edited display name if set, otherwise the auto canonical name."""
    return (meta_row.get("display_name") or "").strip() or auto_canonical


def _in_basket(meta_row: dict) -> int:
    return 1 if str(meta_row.get("in_basket", "")).strip() in ("1", "true", "True") else 0


def _write_meta(rows: list[dict]) -> None:
    with PRODUCT_META_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=META_FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in META_FIELDS} for r in rows)


def build_meta(products: dict[int, str]) -> dict[int, dict]:
    """Per-product editable metadata: keep user edits, guess new ones."""
    existing = load_meta()
    meta = {}
    for pid, canonical in products.items():
        if pid in existing:
            meta[pid] = existing[pid]
        else:
            meta[pid] = {"brand": guess_brand(canonical),
                         "category": guess_category(canonical),
                         "display_name": "", "in_basket": ""}
    # persist (editable source of truth). canonical_name is the auto name (read-
    # only reference); edit display_name to rename, in_basket for the basket.
    _write_meta([{"product_id": pid, "canonical_name": products[pid],
                  "display_name": meta[pid].get("display_name", ""),
                  "brand": meta[pid]["brand"], "category": meta[pid]["category"],
                  "in_basket": meta[pid].get("in_basket", "")}
                 for pid in sorted(products)])
    return meta


def _set_meta_field(pid: int, field: str, value: str) -> None:
    """Update one product's metadata field in product_meta.csv (preserve the rest)."""
    with PRODUCT_META_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    found = False
    for r in rows:
        if int(r["product_id"]) == pid:
            r[field] = value
            found = True
            break
    if not found:
        raise KeyError(pid)
    _write_meta(rows)


def set_display_name(pid: int, display_name: str) -> None:
    _set_meta_field(pid, "display_name", (display_name or "").strip())


def set_in_basket(pid: int, in_basket: bool) -> None:
    _set_meta_field(pid, "in_basket", "1" if in_basket else "")


def apply_meta_to_db() -> int:
    """Re-apply names, search keys, brand/category and basket flag from the CSVs
    to the existing DB (no PDF re-parse). Returns number of products updated."""
    mapping = load_mapping(MAPPING_CSV)        # raw_name -> (canonical, pid)
    meta = load_meta()
    raw_by_pid: dict[int, list[str]] = defaultdict(list)
    auto: dict[int, str] = {}
    for raw, (canon, pid) in mapping.items():
        raw_by_pid[pid].append(raw)
        auto[pid] = canon
    con = sqlite3.connect(DB_PATH)
    try:
        for pid, canon in auto.items():
            m = meta.get(pid, {})
            eff = effective_name(canon, m)
            key = search_key(" ".join([eff, *raw_by_pid[pid]]))
            con.execute(
                """UPDATE products SET canonical_name = ?, search_key = ?,
                          brand = ?, category = ?, in_basket = ? WHERE id = ?""",
                (eff, key, m.get("brand", ""), m.get("category", ""),
                 _in_basket(m), pid))
        con.commit()
    finally:
        con.close()
    return len(auto)


def parse_all() -> list[ParsedReceipt]:
    from extract.parse_lidl import parse_lidl
    sources = sorted(RECEIPTS_DIR.glob("*.pdf")) + sorted(RECEIPTS_DIR.glob("*.png"))
    receipts, unparsed_log = [], []
    for p in sources:
        r = parse_lidl(p) if p.suffix.lower() == ".png" else parse_receipt(p)
        receipts.append(r)
        for line in r.unparsed:
            unparsed_log.append(f"{r.source_pdf}\t{line}")
    UNPARSED_LOG.write_text("\n".join(unparsed_log), encoding="utf-8")
    return receipts


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    receipts = parse_all()
    print(f"Parsed {len(receipts)} receipts.")

    # --- de-duplicate receipts first (re-downloaded copies share a UNP) ---
    kept: list[ParsedReceipt] = []
    skipped = duplicates = 0
    seen_unp: set[str] = set()
    for r in receipts:
        if r.unp is None:
            skipped += 1
        elif r.unp in seen_unp:
            duplicates += 1
        else:
            seen_unp.add(r.unp)
            kept.append(r)

    for r in kept:
        if r.item_count_hint and len(r.items) != r.item_count_hint:
            print(f"  [check] {r.source_pdf}: parsed {len(r.items)} items "
                  f"but receipt says {r.item_count_hint}")
        # Only Lidl PNGs have item prices that should sum to the grand total.
        # Kaufland PDFs print a total that is net of card/promo savings, so
        # sum(line_total) == subtotal there, not total -- skip them.
        if r.total and r.items and r.source_pdf.lower().endswith(".png"):
            s = round(sum(it.line_total for it in r.items), 2)
            if abs(s - r.total) > 0.05:
                print(f"  [check] {r.source_pdf}: items sum {s} != total {r.total}")

    # --- product mapping built only from kept receipts (preserve user edits) ---
    raw_names = [it.raw_name for r in kept for it in r.items]
    mapping = build_mapping(raw_names, load_mapping(MAPPING_CSV))
    save_mapping(mapping, MAPPING_CSV)
    products = {pid: canonical for canonical, pid in mapping.values()}
    print(f"{len(raw_names)} line items -> {len(products)} distinct products "
          f"(mapping: {MAPPING_CSV}).")

    # --- brand/category (auto-suggested, user-editable) ---
    meta = build_meta(products)
    n_brand = sum(1 for m in meta.values() if m["brand"])
    n_cat = sum(1 for m in meta.values() if m["category"])
    print(f"brand/category suggested for {n_brand}/{n_cat} of {len(products)} "
          f"products (edit: {PRODUCT_META_CSV}).")

    # --- write database ---
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    cur = con.cursor()

    # Effective display name = user override (display_name) or auto canonical.
    # Search key skeleton uses the effective name + every raw-name variant, so
    # both the edited words ("кисело мляко") and the original ("КМ") are findable.
    raw_by_pid: dict[int, list[str]] = defaultdict(list)
    for raw, (_canon, pid) in mapping.items():
        raw_by_pid[pid].append(raw)
    eff = {pid: effective_name(products[pid], meta[pid]) for pid in products}
    keys = {pid: search_key(" ".join([eff[pid], *raw_by_pid[pid]]))
            for pid in products}

    cur.executemany(
        "INSERT INTO products (id, canonical_name, brand, category, search_key, in_basket) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(pid, eff[pid], meta[pid]["brand"], meta[pid]["category"], keys[pid],
          _in_basket(meta[pid]))
         for pid in sorted(products)],
    )

    for r in kept:
        # All amounts are stored in EUR; convert pre-2026 BGN receipts.
        f = 1.0 if r.currency == "EUR" else 1.0 / BGN_PER_EUR
        eur = lambda v: (round(v * f, 2) if v is not None else None)
        cur.execute(
            """INSERT INTO receipts
               (unp, purchase_date, purchase_time, branch_id, store_name,
                subtotal, total, card_savings, promo_savings, payment_method,
                points, source_pdf, raw_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r.unp, r.purchase_date, r.purchase_time, r.branch_id, r.store_name,
             eur(r.subtotal), eur(r.total), eur(r.card_savings), eur(r.promo_savings),
             r.payment_method, r.points, r.source_pdf, r.raw_text),
        )
        rid = cur.lastrowid
        # store the original source bytes in the DB with its media type
        src_path = RECEIPTS_DIR / r.source_pdf
        if src_path.exists():
            media = "image/png" if src_path.suffix.lower() == ".png" else "application/pdf"
            cur.execute(
                "INSERT INTO receipt_pdfs (receipt_id, pdf, media_type) VALUES (?, ?, ?)",
                (rid, src_path.read_bytes(), media))
        for it in r.items:
            pid = mapping[it.raw_name][1]
            cur.execute(
                """INSERT INTO line_items
                   (receipt_id, product_id, raw_name, qty, unit_price,
                    line_total, vat_class, vat_rate, unit_measure,
                    on_promo, promo_saving)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, pid, it.raw_name, it.qty, eur(it.unit_price), eur(it.line_total),
                 it.vat_class, VAT_RATES.get(it.vat_class), it.unit_measure,
                 int(it.on_promo), eur(it.promo_saving)),
            )

    con.commit()
    n_receipts = cur.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    n_items = cur.execute("SELECT COUNT(*) FROM line_items").fetchone()[0]
    con.close()

    print(f"DB written: {DB_PATH}")
    print(f"  receipts: {n_receipts}  line_items: {n_items}  products: {len(products)}")
    if skipped:
        print(f"  skipped {skipped} receipts with no UNP")
    if duplicates:
        print(f"  skipped {duplicates} duplicate (re-downloaded) receipts")
    unparsed_count = len([l for l in UNPARSED_LOG.read_text(encoding='utf-8').splitlines() if l])
    print(f"  unparsed lines: {unparsed_count} (see {UNPARSED_LOG})")


if __name__ == "__main__":
    main()
