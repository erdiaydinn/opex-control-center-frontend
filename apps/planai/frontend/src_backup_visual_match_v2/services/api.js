
const API_BASE =
  import.meta.env?.VITE_API_BASE_URL ||
  import.meta.env?.VITE_API_BASE ||
  "http://127.0.0.1:8001";

function buildUrl(path) {
  if (!path) return API_BASE;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

function safeJsonParse(text) {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

async function request(path, options = {}) {
  const headers = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };

  const response = await fetch(buildUrl(path), {
    ...options,
    headers,
  });

  const raw = await response.text();
  const data = safeJsonParse(raw);

  if (!response.ok) {
    const message =
      data?.detail ||
      data?.message ||
      data?.error ||
      `${response.status} ${response.statusText}`;

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export async function apiGet(path) {
  return request(path, { method: "GET" });
}

export async function apiPost(path, body = {}) {
  return request(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function apiPut(path, body = {}) {
  return request(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function apiDelete(path, body = {}) {
  return request(path, {
    method: "DELETE",
    body: JSON.stringify(body),
  });
}

export async function apiUpload(path, file, extraFields = {}) {
  const formData = new FormData();

  if (file) {
    formData.append("file", file);
  }

  Object.entries(extraFields || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      formData.append(key, value);
    }
  });

  return request(path, {
    method: "POST",
    body: formData,
  });
}

export async function apiUploadLayout(file, extraFields = {}) {
  return apiUpload("/upload-layout", file, extraFields);
}

export async function apiUploadProductsCsv(file, extraFields = {}) {
  return apiUpload("/upload-products-csv", file, extraFields);
}

export const api = {
  baseUrl: API_BASE,

  get: apiGet,
  post: apiPost,
  put: apiPut,
  delete: apiDelete,
  upload: apiUpload,
  uploadLayout: apiUploadLayout,
  uploadProductsCsv: apiUploadProductsCsv,

  async login(payload) {
    return apiPost("/auth/login", payload);
  },

  async register(payload) {
    return apiPost("/auth/register", payload);
  },

  async getStores() {
    try {
      return await apiGet("/auth/stores");
    } catch (error) {
      console.warn("getStores fallback:", error?.message || error);
      return {
        stores: [
          {
            store_code: "ACIBADEM",
            code: "ACIBADEM",
            name: "Anka (İstanbul)",
            dmart: "Anka (İstanbul)",
            city: "İstanbul",
            region: "İstanbul-Avrupa",
          },
          {
            store_code: "GUVEN_FR",
            code: "GUVEN_FR",
            name: "Güven (Kocaeli) FR",
            dmart: "Güven (Kocaeli) FR",
            city: "Kocaeli",
            region: "Körfez",
          },
        ],
      };
    }
  },

  async getObjectLibrary() {
    try {
      return await apiGet("/core/object-library");
    } catch (error) {
      console.warn("getObjectLibrary fallback:", error?.message || error);
      return {
        objects: [
          { id: "wall_panel", name: "Duvar Paneli", type: "wall", width: 4, depth: 0.2, height: 3 },
          { id: "round_column", name: "Yuvarlak Kolon", type: "column", width: 0.6, depth: 0.6, height: 3 },
          { id: "rect_column", name: "Dikdörtgen Kolon", type: "column", width: 0.8, depth: 0.5, height: 3 },
          { id: "electric_panel", name: "Elektrik Panosu", type: "utility", width: 1, depth: 0.25, height: 1.8 },
          { id: "emergency_exit", name: "Acil Çıkış", type: "exit", width: 1.5, depth: 0.2, height: 2.2 },
          { id: "dispatch", name: "Dispatch", type: "dispatch", width: 3, depth: 2, height: 0.4 },
          { id: "horizontal_cabinet", name: "Yatay Dolap", type: "fixture", storage_type: "CHILLED", width: 2, depth: 0.9, height: 1.1 },
          { id: "algida_freezer", name: "Algida Dolap", type: "fixture", storage_type: "FROZEN", width: 1.8, depth: 0.8, height: 1.6 },
        ],
      };
    }
  },

  async getProducts(params = {}) {
    const qs = new URLSearchParams();

    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        qs.append(key, value);
      }
    });

    const query = qs.toString();

    try {
      return await apiGet(`/master-products${query ? `?${query}` : ""}`);
    } catch (error) {
      console.warn("getProducts fallback:", error?.message || error);
      return {
        products: [],
        rows: [],
        count: 0,
      };
    }
  },

  async searchProducts(query, limit = 50) {
    try {
      return await apiGet(`/master-products/search?q=${encodeURIComponent(query || "")}&limit=${limit}`);
    } catch (error) {
      console.warn("searchProducts fallback:", error?.message || error);
      return { products: [], rows: [], count: 0 };
    }
  },

  async getDepotDna(storeCode) {
    try {
      return await apiGet(`/core/depot-dna/${encodeURIComponent(storeCode)}`);
    } catch (error) {
      console.warn("getDepotDna fallback:", error?.message || error);
      return null;
    }
  },

  async getLayout(storeCode) {
    try {
      return await apiGet(`/core/layouts/${encodeURIComponent(storeCode)}`);
    } catch (error) {
      console.warn("getLayout fallback:", error?.message || error);
      return null;
    }
  },

  async generatePlanogram(payload) {
    return apiPost("/generate-planogram", payload);
  },

  async generatePlanogramLite(payload) {
    return apiPost("/generate-planogram-lite", payload);
  },

  async scorePlanogram(planogram) {
    return apiPost("/score-planogram", { planogram });
  },

  async diagnostics(planogram) {
    return apiPost("/planogram-diagnostics", { planogram });
  },

  async validateStrictRules(planogram) {
    return apiPost("/validate-strict-rules", { planogram });
  },

  async updateFacing(payload) {
    return apiPost("/update-facing", payload);
  },

  async rotateProduct(payload) {
    return apiPost("/rotate-product", payload);
  },

  async moveProduct(payload) {
    return apiPost("/move-product", payload);
  },

  async removeProduct(payload) {
    return apiPost("/remove-product", payload);
  },

  async addProductToShelf(payload) {
    return apiPost("/add-product-to-shelf", payload);
  },

  async applyModuleRule(payload) {
    return apiPost("/apply-module-rule", payload);
  },

  async applyShelfRule(payload) {
    return apiPost("/apply-shelf-rule", payload);
  },

  async optimizeShelf(payload) {
    return apiPost("/optimize-shelf", payload);
  },

  async optimizeModule(payload) {
    return apiPost("/optimize-module", payload);
  },
};

export default api;
