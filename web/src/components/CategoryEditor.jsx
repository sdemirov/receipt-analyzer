import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useIsNarrow } from "../useMedia.js";

function productPayload(p) {
  return JSON.stringify({
    product_id: p.product_id,
    name: p.canonical_name || p.effective,
    category: p.category || "",
  });
}

function readDragProduct(e) {
  try {
    const raw = e.dataTransfer.getData("application/json");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function CategoryEditor() {
  const narrow = useIsNarrow();
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState("");
  const [members, setMembers] = useState([]);
  const [memberSearch, setMemberSearch] = useState("");
  const [addSearch, setAddSearch] = useState("");
  const [addResults, setAddResults] = useState([]);
  const [newName, setNewName] = useState("");
  const [renameTo, setRenameTo] = useState("");
  const [busy, setBusy] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const [draggingId, setDraggingId] = useState(null);
  const addDebounce = useRef();

  function loadCategories() {
    return api.categories().then(setCategories).catch(() => setCategories([]));
  }

  function loadMembers(cat, search = memberSearch) {
    if (!cat) {
      setMembers([]);
      return Promise.resolve();
    }
    return api.categoryProducts(cat, search).then(setMembers).catch(() => setMembers([]));
  }

  useEffect(() => { loadCategories(); }, []);

  useEffect(() => {
    setRenameTo(selected);
    loadMembers(selected);
  }, [selected]);

  useEffect(() => {
    const t = setTimeout(() => loadMembers(selected, memberSearch), 200);
    return () => clearTimeout(t);
  }, [memberSearch, selected]);

  useEffect(() => {
    clearTimeout(addDebounce.current);
    if (!addSearch.trim()) {
      setAddResults([]);
      return;
    }
    addDebounce.current = setTimeout(() => {
      api.productsMeta(addSearch)
        .then((rows) => setAddResults(rows.slice(0, 30)))
        .catch(() => setAddResults([]));
    }, 250);
  }, [addSearch]);

  async function createCategory() {
    const name = newName.trim();
    if (!name) return;
    setBusy("create");
    try {
      await api.createCategory(name);
      setNewName("");
      await loadCategories();
      setSelected(name);
    } finally {
      setBusy(null);
    }
  }

  async function saveRename() {
    const next = renameTo.trim();
    if (!selected || !next || next === selected) return;
    setBusy("rename");
    try {
      await api.renameCategory(selected, next);
      await loadCategories();
      setSelected(next);
    } finally {
      setBusy(null);
    }
  }

  async function removeCategory() {
    if (!selected) return;
    if (!window.confirm(`Изтрий категорията „${selected}"? Продуктите ще останат без категория.`)) return;
    setBusy("delete");
    try {
      await api.deleteCategory(selected);
      setSelected("");
      setRenameTo("");
      await loadCategories();
    } finally {
      setBusy(null);
    }
  }

  async function assignProduct(pid, targetCategory, fromCategory = "") {
    const cat = (targetCategory || "").trim();
    if (!cat) return;
    if (fromCategory === cat) return;
    setBusy(pid);
    try {
      await api.setProductCategory(pid, cat);
      await loadCategories();
      if (cat === selected) await loadMembers(selected);
      else if (fromCategory === selected) {
        setMembers((rows) => rows.filter((r) => r.product_id !== pid));
      }
      setAddResults((rows) => rows.map((r) =>
        r.product_id === pid ? { ...r, category: cat } : r));
    } finally {
      setBusy(null);
    }
  }

  async function unassignProduct(pid) {
    setBusy(pid);
    try {
      await api.setProductCategory(pid, "");
      await Promise.all([loadMembers(selected), loadCategories()]);
      setAddResults((rows) => rows.map((r) =>
        r.product_id === pid ? { ...r, category: "" } : r));
    } finally {
      setBusy(null);
    }
  }

  function onProductDragStart(e, product) {
    setDraggingId(product.product_id);
    e.dataTransfer.setData("application/json", productPayload(product));
    e.dataTransfer.effectAllowed = "move";
  }

  function onProductDragEnd() {
    setDraggingId(null);
    setDropTarget(null);
  }

  function onCategoryDragOver(e, name) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDropTarget(name);
  }

  function onCategoryDrop(e, name) {
    e.preventDefault();
    setDropTarget(null);
    const product = readDragProduct(e);
    if (!product) return;
    assignProduct(product.product_id, name, product.category);
  }

  function renderProductRow(p, { inMembers = false } = {}) {
    const id = p.product_id;
    const label = p.canonical_name || p.effective;
    return (
      <li
        key={id}
        className={`draggable${draggingId === id ? " dragging" : ""}${inMembers ? "" : " clickable"}`}
        draggable
        onDragStart={(e) => onProductDragStart(e, {
          product_id: id,
          canonical_name: label,
          effective: label,
          category: inMembers ? selected : (p.category || ""),
        })}
        onDragEnd={onProductDragEnd}
        onClick={inMembers ? undefined : () => selected && assignProduct(id, selected, p.category)}
      >
        <span className="drag-handle" title="Влачи към категория">⠿</span>
        <span className="cp-name">{label}</span>
        {!inMembers && (
          <span className="cp-meta">
            {p.category ? `сега: ${p.category}` : "без категория"}
          </span>
        )}
        {inMembers ? (
          <button type="button" className="cp-remove" disabled={busy === id}
            title="Премахни от категорията"
            onClick={(e) => { e.stopPropagation(); unassignProduct(id); }}>×</button>
        ) : (
          <button type="button" className="cp-add" disabled={busy === id || !selected}
            title={selected ? "Добави в избраната категория" : "Избери категория или влачи наляво"}
            onClick={(e) => { e.stopPropagation(); assignProduct(id, selected, p.category); }}>+</button>
        )}
      </li>
    );
  }

  const selectedInfo = categories.find((c) => c.name === selected);

  return (
    <div className={`grid category-grid${narrow ? " narrow" : ""}`}>
      <aside className="panel category-list-panel">
        <h3>Категории</h3>
        <p className="hint category-dnd-hint">Влачи продукт отдясно върху категория.</p>
        <div className="category-create">
          <input
            className="search"
            placeholder="Нова категория…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createCategory()}
          />
          <button type="button" disabled={!newName.trim() || busy === "create"}
            onClick={createCategory}>
            {busy === "create" ? "…" : "+ Добави"}
          </button>
        </div>
        <ul className="category-list">
          {categories.map((c) => (
            <li
              key={c.name}
              className={[
                c.name === selected ? "on" : "",
                dropTarget === c.name ? "drag-over" : "",
              ].filter(Boolean).join(" ")}
              onClick={() => setSelected(c.name)}
              onDragOver={(e) => onCategoryDragOver(e, c.name)}
              onDragLeave={() => setDropTarget((t) => (t === c.name ? null : t))}
              onDrop={(e) => onCategoryDrop(e, c.name)}
            >
              <span className="cat-name">{c.name}</span>
              <span className="cat-count">{c.products}</span>
            </li>
          ))}
          {categories.length === 0 && <li className="empty">Няма категории</li>}
        </ul>
      </aside>

      <section className="panel category-detail">
        {selected ? (
          <>
            <div className="category-detail-head">
              <h3>{selected}</h3>
              <span className="muted">{selectedInfo?.products ?? 0} продукта</span>
            </div>

            <div className="category-rename">
              <input value={renameTo} onChange={(e) => setRenameTo(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && saveRename()} />
              <button type="button" disabled={busy === "rename" || renameTo.trim() === selected || !renameTo.trim()}
                onClick={saveRename}>
                {busy === "rename" ? "…" : "Преименувай"}
              </button>
              <button type="button" className="danger" disabled={busy === "delete"}
                onClick={removeCategory}>
                {busy === "delete" ? "…" : "Изтрий"}
              </button>
            </div>

            <div className="category-section">
              <h4>Продукти в категорията</h4>
              <input className="search" placeholder="Търси в категорията…"
                value={memberSearch} onChange={(e) => setMemberSearch(e.target.value)} />
              <ul className="category-products">
                {members.map((p) => renderProductRow(p, { inMembers: true }))}
                {members.length === 0 && (
                  <li className="empty">Няма продукти — влачи отдолу или търси</li>
                )}
              </ul>
            </div>
          </>
        ) : (
          <div className="placeholder">Избери категория отляво, за да видиш продуктите ѝ.</div>
        )}

        <div className="category-section">
          <h4>Търси продукт</h4>
          <input className="search" placeholder="Търси продукт (BG/EN)…"
            value={addSearch} onChange={(e) => setAddSearch(e.target.value)} />
          <ul className="category-products add">
            {addResults.map((p) => renderProductRow(p))}
            {addSearch.trim() && addResults.length === 0 && (
              <li className="empty">Няма резултати</li>
            )}
          </ul>
        </div>
      </section>
    </div>
  );
}
