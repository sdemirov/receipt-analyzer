import { useEffect, useState } from "react";
import { api } from "./api.js";
import PriceExplorer from "./components/PriceExplorer.jsx";
import SpendDashboard from "./components/SpendDashboard.jsx";
import RenameEditor from "./components/RenameEditor.jsx";
import CategoryEditor from "./components/CategoryEditor.jsx";
import ReceiptsList from "./components/ReceiptsList.jsx";
import ProductsTable from "./components/ProductsTable.jsx";

const TABS = ["prices", "spend", "receipts", "products", "rename", "categories"];
const tabFromHash = () => {
  const h = window.location.hash.replace(/^#\/?/, "");
  return TABS.includes(h) ? h : "prices";
};

export default function App() {
  const [tab, setTab] = useState(tabFromHash);
  const [stats, setStats] = useState(null);
  // Chart selection lives here so it persists across tabs (e.g. adding a
  // product from the Бележки tab populates the Цени във времето chart).
  const [selected, setSelected] = useState([]); // [{id, canonical_name, unit_measure}]
  const [hidden, setHidden] = useState(new Set()); // product ids hidden from chart
  const toggleProduct = (p) => {
    setSelected((cur) =>
      cur.find((x) => x.id === p.id) ? cur.filter((x) => x.id !== p.id) : [...cur, p]
    );
    setHidden((h) => { const n = new Set(h); n.delete(p.id); return n; });
  };

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats({ error: true }));
  }, []);

  // Keep the tab in the URL hash so refresh / back-forward preserve the page.
  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (t) => { window.location.hash = t; setTab(t); };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">🧾</span>
          <div>
            <h1>Digital Receipts Analyzer</h1>
            <p className="sub">Проследяване на цени и разходи</p>
          </div>
        </div>
        {stats && !stats.error && (
          <div className="kpis">
            <Kpi label="Бележки" value={stats.receipts} />
            <Kpi label="Продукти" value={stats.products} />
            <Kpi label="Общо разход" value={`${stats.total_spend} €`} />
            <Kpi label="Период" value={`${stats.first_date} → ${stats.last_date}`} small />
          </div>
        )}
      </header>

      <nav className="tabs">
        <button className={tab === "prices" ? "active" : ""} onClick={() => go("prices")}>
          Цени във времето{selected.length > 0 ? ` (${selected.length})` : ""}
        </button>
        <button className={tab === "spend" ? "active" : ""} onClick={() => go("spend")}>
          Разходи
        </button>
        <button className={tab === "receipts" ? "active" : ""} onClick={() => go("receipts")}>
          🧾 Бележки
        </button>
        <button className={tab === "products" ? "active" : ""} onClick={() => go("products")}>
          📋 Продукти
        </button>
        <button className={tab === "rename" ? "active" : ""} onClick={() => go("rename")}>
          ✏️ Редакция
        </button>
        <button className={tab === "categories" ? "active" : ""} onClick={() => go("categories")}>
          🏷 Категории
        </button>
      </nav>

      <main>
        {tab === "prices" && (
          <PriceExplorer selected={selected} setSelected={setSelected}
            hidden={hidden} setHidden={setHidden} toggle={toggleProduct} />
        )}
        {tab === "spend" && <SpendDashboard />}
        {tab === "receipts" && (
          <ReceiptsList selectedIds={new Set(selected.map((s) => s.id))}
            onToggleProduct={toggleProduct} />
        )}
        {tab === "products" && (
          <ProductsTable selectedIds={new Set(selected.map((s) => s.id))}
            onToggleProduct={toggleProduct} />
        )}
        {tab === "rename" && <RenameEditor />}
        {tab === "categories" && <CategoryEditor />}
      </main>
    </div>
  );
}

function Kpi({ label, value, small }) {
  return (
    <div className="kpi">
      <div className={small ? "kpi-value small" : "kpi-value"}>{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  );
}
