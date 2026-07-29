const API = 'http://127.0.0.1:8001';

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData;
  const res = await fetch(`${API}${path}`, {
    headers: isForm ? (options.headers || {}) : { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = '';
    try { detail = JSON.stringify(await res.json()); } catch { detail = await res.text().catch(() => ''); }
    throw new Error(`API ${path} failed: ${res.status} ${detail}`);
  }
  return res.json();
}

export const api = {
  health: (signal) => request('/', { signal }),
  uploadProducts: (file, signal) => {
    const form = new FormData();
    form.append('file', file);
    return request('/upload-products-csv', { method: 'POST', body: form, signal });
  },
  uploadLayout: (file, storeCode = 'AUTO', signal) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/parse-layout-file?store_code=${encodeURIComponent(storeCode)}`, { method: 'POST', body: form, signal });
  },
  generatePlanogram: (payload, signal) => request('/generate-planogram', { method: 'POST', body: JSON.stringify(payload), signal }),
  generatePlanogramLite: (payload, signal) => request('/generate-planogram-lite', { method: 'POST', body: JSON.stringify(payload), signal }),
  generatePlanogramCouncil: (payload, signal) => request('/generate-planogram-council', { method: 'POST', body: JSON.stringify(payload), signal }),
  scorePlanogram: (payload, signal) => request('/score-planogram', { method: 'POST', body: JSON.stringify(payload), signal }),
  updateFacing: (payload, signal) => request('/update-facing', { method: 'POST', body: JSON.stringify(payload), signal }),
  rotateProduct: (payload, signal) => request('/rotate-product', { method: 'POST', body: JSON.stringify(payload), signal }),
  dbHealth: (signal) => request('/db/health', { signal }),
  bootstrap: (storeCode, signal) => request(`/bootstrap/${encodeURIComponent(storeCode || 'AUTO')}`, { signal }),
  saveStoreDna: (storeCode, dna, signal) => request(`/stores/${encodeURIComponent(storeCode || 'AUTO')}/dna`, { method: 'POST', body: JSON.stringify({ dna, actor: 'frontend' }), signal }),
  saveLayout: (storeCode, layout, note = '', signal) => request(`/layouts/${encodeURIComponent(storeCode || 'AUTO')}/save`, { method: 'POST', body: JSON.stringify({ layout, note, actor: 'frontend' }), signal }),
  latestLayout: (storeCode, signal) => request(`/layouts/${encodeURIComponent(storeCode || 'AUTO')}/latest`, { signal }),
  savePlanogram: (storeCode, planogram, summary = {}, note = '', signal) => request(`/planograms/${encodeURIComponent(storeCode || 'AUTO')}/save`, { method: 'POST', body: JSON.stringify({ planogram, summary, note, actor: 'frontend' }), signal }),
  latestPlanogram: (storeCode, signal) => request(`/planograms/${encodeURIComponent(storeCode || 'AUTO')}/latest`, { signal }),
  createTask: (payload, signal) => request('/tasks', { method: 'POST', body: JSON.stringify(payload), signal }),
  listTasks: (storeCode, signal) => request(`/tasks?store_code=${encodeURIComponent(storeCode || 'AUTO')}`, { signal }),
  readiness: (storeCode, signal) => request(`/stores/${encodeURIComponent(storeCode || 'AUTO')}/readiness`, { signal }),
  getStoreDna: (storeCode, signal) => request(`/stores/${encodeURIComponent(storeCode || 'AUTO')}/dna`, { signal }),
  generateStoreDnaEasy: (storeCode, payload, signal) => request(`/stores/${encodeURIComponent(storeCode || 'AUTO')}/dna/generate-easy`, { method: 'POST', body: JSON.stringify(payload), signal }),
  generateStoreDnaTemplate: (storeCode, payload, signal) => request(`/stores/${encodeURIComponent(storeCode || 'AUTO')}/dna/generate-template`, { method: 'POST', body: JSON.stringify(payload), signal }),
  fixturePools: (storeCode, signal) => request(`/stores/${encodeURIComponent(storeCode || 'AUTO')}/dna/fixture-pools`, { signal }),
  uploadAbc: (storeCode, file, signal) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/abc/upload?store_code=${encodeURIComponent(storeCode || 'AUTO')}`, { method: 'POST', body: form, signal });
  },
  uploadCatalog: (storeCode, file, signal) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/catalog/upload?store_code=${encodeURIComponent(storeCode || 'AUTO')}`, { method: 'POST', body: form, signal });
  },
  catalogStatus: (storeCode, signal) => request(`/catalog/status?store_code=${encodeURIComponent(storeCode || 'AUTO')}`, { signal }),
  latestAbc: (storeCode, signal) => request(`/abc/${encodeURIComponent(storeCode || 'AUTO')}/latest`, { signal }),
  mergeProducts: (storeCode, signal) => request('/products/merge', { method: 'POST', body: JSON.stringify({ store_code: storeCode || 'AUTO' }), signal }),
  mergedProducts: (storeCode, signal) => request(`/products/merged/${encodeURIComponent(storeCode || 'AUTO')}`, { signal }),
  generateFixtureFirstPlanogram: (storeCode, payload = {}, signal) => request(`/planograms/${encodeURIComponent(storeCode || 'AUTO')}/generate-fixture-first`, { method: 'POST', body: JSON.stringify(payload), signal }),
  unplacedCsvUrl: (storeCode, versionId = 'latest') => `${API}/unplaced/${encodeURIComponent(storeCode || 'AUTO')}/${encodeURIComponent(versionId)}/csv`,
  unplacedXlsxUrl: (storeCode, versionId = 'latest') => `${API}/unplaced/${encodeURIComponent(storeCode || 'AUTO')}/${encodeURIComponent(versionId)}/xlsx`,
};
