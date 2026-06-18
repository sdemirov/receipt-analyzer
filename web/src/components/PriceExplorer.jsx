import { useEffect, useMemo, useRef, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api.js";
import ReceiptModal from "./ReceiptModal.jsx";

const COLORS = [
  "#2a9d8f", "#0070b8", "#0a9d58", "#f39200", "#7b3fa0",
  "#00a3a3", "#c2185b", "#5d4037", "#455a64", "#afb42b",
];

// Dot renderer: gold ringed marker on promo dates, small colored dot otherwise.
// A larger transparent circle on top makes the point easy to click (opens the
// receipt for that purchase).
function makeDot(pid, color, onPick) {
  return function Dot(props) {
    const { cx, cy, payload, index } = props;
    if (cx == null || cy == null || payload[pid] == null) return null;
    const rid = payload[`${pid}_rid`];
    const marker = payload[`${pid}_promo`] ? (
      <g>
        <circle cx={cx} cy={cy} r={7} fill="#ffd400" stroke={color} strokeWidth={2} />
        <text x={cx} y={cy + 3} textAnchor="middle" fontSize={9} fontWeight="700">%</text>
      </g>
    ) : (
      <circle cx={cx} cy={cy} r={3} fill={color} />
    );
    return (
      <g key={`dot-${pid}-${index}`} style={{ cursor: rid ? "pointer" : "default" }}
         onClick={() => rid && onPick(rid)}>
        {marker}
        <circle cx={cx} cy={cy} r={11} fill="transparent" />
      </g>
    );
  };
}

function PriceTooltip({ active, payload, label, names }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="tt-date">{label}</div>
      {payload.map((s) => {
        const promo = s.payload[`${s.dataKey}_promo`];
        return (
          <div key={s.dataKey} className="tt-row">
            <i style={{ background: s.color }} />
            <span>{names[s.dataKey]}: <b>{Number(s.value).toFixed(2)} €</b></span>
            {promo && (
              <span className="tt-promo">
                🏷 промоция −{promo.saving.toFixed(2)} € (редовна {promo.regular.toFixed(2)} €)
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function PriceExplorer({ selected, setSelected, hidden, setHidden, toggle }) {
  const [search, setSearch] = useState("");
  const [products, setProducts] = useState([]);
  const [series, setSeries] = useState({});      // id -> points[]
  const [branches, setBranches] = useState([]);
  const [facets, setFacets] = useState({ brands: [], categories: [] });
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [filters, setFilters] = useState({ from: "", to: "", branch: "" });
  const [openRid, setOpenRid] = useState(null);
  const debounce = useRef();

  useEffect(() => {
    api.branches().then(setBranches).catch(() => {});
    api.facets().then(setFacets).catch(() => {});
  }, []);

  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      // Idle list shows comparable products (>=2 dates); any active search or
      // filter reveals everything, including products bought only once.
      const minDates = search.trim() || brand || category ? 1 : 2;
      api.products(search, minDates, { brand, category })
        .then(setProducts).catch(() => setProducts([]));
    }, 250);
  }, [search, brand, category]);

  // (Re)load price series for every selected product whenever filters change.
  useEffect(() => {
    let cancelled = false;
    Promise.all(
      selected.map((p) =>
        api.prices(p.id, filters).then((r) => [p.id, r.points])
      )
    ).then((entries) => {
      if (!cancelled) setSeries(Object.fromEntries(entries));
    });
    return () => { cancelled = true; };
  }, [selected, filters]);

  function toggleHidden(id) {
    setHidden((h) => {
      const n = new Set(h);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  function showBasket() {
    api.basket()
      .then((items) => setSelected(items.map((p) => ({
        id: p.id, canonical_name: p.canonical_name, unit_measure: p.unit_measure,
      }))))
      .catch(() => {});
  }

  // Merge each product's points into one array keyed by date. Promo info for a
  // (date, product) is stored under "<id>_promo" for the dot + tooltip.
  const chartData = useMemo(() => {
    const byDate = new Map();
    for (const p of selected) {
      for (const pt of series[p.id] || []) {
        if (!byDate.has(pt.date)) byDate.set(pt.date, { date: pt.date });
        const row = byDate.get(pt.date);
        row[p.id] = pt.unit_price;
        row[`${p.id}_rid`] = pt.receipt_id;
        if (pt.on_promo) row[`${p.id}_promo`] = { saving: pt.promo_saving, regular: pt.regular_price };
      }
    }
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [selected, series]);

  const nameById = useMemo(
    () => Object.fromEntries(selected.map((p) => [p.id, p.canonical_name])),
    [selected]
  );

  return (
    <>
    <div className="grid">
      <aside className="panel picker">
        <input
          className="search"
          placeholder="Търси продукт…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="facet-filters">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Всички категории</option>
            {facets.categories.map((c) => (
              <option key={c.name} value={c.name}>{c.name} ({c.products})</option>
            ))}
          </select>
          <select value={brand} onChange={(e) => setBrand(e.target.value)}>
            <option value="">Всички марки</option>
            {facets.brands.map((b) => (
              <option key={b.name} value={b.name}>{b.name} ({b.products})</option>
            ))}
          </select>
        </div>
        <div className="basket-row">
          <button className="basket-btn" onClick={showBasket}>🧺 Покажи кошницата</button>
          {selected.length > 0 && (
            <button className="basket-btn clear"
              onClick={() => { setSelected([]); setHidden(new Set()); }}>
              ✕ Изчисти ({selected.length})
            </button>
          )}
        </div>
        <p className="hint">По подразбиране се показват продукти с ≥2 дати; търсене/филтър намира всички (вкл. еднократни покупки).</p>
        <ul className="product-list">
          {products.map((p) => {
            const on = selected.find((x) => x.id === p.id);
            return (
              <li key={p.id} className={on ? "on" : ""} onClick={() => toggle(p)}>
                <span className="pl-name">{p.canonical_name}</span>
                <span className="pl-meta">
                  {p.dates} дати · {p.min_price.toFixed(2)}–{p.max_price.toFixed(2)} €
                  {p.unit_measure === "kg" ? " /кг" : ""}
                  {p.category ? ` · ${p.category}` : ""}
                </span>
              </li>
            );
          })}
          {products.length === 0 && <li className="empty">Няма резултати</li>}
        </ul>
      </aside>

      <section className="panel chart-area">
        <div className="filters">
          <label>От <input type="date" value={filters.from}
            onChange={(e) => setFilters({ ...filters, from: e.target.value })} /></label>
          <label>До <input type="date" value={filters.to}
            onChange={(e) => setFilters({ ...filters, to: e.target.value })} /></label>
          <label>Магазин
            <select value={filters.branch}
              onChange={(e) => setFilters({ ...filters, branch: e.target.value })}>
              <option value="">Всички</option>
              {branches.map((b) => (
                <option key={b.branch_id} value={b.branch_id}>
                  {b.store_name?.replace("Хипермаркет Кауфланд ", "") || b.branch_id}
                </option>
              ))}
            </select>
          </label>
        </div>

        {selected.length === 0 ? (
          <div className="placeholder">Избери продукт отляво, за да видиш цената му във времето.</div>
        ) : (
          <>
            <p className="promo-hint">
              <b>Кликни върху точка</b>, за да видиш бележката за тази покупка. Точките с
              <b> жълт маркер „%"</b> са в промоция.
            </p>
            <div className="chips">
              {selected.map((p, i) => (
                <span key={p.id} className={hidden.has(p.id) ? "chip off" : "chip"}
                  style={{ borderColor: COLORS[i % COLORS.length] }}
                  title={hidden.has(p.id) ? "Покажи на графиката" : "Скрий от графиката"}
                  onClick={() => toggleHidden(p.id)}>
                  <i style={{ background: COLORS[i % COLORS.length] }} />
                  {p.canonical_name}
                  <button title="Премахни" onClick={(e) => { e.stopPropagation(); toggle(p); }}>×</button>
                </span>
              ))}
            </div>
            <ResponsiveContainer width="100%" height={460}>
              <LineChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} minTickGap={24} />
                <YAxis tick={{ fontSize: 12 }} width={48}
                  label={{ value: "€", angle: -90, position: "insideLeft", fontSize: 12 }} />
                <Tooltip content={<PriceTooltip names={nameById} />} />
                <Legend />
                {selected.map((p, i) => (
                  hidden.has(p.id) ? null : (
                  <Line key={p.id} type="monotone" dataKey={String(p.id)} name={p.canonical_name}
                    stroke={COLORS[i % COLORS.length]} strokeWidth={2}
                    dot={makeDot(String(p.id), COLORS[i % COLORS.length], setOpenRid)}
                    activeDot={{ r: 5, onClick: (e, pl) => pl?.payload?.[`${p.id}_rid`] && setOpenRid(pl.payload[`${p.id}_rid`]) }}
                    connectNulls />
                  )
                ))}
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </section>
    </div>
    {openRid && (
      <ReceiptModal rid={openRid} onClose={() => setOpenRid(null)}
        selectedIds={new Set(selected.map((s) => s.id))}
        onToggleProduct={toggle} />
    )}
    </>
  );
}
