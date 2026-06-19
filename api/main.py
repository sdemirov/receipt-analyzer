"""FastAPI backend serving the Kaufland receipts data (read-only SQLite).

Run:  uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import csv
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from config import DB_PATH, PRODUCT_META_CSV
from extract.build_db import apply_meta_to_db, set_display_name, set_in_basket
from translit import search_key


class RenameBody(BaseModel):
    display_name: str = ""


class BasketBody(BaseModel):
    in_basket: bool = False

app = FastAPI(title="Digital Receipts Analyzer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # local/personal app
    allow_methods=["*"],
    allow_headers=["*"],
)


def q(sql: str, params: tuple = ()) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    # Unicode-aware lowercase (SQLite's built-in LOWER/LIKE only fold ASCII,
    # so this is what makes Cyrillic search case-insensitive).
    con.create_function("pylower", 1,
                        lambda s: s.lower() if s is not None else s,
                        deterministic=True)
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


@app.get("/stats")
def stats() -> dict:
    row = q(
        """SELECT COUNT(*) AS receipts,
                  (SELECT COUNT(*) FROM products)   AS products,
                  (SELECT COUNT(*) FROM line_items) AS line_items,
                  MIN(purchase_date) AS first_date,
                  MAX(purchase_date) AS last_date,
                  ROUND(SUM(total), 2)        AS total_spend,
                  ROUND(SUM(card_savings), 2) AS card_savings,
                  ROUND(SUM(promo_savings), 2) AS promo_savings
           FROM receipts"""
    )[0]
    return row


@app.get("/branches")
def branches() -> list[dict]:
    return q(
        """SELECT branch_id,
                  MAX(store_name) AS store_name,
                  COUNT(*)        AS receipts
           FROM receipts GROUP BY branch_id ORDER BY receipts DESC"""
    )


@app.get("/facets")
def facets() -> dict:
    """Distinct brands and categories (with product counts) for filters."""
    return {
        "brands": q(
            """SELECT brand AS name, COUNT(*) AS products FROM products
               WHERE brand <> '' GROUP BY brand ORDER BY name"""
        ),
        "categories": q(
            """SELECT category AS name, COUNT(*) AS products FROM products
               WHERE category <> '' GROUP BY category ORDER BY name"""
        ),
    }


@app.get("/products")
def products(
    search: str = "",
    min_dates: int = 1,
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
) -> list[dict]:
    sql = """SELECT p.id,
                    p.canonical_name,
                    p.brand,
                    p.category,
                    COUNT(li.id)                    AS purchases,
                    COUNT(DISTINCT r.purchase_date) AS dates,
                    MIN(li.unit_price)              AS min_price,
                    MAX(li.unit_price)              AS max_price,
                    MAX(li.unit_measure)            AS unit_measure
             FROM products p
             JOIN line_items li ON li.product_id = p.id
             JOIN receipts r    ON r.id = li.receipt_id
             WHERE p.search_key LIKE ?"""
    params: list = [f"%{search_key(search)}%"]
    if brand:
        sql += " AND p.brand = ?"; params.append(brand)
    if category:
        sql += " AND p.category = ?"; params.append(category)
    sql += " GROUP BY p.id HAVING dates >= ? ORDER BY dates DESC, purchases DESC"
    params.append(min_dates)
    return q(sql, tuple(params))


@app.get("/products/meta")
def products_meta(search: str = "") -> list[dict]:
    """All products with their auto name + editable display name (for renaming)."""
    if not PRODUCT_META_CSV.exists():
        return []
    key = search_key(search)
    out = []
    with PRODUCT_META_CSV.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            auto = r.get("canonical_name", "")
            disp = (r.get("display_name", "") or "").strip()
            if key and key not in search_key(f"{auto} {disp}"):
                continue
            in_basket = str(r.get("in_basket", "") or "").strip() in ("1", "true", "True")
            out.append({"product_id": int(r["product_id"]), "auto_name": auto,
                        "display_name": disp, "effective": disp or auto,
                        "in_basket": in_basket})
    out.sort(key=lambda x: x["effective"].lower())
    return out


@app.put("/products/{pid}/name")
def rename_product(pid: int, body: RenameBody) -> dict:
    """Set a product's display name; persists to product_meta.csv + applies live."""
    try:
        set_display_name(pid, body.display_name)
    except KeyError:
        raise HTTPException(404, "product not found")
    apply_meta_to_db()
    row = q("SELECT canonical_name FROM products WHERE id = ?", (pid,))
    return {"product_id": pid, "effective": row[0]["canonical_name"] if row else None}


@app.put("/products/{pid}/basket")
def set_basket(pid: int, body: BasketBody) -> dict:
    """Add/remove a product to the 'Потребителска кошница'; persists + applies live."""
    try:
        set_in_basket(pid, body.in_basket)
    except KeyError:
        raise HTTPException(404, "product not found")
    apply_meta_to_db()
    return {"product_id": pid, "in_basket": body.in_basket}


@app.get("/basket")
def basket() -> list[dict]:
    """Products in the basket (shape compatible with the price chart selection)."""
    return q(
        """SELECT p.id, p.canonical_name,
                  MAX(li.unit_measure) AS unit_measure
           FROM products p JOIN line_items li ON li.product_id = p.id
           WHERE p.in_basket = 1
           GROUP BY p.id ORDER BY p.canonical_name COLLATE NOCASE"""
    )


@app.get("/products/{product_id}/prices")
def product_prices(
    product_id: int,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
) -> dict:
    prod = q("SELECT id, canonical_name FROM products WHERE id = ?", (product_id,))
    if not prod:
        raise HTTPException(404, "product not found")

    sql = """SELECT r.purchase_date AS date,
                    r.id             AS receipt_id,
                    li.unit_price    AS unit_price,
                    li.line_total    AS line_total,
                    li.qty           AS qty,
                    li.unit_measure  AS unit_measure,
                    li.raw_name      AS raw_name,
                    li.on_promo      AS on_promo,
                    li.promo_saving  AS promo_saving,
                    ROUND(li.unit_price + li.promo_saving / li.qty, 2) AS regular_price,
                    r.branch_id      AS branch
             FROM line_items li JOIN receipts r ON r.id = li.receipt_id
             WHERE li.product_id = ?"""
    params: list = [product_id]
    if date_from:
        sql += " AND r.purchase_date >= ?"; params.append(date_from)
    if date_to:
        sql += " AND r.purchase_date <= ?"; params.append(date_to)
    if branch:
        sql += " AND r.branch_id = ?"; params.append(branch)
    sql += " ORDER BY r.purchase_date"
    return {"product": prod[0], "points": q(sql, tuple(params))}


@app.get("/analytics/spend")
def spend(by: str = "month") -> list[dict]:
    if by == "month":
        return q(
            """SELECT substr(purchase_date, 1, 7) AS bucket,
                      ROUND(SUM(total), 2)         AS spend,
                      COUNT(*)                     AS receipts
               FROM receipts GROUP BY bucket ORDER BY bucket"""
        )
    if by == "store":
        return q(
            """SELECT branch_id AS bucket,
                      MAX(store_name) AS store_name,
                      ROUND(SUM(total), 2) AS spend,
                      COUNT(*) AS receipts
               FROM receipts GROUP BY branch_id ORDER BY spend DESC"""
        )
    if by == "vat":
        return q(
            """SELECT vat_class AS bucket,
                      ROUND(SUM(line_total), 2) AS spend,
                      COUNT(*) AS items
               FROM line_items GROUP BY vat_class ORDER BY spend DESC"""
        )
    if by == "product":
        return q(
            """SELECT p.canonical_name AS bucket,
                      ROUND(SUM(li.line_total), 2) AS spend,
                      COUNT(*) AS items
               FROM line_items li JOIN products p ON p.id = li.product_id
               GROUP BY p.id ORDER BY spend DESC LIMIT 30"""
        )
    if by in ("category", "brand"):
        col = "category" if by == "category" else "brand"
        return q(
            f"""SELECT CASE WHEN p.{col}='' THEN '(няма)' ELSE p.{col} END AS bucket,
                       ROUND(SUM(li.line_total), 2) AS spend,
                       COUNT(*) AS items
                FROM line_items li JOIN products p ON p.id = li.product_id
                GROUP BY bucket ORDER BY spend DESC"""
        )
    raise HTTPException(400, "by must be one of: month, store, vat, product, category, brand")


@app.get("/receipts/{rid}")
def receipt_detail(rid: int) -> dict:
    head = q(
        """SELECT id, unp, purchase_date, purchase_time, branch_id, store_name,
                  subtotal, total, card_savings, promo_savings, payment_method,
                  points, source_pdf, raw_text
           FROM receipts WHERE id = ?""",
        (rid,),
    )
    if not head:
        raise HTTPException(404, "receipt not found")
    items = q(
        """SELECT li.product_id, li.raw_name, p.canonical_name, li.qty, li.unit_price,
                  li.line_total, li.vat_class, li.unit_measure,
                  li.on_promo, li.promo_saving
           FROM line_items li JOIN products p ON p.id = li.product_id
           WHERE li.receipt_id = ? ORDER BY li.id""",
        (rid,),
    )
    row = head[0]
    return {"receipt": row, "items": items, "text": row.pop("raw_text", "") or ""}


@app.get("/receipts/{rid}/pdf")
def receipt_pdf(rid: int):
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute(
            "SELECT pdf, media_type FROM receipt_pdfs WHERE receipt_id = ?",
            (rid,)).fetchone()
    finally:
        con.close()
    if not row or row[0] is None:
        raise HTTPException(404, "media not found")
    media_type = row[1] or "application/pdf"
    return Response(content=row[0], media_type=media_type,
                    headers={"Content-Disposition": "inline"})


@app.get("/receipts")
def receipts() -> list[dict]:
    return q(
        """SELECT r.id, r.purchase_date, r.purchase_time, r.branch_id, r.store_name,
                  r.total, r.card_savings, r.promo_savings, r.payment_method, r.points,
                  COUNT(li.id) AS n_items
           FROM receipts r LEFT JOIN line_items li ON li.receipt_id = r.id
           GROUP BY r.id ORDER BY r.purchase_date DESC, r.purchase_time DESC"""
    )
