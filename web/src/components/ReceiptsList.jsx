import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import ReceiptModal from "./ReceiptModal.jsx";

const PAGE = 30;

// Column spec: key, label, accessor, and type (num sorts numerically).
const COLS = [
  { key: "date", label: "Дата", type: "str", val: (r) => `${r.purchase_date} ${r.purchase_time || ""}` },
  { key: "store", label: "Магазин", type: "str", val: (r) => (r.store_name || "").replace("Хипермаркет ", "") || `Филиал ${r.branch_id}` },
  { key: "items", label: "Бр.", type: "num", val: (r) => r.n_items || 0 },
  { key: "total", label: "Сума", type: "num", val: (r) => r.total || 0 },
  { key: "pay", label: "Плащане", type: "str", val: (r) => r.payment_method || "" },
  { key: "saved", label: "Спестено", type: "num", val: (r) => (r.card_savings || 0) + (r.promo_savings || 0) },
];

export default function ReceiptsList({ selectedIds, onToggleProduct }) {
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(0);
  const [openRid, setOpenRid] = useState(null);
  const [sort, setSort] = useState({ key: "date", dir: "desc" });
  const [storeQuery, setStoreQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    api.receipts().then(setRows).catch(() => setRows([]));
  }, []);

  const filtered = useMemo(() => {
    let out = rows;
    if (dateFrom) out = out.filter((r) => r.purchase_date >= dateFrom);
    if (dateTo) out = out.filter((r) => r.purchase_date <= dateTo);
    const q = storeQuery.trim().toLowerCase();
    if (q) {
      out = out.filter((r) =>
        `${r.store_name || ""} ${r.branch_id || ""}`.toLowerCase().includes(q));
    }
    return out;
  }, [rows, storeQuery, dateFrom, dateTo]);

  const hasFilter = !!(storeQuery.trim() || dateFrom || dateTo);

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
          {hasFilter
            ? `${filtered.length} от ${rows.length} бележки`
            : `Всички бележки (${rows.length})`}
          . Кликни заглавие, за да сортираш · ред, за да видиш продукти / текст / PDF.
        </p>
        <div className="receipts-filters">
          <div className="filters">
            <label>
              От
              <input type="date" value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setPage(0); }} />
            </label>
            <label>
              До
              <input type="date" value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setPage(0); }} />
            </label>
          </div>
          <input
            className="store-filter"
            type="search"
            placeholder="Филтър по магазин… (напр. Лидл)"
            value={storeQuery}
            onChange={(e) => { setStoreQuery(e.target.value); setPage(0); }}
          />
        </div>
      </div>
      <div className="table-scroll">
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
          {shown.map((r) => {
            const saved = (r.card_savings || 0) + (r.promo_savings || 0);
            return (
              <tr key={r.id} className="clickable" onClick={() => setOpenRid(r.id)}>
                <td>{r.purchase_date} {r.purchase_time ? r.purchase_time.slice(0, 5) : ""}</td>
                <td>{(r.store_name || "").replace("Хипермаркет ", "") || `Филиал ${r.branch_id}`}</td>
                <td>{r.n_items}</td>
                <td>{r.total != null ? `${r.total.toFixed(2)} €` : ""}</td>
                <td>{r.payment_method}</td>
                <td>{saved > 0 ? `−${saved.toFixed(2)} €` : ""}</td>
              </tr>
            );
          })}
          {sorted.length === 0 && (
            <tr><td colSpan={6} className="muted">
              {rows.length === 0 ? "Няма бележки" : "Няма съвпадения за избраните филтри"}
            </td></tr>
          )}
        </tbody>
      </table>
      </div>

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
