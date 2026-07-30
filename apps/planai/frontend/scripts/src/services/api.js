const API_BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8001").replace(/\/$/, "");

function makeUrl(path) {
  const p = String(path || "");
  return `${API_BASE}${p.startsWith("/") ? p : `/${p}`}`;
}

async function parseResponse(res) {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return await res.json();
  return await res.text();
}

export async function apiRequest(path, options = {}) {
  const hasBody = options.body !== undefined && options.body !== null;
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;

  const res = await fetch(makeUrl(path), {
    ...options,
    headers: {
      ...(hasBody && !isFormData ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });

  const data = await parseResponse(res);

  if (!res.ok) {
    const msg = typeof data === "string" ? data : data?.detail || data?.message || `API ERROR ${res.status}`;
    throw new Error(msg);
  }

  return data;
}

export async function apiPost(path, payload = {}) {
  return apiRequest(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function apiGet(path) {
  return apiRequest(path, { method: "GET" });
}

export async function apiUploadLayout(file, storeCode = "") {
  const fd = new FormData();
  fd.append("file", file);
  if (storeCode) fd.append("store_code", storeCode);
  return apiRequest(`/parse-layout-file?store_code=${encodeURIComponent(storeCode || "")}`, {
    method: "POST",
    body: fd,
  });
}

export const api = {
  baseUrl: API_BASE,

  getStores: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") qs.set(k, String(v));
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiGet(`/core/stores${suffix}`);
  },

  getStore: (code) => apiGet(`/core/stores/${encodeURIComponent(code)}`),

  getDepotDNA: (storeCode) => apiGet(`/core/depot-dna/${encodeURIComponent(storeCode)}`),
  saveDepotDNA: (storeCode, payload) => apiPost(`/core/depot-dna/${encodeURIComponent(storeCode)}`, payload),

  getLayout: (storeCode) => apiGet(`/core/layouts/${encodeURIComponent(storeCode)}`),
  saveLayout: (storeCode, payload) => apiPost(`/core/layouts/${encodeURIComponent(storeCode)}`, payload),

  getObjectLibrary: () => apiGet("/core/object-library"),

  getProducts: (limit = 200, offset = 0) => apiGet(`/master-products?limit=${limit}&offset=${offset}`),
  searchProducts: (q = "", storage = "", limit = 80) => {
    const qs = new URLSearchParams({ q, storage, limit: String(limit) });
    return apiGet(`/master-products/search?${qs.toString()}`);
  },

  generatePlanogram: (payload) => apiPost("/generate-planogram", payload),
  generatePlanogramLite: (payload) => apiPost("/generate-planogram-lite", payload),

  capacity: (payload) => apiPost("/core/intelligence/capacity", payload),
  route: (payload) => apiPost("/core/intelligence/route", payload),
};

export default api;
