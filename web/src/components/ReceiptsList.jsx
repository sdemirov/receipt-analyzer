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

  useEffect(() => {
    api.receipts().then(setRows).catch(() => setRows([]));
  }, []);

  const sorted = useMemo(() => {
    const c = COLS.find((c) => c.key === sort.key);
    if (!c) return rows;
    const out = [...rows].sort((a, b) => {
      const va = c.val(a), vb = c.val(b);
      const cmp = c.type === "num" ? va - vb : String(va).localeCompare(String(vb), "bg");
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return out;
  }, [rows, sort]);

  function onSort(key) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
    setPage(0);
  }

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE));
  const cur = Math.min(page, pageCount - 1);
  const shown = sorted.slice(cur * PAGE, cur * PAGE + PAGE);

  return (
    <div className="panel receipts">
      <p className="hint">Всички бележки ({rows.length}). Кликни заглавие, за да сортираш · ред, за да видиш продукти / текст / PDF.</p>
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
          {rows.length === 0 && <tr><td colSpan={6} className="muted">Няма бележки</td></tr>}
        </tbody>
      </table>

      {rows.length > PAGE && (
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
