const API_BASE = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) throw new Error(data.detail || data.message || `API error ${res.status}`);
  return data;
}

export const plonagramApi = {
  getStores: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/core/stores${q ? `?${q}` : ""}`);
  },
  getStore: (storeCode) => request(`/core/stores/${storeCode}`),
  getDepotDNA: (storeCode) => request(`/core/depot-dna/${storeCode}`),
  saveDepotDNA: (storeCode, dna) => request(`/core/depot-dna/${storeCode}`, {
    method: "POST",
    body: JSON.stringify(dna),
  }),
  getLayout: (storeCode) => request(`/core/layouts/${storeCode}`),
  saveLayout: (storeCode, layout) => request(`/core/layouts/${storeCode}`, {
    method: "POST",
    body: JSON.stringify({ layout }),
  }),
  getObjectLibrary: () => request("/core/object-library"),
  scoreCapacity: (layout, dna = null) => request("/core/intelligence/capacity", {
    method: "POST",
    body: JSON.stringify({ layout, dna }),
  }),
  scoreRoute: (layout, sequence) => request("/core/intelligence/route", {
    method: "POST",
    body: JSON.stringify({ layout, sequence }),
  }),
};

export default plonagramApi;
