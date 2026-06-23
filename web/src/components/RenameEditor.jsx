import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useIsNarrow } from "../useMedia.js";

const PAGE = 20;

function RenameRow({ r, edits, setEdits, busy, saveName, toggleBasket }) {
  const val = edits[r.product_id] ?? r.effective;
  const changed = val !== r.effective;
  const toSave = val.trim() === r.auto_name ? "" : val;

  return (
  <>
    <div className="rename-card-head">
      <span className="cur">{r.effective}</span>
      {r.display_name && <span className="auto">авто: {r.auto_name}</span>}
    </div>
    <input value={val} placeholder={r.auto_name}
      onChange={(e) => setEdits({ ...edits, [r.product_id]: e.target.value })}
      onKeyDown={(e) => e.key === "Enter" && changed && saveName(r.product_id, toSave)} />
    <div className="rename-card-actions">
      <button disabled={!changed || busy === r.product_id}
        onClick={() => saveName(r.product_id, toSave)}>
        {busy === r.product_id ? "…" : "Запази"}
      </button>
      {r.display_name && (
        <button className="reset" title="Върни автоматичното име"
          onClick={() => saveName(r.product_id, "")}>↺</button>
      )}
      <button className={r.in_basket ? "in-basket" : "add-basket"}
        disabled={busy === r.product_id}
        onClick={() => toggleBasket(r.product_id, !r.in_basket)}>
        {r.in_basket ? "🧺 Премахни" : "🧺 Добави"}
      </button>
    </div>
  </>
  );
}

export default function RenameEditor() {
  const narrow = useIsNarrow();
  const [search, setSearch] = useState("");
  const [basketOnly, setBasketOnly] = useState(false);
  const [rows, setRows] = useState([]);
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(null);
  const [page, setPage] = useState(0);
  const debounce = useRef();

  function load() {
    api.productsMeta(search).then(setRows).catch(() => setRows([]));
  }

  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => { setPage(0); load(); }, 250);
  }, [search]);

  async function saveName(id, value) {
    setBusy(id);
    try {
      await api.renameProduct(id, value);
      setEdits((e) => { const n = { ...e }; delete n[id]; return n; });
      load();
    } finally { setBusy(null); }
  }

  async function toggleBasket(id, next) {
    setBusy(id);
    try {
      await api.setBasket(id, next);
      load();
    } finally { setBusy(null); }
  }

  async function clearBasket() {
    if (!window.confirm("Премахни всички продукти от потребителската кошница?")) return;
    setBusy("clear");
    try {
      await api.clearBasket();
      setBasketOnly(false);
      load();
    } finally { setBusy(null); }
  }

  const filtered = basketOnly ? rows.filter((r) => r.in_basket) : rows;
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE));
  const cur = Math.min(page, pageCount - 1);
  const shown = filtered.slice(cur * PAGE, cur * PAGE + PAGE);
  const inBasket = rows.filter((r) => r.in_basket).length;

  const rowProps = { edits, setEdits, busy, saveName, toggleBasket };

  return (
    <div className="panel rename">
      <p className="hint">
        Преименувай продукт (напр. „Балкан Био <b>КМ</b> 3,6%" → „Балкан Био
        <b> кисело мляко</b> 3,6%"); празно = автоматичното име. Добави продукти в
        <b> 🧺 Потребителска кошница</b>, за да ги гледаш заедно в „Цени във времето".
        {inBasket > 0 && <> Сега в кошницата: <b>{inBasket}</b>.</>}
      </p>
      <input className="search" placeholder="Търси продукт (BG/EN)…"
        value={search} onChange={(e) => setSearch(e.target.value)} />
      <div className="basket-toolbar">
        <button type="button"
          className={basketOnly ? "basket-filter on" : "basket-filter"}
          onClick={() => { setBasketOnly((v) => !v); setPage(0); }}>
          🧺 Само кошницата{inBasket > 0 ? ` (${inBasket})` : ""}
        </button>
        {inBasket > 0 && (
          <button type="button" className="basket-filter clear"
            disabled={busy === "clear"}
            onClick={clearBasket}>
            {busy === "clear" ? "…" : "Изчисти цялата кошница"}
          </button>
        )}
      </div>

      {narrow ? (
        <div className="rename-cards">
          {shown.map((r) => (
            <div key={r.product_id} className={`rename-card${r.in_basket ? " basket" : ""}`}>
              <RenameRow r={r} {...rowProps} />
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="muted rename-empty">
              {basketOnly ? "Кошницата е празна" : "Няма резултати"}
            </p>
          )}
        </div>
      ) : (
        <div className="table-scroll">
          <table className="rename-table">
            <thead>
              <tr><th>Текущо име</th><th>Ново име</th><th></th><th>Кошница</th></tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const val = edits[r.product_id] ?? r.effective;
                const changed = val !== r.effective;
                const toSave = val.trim() === r.auto_name ? "" : val;
                return (
                  <tr key={r.product_id} className={r.in_basket ? "basket" : ""}>
                    <td>
                      <span className="cur">{r.effective}</span>
                      {r.display_name && <span className="auto">авто: {r.auto_name}</span>}
                    </td>
                    <td>
                      <input value={val} placeholder={r.auto_name}
                        onChange={(e) => setEdits({ ...edits, [r.product_id]: e.target.value })}
                        onKeyDown={(e) => e.key === "Enter" && changed && saveName(r.product_id, toSave)} />
                    </td>
                    <td className="actions">
                      <button disabled={!changed || busy === r.product_id}
                        onClick={() => saveName(r.product_id, toSave)}>
                        {busy === r.product_id ? "…" : "Запази"}
                      </button>
                      {r.display_name && (
                        <button className="reset" title="Върни автоматичното име"
                          onClick={() => saveName(r.product_id, "")}>↺</button>
                      )}
                    </td>
                    <td className="actions">
                      <button className={r.in_basket ? "in-basket" : "add-basket"}
                        disabled={busy === r.product_id}
                        onClick={() => toggleBasket(r.product_id, !r.in_basket)}>
                        {r.in_basket ? "🧺 Премахни" : "🧺 Добави"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr><td colSpan={4} className="muted">
                  {basketOnly ? "Кошницата е празна" : "Няма резултати"}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="pager">
          <button disabled={cur === 0} onClick={() => setPage(cur - 1)}>← Назад</button>
          <span>Стр. {cur + 1} / {pageCount} · {filtered.length} продукта</span>
          <button disabled={cur >= pageCount - 1} onClick={() => setPage(cur + 1)}>Напред →</button>
        </div>
      )}
    </div>
  );
}
