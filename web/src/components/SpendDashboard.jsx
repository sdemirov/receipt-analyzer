import { useEffect, useMemo, useState } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api.js";
import { useIsNarrow } from "../useMedia.js";

const VAT_LABELS = { "А": "А · 0%", "Б": "Б · 20%", "Г": "Г · 9%" };
const PIE_COLORS = ["#2a9d8f", "#0070b8", "#0a9d58", "#f39200", "#7b3fa0"];

const GRANULARITY = {
  month: { by: "month", title: "Разходи по месеци" },
  quarter: { by: "quarter", title: "Разходи по тримесечия" },
  year: { by: "year", title: "Разходи по години" },
};

function yearsBetween(first, last) {
  const y1 = parseInt(first.slice(0, 4), 10);
  const y2 = parseInt(last.slice(0, 4), 10);
  const out = [];
  for (let y = y2; y >= y1; y--) out.push(y);
  return out;
}

function periodBounds(period) {
  if (!period) return {};
  if (period.includes("-Q")) {
    const [y, q] = period.split("-Q");
    const qi = parseInt(q, 10);
    const m0 = (qi - 1) * 3 + 1;
    const m1 = qi * 3;
    const from = `${y}-${String(m0).padStart(2, "0")}-01`;
    const lastDay = new Date(parseInt(y, 10), m1, 0).getDate();
    const to = `${y}-${String(m1).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
    return { from, to };
  }
  return { from: `${period}-01-01`, to: `${period}-12-31` };
}

function periodLabel(period) {
  if (!period) return "Всички";
  if (period.includes("-Q")) {
    const [y, q] = period.split("-Q");
    return `${y} · Q${q}`;
  }
  return period;
}

export default function SpendDashboard() {
  const narrow = useIsNarrow();
  const barLeft = narrow ? 72 : 130;
  const barH = narrow ? 280 : 360;
  const topH = narrow ? 320 : 420;
  const pieR = narrow ? 72 : 100;
  const [years, setYears] = useState([]);
  const [period, setPeriod] = useState(""); // "" | "2025" | "2025-Q2"
  const [granularity, setGranularity] = useState("month");
  const [byTime, setByTime] = useState([]);
  const [byStore, setByStore] = useState([]);
  const [byVat, setByVat] = useState([]);
  const [byCategory, setByCategory] = useState([]);
  const [topProducts, setTopProducts] = useState([]);

  const range = useMemo(() => periodBounds(period), [period]);
  const timeMeta = GRANULARITY[granularity] || GRANULARITY.month;

  useEffect(() => {
    api.stats()
      .then((s) => {
        if (s.first_date && s.last_date) setYears(yearsBetween(s.first_date, s.last_date));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const opts = range;
    Promise.all([
      api.spend(timeMeta.by, opts).then(setByTime).catch(() => setByTime([])),
      api.spend("store", opts).then(setByStore).catch(() => setByStore([])),
      api.spend("vat", opts).then(setByVat).catch(() => setByVat([])),
      api.spend("category", opts).then(setByCategory).catch(() => setByCategory([])),
      api.spend("product", opts).then((r) => setTopProducts(r.slice(0, 15))).catch(() => setTopProducts([])),
    ]);
  }, [period, timeMeta.by]);

  const periodTotal = useMemo(
    () => byTime.reduce((s, r) => s + Number(r.spend || 0), 0),
    [byTime],
  );

  return (
    <div className="dash">
      <section className="panel spend-toolbar">
        <div className="filters">
          <label>
            Период
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              <option value="">Всички</option>
              {years.map((y) => (
                <optgroup key={y} label={String(y)}>
                  <option value={String(y)}>{y} · цяла година</option>
                  {[1, 2, 3, 4].map((q) => (
                    <option key={`${y}-Q${q}`} value={`${y}-Q${q}`}>
                      {y} · Q{q}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label>
            Графика
            <select value={granularity} onChange={(e) => setGranularity(e.target.value)}>
              <option value="month">По месеци</option>
              <option value="quarter">По тримесечия</option>
              <option value="year">По години</option>
            </select>
          </label>
        </div>
        {period && (
          <p className="hint spend-period-summary">
            Показани разходи за <b>{periodLabel(period)}</b>
            {!narrow && range.from && <> ({range.from} → {range.to})</>}
            : <b>{periodTotal.toFixed(2)} €</b>
          </p>
        )}
      </section>

      <section className="panel">
        <h3>{timeMeta.title}</h3>
        <ResponsiveContainer width="100%" height={narrow ? 240 : 300}>
          <LineChart data={byTime} margin={{ top: 10, right: 8, left: 4, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="bucket" tick={{ fontSize: narrow ? 10 : 12 }} minTickGap={narrow ? 28 : 20} />
            <YAxis tick={{ fontSize: narrow ? 10 : 12 }} width={narrow ? 40 : 48} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            <Line type="monotone" dataKey="spend" name="Разход" stroke="#3d5a80" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <div className="dash-row">
        <section className="panel half">
          <h3>Разходи по магазин</h3>
          <ResponsiveContainer width="100%" height={narrow ? 220 : 280}>
            <BarChart data={byStore} layout="vertical" margin={{ left: 8, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis type="number" tick={{ fontSize: narrow ? 10 : 12 }} />
              <YAxis type="category" dataKey="branch_id" width={narrow ? 36 : 50} tick={{ fontSize: narrow ? 10 : 12 }} />
              <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`}
                labelFormatter={(l) => byStore.find((s) => s.branch_id === l)?.store_name || l} />
              <Bar dataKey="spend" name="Разход" fill="#0070b8" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel half">
          <h3>Разходи по ДДС група</h3>
          <ResponsiveContainer width="100%" height={narrow ? 220 : 280}>
            <PieChart>
              <Pie data={byVat} dataKey="spend" nameKey="bucket" outerRadius={pieR}
                label={narrow ? false : (e) => `${VAT_LABELS[e.bucket] || e.bucket}: ${e.spend} €`}>
                {byVat.map((e, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            </PieChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="panel">
        <h3>Разходи по категория</h3>
        <ResponsiveContainer width="100%" height={barH}>
          <BarChart data={byCategory} layout="vertical" margin={{ left: barLeft, right: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis type="number" tick={{ fontSize: narrow ? 10 : 12 }} />
            <YAxis type="category" dataKey="bucket" width={barLeft} tick={{ fontSize: narrow ? 10 : 11 }} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            <Bar dataKey="spend" name="Разход" fill="#f39200" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="panel">
        <h3>Топ 15 продукта по обща сума</h3>
        <ResponsiveContainer width="100%" height={topH}>
          <BarChart data={topProducts} layout="vertical" margin={{ left: barLeft, right: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis type="number" tick={{ fontSize: narrow ? 10 : 12 }} />
            <YAxis type="category" dataKey="bucket" width={barLeft} tick={{ fontSize: narrow ? 10 : 11 }} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            <Bar dataKey="spend" name="Обща сума" fill="#0a9d58" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  );
}
