const BASE = "/api";

async function get(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function put(path, body) {
  const res = await fetch(BASE + path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function del(path) {
  const res = await fetch(BASE + path, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  stats: () => get("/stats"),
  branches: () => get("/branches"),
  facets: () => get("/facets"),
  products: (search = "", minDates = 1, { brand, category } = {}) => {
    const p = new URLSearchParams({ search, min_dates: String(minDates) });
    if (brand) p.set("brand", brand);
    if (category) p.set("category", category);
    return get(`/products?${p.toString()}`);
  },
  prices: (id, { from, to, branch } = {}) => {
    const p = new URLSearchParams();
    if (from) p.set("date_from", from);
    if (to) p.set("date_to", to);
    if (branch) p.set("branch", branch);
    const qs = p.toString();
    return get(`/products/${id}/prices${qs ? "?" + qs : ""}`);
  },
  spend: (by, { from, to } = {}) => {
    const p = new URLSearchParams({ by });
    if (from) p.set("date_from", from);
    if (to) p.set("date_to", to);
    return get(`/analytics/spend?${p.toString()}`);
  },
  receipt: (rid) => get(`/receipts/${rid}`),
  pdfUrl: (rid) => `${BASE}/receipts/${rid}/pdf`,
  productsMeta: (search = "") => get(`/products/meta?search=${encodeURIComponent(search)}`),
  renameProduct: (id, displayName) => put(`/products/${id}/name`, { display_name: displayName }),
  setBasket: (id, inBasket) => put(`/products/${id}/basket`, { in_basket: inBasket }),
  clearBasket: () => del("/basket"),
  basket: () => get("/basket"),
  categories: () => get("/categories"),
  createCategory: (name) => post("/categories", { name }),
  renameCategory: (oldName, newName) => put("/categories/rename", { old_name: oldName, new_name: newName }),
  deleteCategory: (name) => del(`/categories?name=${encodeURIComponent(name)}`),
  categoryProducts: (category, search = "") =>
    get(`/categories/products?category=${encodeURIComponent(category)}&search=${encodeURIComponent(search)}`),
  setProductCategory: (id, category) => put(`/products/${id}/category`, { category }),
  receipts: () => get("/receipts"),
  lineItems: () => get("/line-items"),
};
