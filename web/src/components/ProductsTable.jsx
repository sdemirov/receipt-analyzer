import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import ReceiptModal from "./ReceiptModal.jsx";

const PAGE = 50;

// Column spec: key, label, accessor, type (num sorts numerically), and an
// optional cell renderer. Mandatory columns: date, product, price (unit), qty.
const COLS = [
  { key: "date", label: "Дата", type: "str",
    val: (r) => `${r.date || ""} ${r.time || ""}`,
    cell: (r) => `${r.date || "—"}${r.time ? " " + r.time.slice(0, 5) : ""}` },
  { key: "product", label: "Продукт", type: "str",
    val: (r) => r.product || r.raw_name || "",
    cell: (r) => <>{r.product}{r.on_promo ? " 🏷" : ""}</> },
  { key: "qty", label: "Кол.", type: "num", val: (r) => r.qty || 0,
    cell: (r) => (r.unit_measure === "kg" ? `${r.qty} кг` : r.qty) },
  { key: "unit_price", label: "Ед. цена", type: "num", val: (r) => r.unit_price || 0,
    cell: (r) => `${(r.unit_price ?? 0).toFixed(2)} €${r.unit_measure === "kg" ? "/кг" : ""}` },
  { key: "line_total", label: "Сума", type: "num", val: (r) => r.line_total || 0,
    cell: (r) => `${(r.line_total ?? 0).toFixed(2)} €` },
  { key: "vat", label: "ДДС", type: "str", val: (r) => r.vat_class || "",
    cell: (r) => r.vat_class || "" },
  { key: "store", label: "Магазин", type: "str",
    val: (r) => (r.store_name || "").replace("Хипермаркет ", "") || `Филиал ${r.branch}`,
    cell: (r) => (r.store_name || "").replace("Хипермаркет ", "") || `Филиал ${r.branch}` },
];

export default function ProductsTable({ selectedIds, onToggleProduct }) {
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(0);
  const [openRid, setOpenRid] = useState(null);
  const [sort, setSort] = useState({ key: "date", dir: "desc" });
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.lineItems().then(setRows).catch(() => setRows([]));
  }, []);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((r) =>
      `${r.product || ""} ${r.raw_name || ""}`.toLowerCase().includes(term));
  }, [rows, query]);

  const sorted = useMemo(() => {
    const c = COLS.find((c) => c.key === sort.key);
    if (!c) return filtered;
    const out = [...filtered].sort((a, b) => {
      const va = c.val(a), vb = c.val(b);
      const cmp = c.type === "num" ? va - vb : String(va).localeCompare(String(vb), "bg");
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return out;
  }, [filtered, sort]);

  function onSort(key) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
    setPage(0);
  }

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE));
  const cur = Math.min(page, pageCount - 1);
  const shown = sorted.slice(cur * PAGE, cur * PAGE + PAGE);

  return (
    <div className="panel receipts">
      <div className="receipts-head">
        <p className="hint">
          {query.trim()
            ? `${sorted.length} от ${rows.length} покупки`
            : `Всички покупки (${rows.length})`}. Кликни заглавие, за да сортираш · ред, за да видиш бележката.
        </p>
        <input
          className="store-filter"
          type="search"
          placeholder="Филтър по продукт…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPage(0); }}
        />
      </div>
      <table className="receipts-table">
        <thead>
          <tr>
            {COLS.map((c) => (
              <th key={c.key} className="sortable" onClick={() => onSort(c.key)}>
                {c.label} <span className="sort-ind">{sort.key === c.key ? (sort.dir === "asc" ? "▲" : "▼") : "↕"}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={`${r.receipt_id}-${r.product_id}-${i}`} className="clickable"
              onClick={() => setOpenRid(r.receipt_id)}>
              {COLS.map((c) => <td key={c.key}>{c.cell(r)}</td>)}
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr><td colSpan={COLS.length} className="muted">
              {rows.length === 0 ? "Няма покупки" : "Няма съвпадения"}
            </td></tr>
          )}
        </tbody>
      </table>

      {sorted.length > PAGE && (
        <div className="pager">
          <button disabled={cur === 0} onClick={() => setPage(cur - 1)}>← Назад</button>
          <span>Стр. {cur + 1} / {pageCount}</span>
          <button disabled={cur >= pageCount - 1} onClick={() => setPage(cur + 1)}>Напред →</button>
        </div>
      )}

      {openRid && (
        <ReceiptModal rid={openRid} onClose={() => setOpenRid(null)}
          selectedIds={selectedIds} onToggleProduct={onToggleProduct} />
      )}
    </div>
  );
}
