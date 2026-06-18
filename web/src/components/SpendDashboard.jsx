import { useEffect, useState } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api.js";

const VAT_LABELS = { "А": "А · 0%", "Б": "Б · 20%", "Г": "Г · 9%" };
const PIE_COLORS = ["#2a9d8f", "#0070b8", "#0a9d58", "#f39200", "#7b3fa0"];

export default function SpendDashboard() {
  const [byMonth, setByMonth] = useState([]);
  const [byStore, setByStore] = useState([]);
  const [byVat, setByVat] = useState([]);
  const [byCategory, setByCategory] = useState([]);
  const [topProducts, setTopProducts] = useState([]);

  useEffect(() => {
    api.spend("month").then(setByMonth).catch(() => {});
    api.spend("store").then(setByStore).catch(() => {});
    api.spend("vat").then(setByVat).catch(() => {});
    api.spend("category").then(setByCategory).catch(() => {});
    api.spend("product").then((r) => setTopProducts(r.slice(0, 15))).catch(() => {});
  }, []);

  return (
    <div className="dash">
      <section className="panel">
        <h3>Разходи по месеци</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={byMonth} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="bucket" tick={{ fontSize: 12 }} minTickGap={20} />
            <YAxis tick={{ fontSize: 12 }} width={48} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            <Line type="monotone" dataKey="spend" name="Разход" stroke="#3d5a80" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <div className="dash-row">
        <section className="panel half">
          <h3>Разходи по магазин</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={byStore} layout="vertical" margin={{ left: 20, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="branch_id" width={50} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`}
                labelFormatter={(l) => byStore.find((s) => s.branch_id === l)?.store_name || l} />
              <Bar dataKey="spend" name="Разход" fill="#0070b8" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel half">
          <h3>Разходи по ДДС група</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={byVat} dataKey="spend" nameKey="bucket" outerRadius={100}
                label={(e) => `${VAT_LABELS[e.bucket] || e.bucket}: ${e.spend} €`}>
                {byVat.map((e, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            </PieChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="panel">
        <h3>Разходи по категория</h3>
        <ResponsiveContainer width="100%" height={360}>
          <BarChart data={byCategory} layout="vertical" margin={{ left: 130, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="bucket" width={130} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            <Bar dataKey="spend" name="Разход" fill="#f39200" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="panel">
        <h3>Топ 15 продукта по обща сума</h3>
        <ResponsiveContainer width="100%" height={420}>
          <BarChart data={topProducts} layout="vertical" margin={{ left: 130, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="bucket" width={130} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(2)} €`} />
            <Bar dataKey="spend" name="Обща сума" fill="#0a9d58" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  );
}
