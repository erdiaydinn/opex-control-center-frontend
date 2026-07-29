const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const message = data?.detail || data?.message || `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data;
}

export async function uploadProductsCsv(file, allowAiDimensions = true) {
  const form = new FormData();
  form.append("file", file);
  return request(`/upload-products-csv?allow_ai_dimensions=${allowAiDimensions ? "true" : "false"}`, {
    method: "POST",
    body: form,
  });
}

export async function fetchProductLibrary({ q = "", storage = "", limit = 300, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (storage) params.set("storage", storage);
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  if (q || storage) {
    return request(`/master-products/search?${params.toString()}`);
  }
  return request(`/master-products?${params.toString()}`);
}

export async function scorePlanogramV19(planogram) {
  return request("/intelligence-v19/score-planogram", {
    method: "POST",
    body: JSON.stringify({ planogram }),
  });
}

export async function productConfidenceV19({ product, aisle, module, shelf, existing_products }) {
  return request("/intelligence-v19/product-confidence", {
    method: "POST",
    body: JSON.stringify({ product, aisle, module, shelf, existing_products }),
  });
}

export async function compareShelfChangeV19({ shelf, current_product, candidate_product, aisle, module }) {
  return request("/intelligence-v19/compare-shelf-change", {
    method: "POST",
    body: JSON.stringify({ shelf, current_product, candidate_product, aisle, module }),
  });
}

export async function sortSuggestionsV19({ products, shelf }) {
  return request("/intelligence-v19/sort-suggestions", {
    method: "POST",
    body: JSON.stringify({ products, shelf }),
  });
}

export { API_BASE };
