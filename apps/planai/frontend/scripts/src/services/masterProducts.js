
const API_BASE = "http://127.0.0.1:8001";

export async function searchMasterProducts({ q = "", storage = "", limit = 80 } = {}) {
  const params = new URLSearchParams({ q, storage, limit: String(limit) });
  const res = await fetch(`${API_BASE}/master-products/search?${params.toString()}`);
  if (!res.ok) throw new Error(`Master product search failed: HTTP ${res.status}`);
  return res.json();
}

export async function loadMasterProducts(limit = 10000) {
  const res = await fetch(`${API_BASE}/master-products?limit=${limit}`);
  if (!res.ok) throw new Error(`Master product load failed: HTTP ${res.status}`);
  return res.json();
}
