const API_BASE = import.meta?.env?.VITE_PLANOGRAM_API_URL || "http://127.0.0.1:8001";

async function safeJson(res) {
  const text = await res.text();
  try { return text ? JSON.parse(text) : {}; } catch { return { raw: text }; }
}

export async function uploadAbcAndBuildTwin(file, options = {}) {
  if (!file) throw new Error("ABC dosyası seçilmedi.");
  const fd = new FormData();
  fd.append("file", file);
  if (options.storeCode) fd.append("store_code", options.storeCode);
  if (options.catalogMode) fd.append("catalog_mode", options.catalogMode);

  const res = await fetch(`${API_BASE}/visual-twin/abc-upload-build`, {
    method: "POST",
    body: fd,
  });
  const data = await safeJson(res);
  if (!res.ok) throw new Error(data?.detail || data?.message || "ABC upload/build başarısız.");
  return data;
}

export async function buildVisualTwinFromProducts(payload) {
  const res = await fetch(`${API_BASE}/visual-twin/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const data = await safeJson(res);
  if (!res.ok) throw new Error(data?.detail || data?.message || "Visual Twin payload üretilemedi.");
  return data;
}

export async function getCatalogStatus() {
  const res = await fetch(`${API_BASE}/data-pipeline/catalog/status`);
  const data = await safeJson(res);
  if (!res.ok) throw new Error(data?.detail || data?.message || "Catalog status alınamadı.");
  return data;
}

export function summarizeTwinPayload(payload) {
  const p = payload || {};
  const products = p.products || p.visual_products || [];
  const excluded = p.excluded_products || p.excluded || [];
  const review = p.review_products || p.review || [];
  const withImage = products.filter((x) => x.image_url || x.visual?.image_url).length;
  return {
    total: p.total_products ?? products.length + excluded.length + review.length,
    sellable: p.sellable_products_count ?? products.length,
    excluded: p.excluded_products_count ?? excluded.length,
    review: p.review_products_count ?? review.length,
    withImage,
    imageCoveragePct: products.length ? Math.round((withImage / products.length) * 100) : 0,
  };
}
