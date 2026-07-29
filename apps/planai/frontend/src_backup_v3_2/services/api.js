const API_BASE = (import.meta?.env?.VITE_PLONAGRAM_API_BASE || import.meta?.env?.VITE_API_BASE || 'http://127.0.0.1:8001').replace(/\/$/, '');

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
  const res = await fetch(url, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) {
    const msg = data?.detail || data?.message || `${res.status} ${res.statusText}`;
    throw new Error(msg);
  }
  return data;
}

export const api = {
  base: API_BASE,
  getHealth: () => request('/'),
  getStores: () => request('/auth/stores'),
  login: (payload) => request('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  getProducts: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/master-products${q ? `?${q}` : ''}`);
  },
  searchProducts: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/master-products/search${q ? `?${q}` : ''}`);
  },
  uploadProductsCsv: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return request('/upload-products-csv', { method: 'POST', body: fd });
  },
  parseLayoutFile: (file, storeCode = 'AUTO') => {
    const fd = new FormData();
    fd.append('file', file);
    return request(`/parse-layout-file?store_code=${encodeURIComponent(storeCode)}`, { method: 'POST', body: fd });
  },
  generatePlanogram: (payload) => request('/generate-planogram', { method: 'POST', body: JSON.stringify(payload) }),
  generatePlanogramLite: (payload) => request('/generate-planogram-lite', { method: 'POST', body: JSON.stringify(payload) }),
  scorePlanogram: (planogram) => request('/score-planogram', { method: 'POST', body: JSON.stringify({ planogram }) }),
  diagnostics: (planogram) => request('/planogram-diagnostics', { method: 'POST', body: JSON.stringify({ planogram }) }),
  validateRules: (planogram) => request('/validate-strict-rules', { method: 'POST', body: JSON.stringify({ planogram }) }),
  updateFacing: (payload) => request('/update-facing', { method: 'POST', body: JSON.stringify(payload) }),
  rotateProduct: (payload) => request('/rotate-product', { method: 'POST', body: JSON.stringify(payload) }),
  moveProduct: (payload) => request('/move-product', { method: 'POST', body: JSON.stringify(payload) }),
  addProductToShelf: (payload) => request('/add-product-to-shelf', { method: 'POST', body: JSON.stringify(payload) }),
  applyModuleRule: (payload) => request('/apply-module-rule', { method: 'POST', body: JSON.stringify(payload) }),
  applyShelfRule: (payload) => request('/apply-shelf-rule', { method: 'POST', body: JSON.stringify(payload) }),
  optimizeShelf: (payload) => request('/optimize-shelf', { method: 'POST', body: JSON.stringify(payload) }),
  optimizeModule: (payload) => request('/optimize-module', { method: 'POST', body: JSON.stringify(payload) }),
  saveUsageLog: (payload) => request('/save-usage-log', { method: 'POST', body: JSON.stringify(payload) }),
};

export default api;
