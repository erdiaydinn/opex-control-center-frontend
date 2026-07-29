const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

async function parseJsonResponse(res) {
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(data?.detail || data?.message || `API error ${res.status}`);
  }
  return data;
}

export async function uploadSkuCatalog(file, { allowAiDimensions = true, persistToMaster = true } = {}) {
  if (!file) throw new Error("SKU catalog dosyası seçilmedi.");

  const form = new FormData();
  form.append("file", file);

  const url = new URL(`${API_BASE}/upload-products-csv`);
  url.searchParams.set("allow_ai_dimensions", String(allowAiDimensions));
  url.searchParams.set("persist_to_master", String(persistToMaster));

  const res = await fetch(url.toString(), { method: "POST", body: form });
  return parseJsonResponse(res);
}

export async function loadSkuLibrary({ limit = 10000, offset = 0 } = {}) {
  const url = new URL(`${API_BASE}/master-products`);
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("offset", String(offset));
  const res = await fetch(url.toString());
  return parseJsonResponse(res);
}

export async function searchSkuLibrary({ q = "", storage = "", fixture = "", brand = "", category = "", limit = 200 } = {}) {
  const url = new URL(`${API_BASE}/master-products/search`);
  if (q) url.searchParams.set("q", q);
  if (storage) url.searchParams.set("storage", storage);
  if (fixture) url.searchParams.set("fixture", fixture);
  if (brand) url.searchParams.set("brand", brand);
  if (category) url.searchParams.set("category", category);
  url.searchParams.set("limit", String(limit));
  const res = await fetch(url.toString());
  return parseJsonResponse(res);
}
