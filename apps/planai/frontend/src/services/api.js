const API_BASE =
  import.meta.env?.VITE_API_BASE_URL ||
  import.meta.env?.VITE_API_BASE ||
  "http://127.0.0.1:8001";

const AUTH_STORAGE_KEY = "plonagram_access_token";
const USER_STORAGE_KEY = "plonagram_user";

function getAccessToken() {
  try {
    return localStorage.getItem(AUTH_STORAGE_KEY) || sessionStorage.getItem(AUTH_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function rememberSession(data) {
  if (!data?.access_token) return data;
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, data.access_token);
    if (data.user) localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(data.user));
  } catch {}
  return data;
}

function forgetSession() {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    sessionStorage.removeItem(USER_STORAGE_KEY);
  } catch {}
}

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
  const token = getAccessToken();
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;

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

export async function apiGet(path, signal) {
  return request(path, { method: "GET", signal });
}

export async function apiPost(path, body = {}, signal) {
  return request(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

export async function apiPut(path, body = {}, signal) {
  return request(path, {
    method: "PUT",
    body: JSON.stringify(body),
    signal,
  });
}

export async function apiDelete(path, body = {}, signal) {
  return request(path, {
    method: "DELETE",
    body: JSON.stringify(body),
    signal,
  });
}

export async function apiUpload(path, file, extraFields = {}, signal) {
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
    signal,
  });
}

export async function apiUploadLayout(file, extraFields = {}, signal) {
  return apiUpload("/parse-layout-file", file, extraFields, signal);
}

export async function apiUploadProductsCsv(file, extraFields = {}, signal) {
  return apiUpload("/upload-products-csv", file, extraFields, signal);
}

function buildQuery(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      qs.append(key, value);
    }
  });
  const query = qs.toString();
  return query ? `?${query}` : "";
}

export const api = {
  baseUrl: API_BASE,

  get: apiGet,
  post: apiPost,
  put: apiPut,
  delete: apiDelete,
  upload: apiUpload,

  // ---------------------------------------------------------------
  // SKU CATALOG / PRODUCT LIBRARY
  // Frontend (App.jsx handleSkuFile, DataViews ProductLibrary) bu
  // metodlari cagiriyor. Backend gercek endpointleri:
  //   POST /upload-products-csv  -> persist_to_master=true ile yazar
  //   GET  /product-library      -> canli master_products.csv okur
  //   GET  /master-products/search -> SKU/barkod/ad/marka/kategori arar
  // ---------------------------------------------------------------

  async uploadProducts(file, signal) {
    // persist_to_master backend tarafinda zaten varsayilan true; UI'nin
    // upload sonrasi Product Library'yi canli catalogtan yenilemesi icin
    // bu cagrinin master_products.csv'ye yazmasi sarttir.
    return apiUploadProductsCsv(file, { persist_to_master: true, allow_ai_dimensions: true }, signal);
  },

  async uploadProductsCsv(file, extraFields = {}, signal) {
    return apiUploadProductsCsv(file, extraFields, signal);
  },

  async productLibrary(limit = 1000, offset = 0, signal) {
    return apiGet(`/product-library${buildQuery({ limit, offset })}`, signal);
  },

  async searchProductLibrary({ q = "", storage = "", limit = 500 } = {}, signal) {
    // Backend /master-products/search: q SKU/barkod/ad/marka/kategori uzerinde arar,
    // storage AMBIENT/CHILLED/FROZEN ile filtreler.
    return apiGet(`/master-products/search${buildQuery({ q, storage, limit })}`, signal);
  },

  async getProducts(params = {}, signal) {
    return apiGet(`/master-products${buildQuery(params)}`, signal);
  },

  async searchProducts(query, limit = 50, signal) {
    return apiGet(`/master-products/search${buildQuery({ q: query || "", limit })}`, signal);
  },

  async getProduct(sku, signal) {
    return apiGet(`/master-products/${encodeURIComponent(sku)}`, signal);
  },

  // ---------------------------------------------------------------
  // STORE DNA + ABC / CATALOG PIPELINE
  // StoreDNASetupWizard ve ABCCatalogUploadPanel bu metodlari cagiriyor.
  // Backend hafif uyumlu endpointler sunar; tam persistence yoksa bile
  // 404 yerine guvenli readiness/status objesi doner.
  // ---------------------------------------------------------------

  async generateStoreDnaEasy(storeCode, payload, signal) {
    return apiPost(`/stores/${encodeURIComponent(storeCode || "AUTO")}/dna/generate-easy`, payload || {}, signal);
  },

  async generateStoreDnaTemplate(storeCode, payload, signal) {
    return apiPost(`/stores/${encodeURIComponent(storeCode || "AUTO")}/dna/generate-template`, payload || {}, signal);
  },

  async getStoreDna(storeCode, signal) {
    try {
      return await apiGet(`/stores/${encodeURIComponent(storeCode || "AUTO")}/dna`, signal);
    } catch (error) {
      console.warn("getStoreDna unavailable:", error?.message || error);
      return null;
    }
  },

  async catalogStatus(storeCode, signal) {
    try {
      return await apiGet(`/catalog/status${buildQuery({ store_code: storeCode || "AUTO" })}`, signal);
    } catch (error) {
      console.warn("catalogStatus unavailable:", error?.message || error);
      return null;
    }
  },

  async latestAbc(storeCode, signal) {
    try {
      return await apiGet(`/abc/${encodeURIComponent(storeCode || "AUTO")}/latest`, signal);
    } catch (error) {
      console.warn("latestAbc unavailable:", error?.message || error);
      return null;
    }
  },

  async uploadAbc(storeCode, file, signal) {
    return apiUpload(`/abc/upload${buildQuery({ store_code: storeCode || "AUTO" })}`, file, {}, signal);
  },

  async uploadCatalog(storeCode, file, signal) {
    return apiUpload(`/catalog/upload${buildQuery({ store_code: storeCode || "AUTO" })}`, file, {}, signal);
  },

  async mergeProducts(storeCode, signal) {
    return apiPost("/products/merge", { store_code: storeCode || "AUTO" }, signal);
  },

  // ---------------------------------------------------------------
  // LAYOUT
  // ---------------------------------------------------------------

  async uploadLayout(file, store, signal) {
    return apiUploadLayout(file, { store_code: store || "AUTO" }, signal);
  },

  // ---------------------------------------------------------------
  // PLANOGRAM ENGINE
  // App.jsx generateOptimalPlan -> generatePlanogramCouncil ile
  // backend saglik/enrichment kontrolu yapar (sonucu placement source
  // olarak kullanmaz; tek motor lokal allocator'dir).
  // ---------------------------------------------------------------

  async generatePlanogram(payload, signal) {
    return apiPost("/generate-planogram", payload, signal);
  },

  async generatePlanogramCouncil(payload, signal) {
    return apiPost("/generate-planogram", payload, signal);
  },

  async generatePlanogramLite(payload, signal) {
    return apiPost("/generate-planogram-lite", payload, signal);
  },

  async generatePlanogramFast(payload, signal) {
    return apiPost("/generate-planogram-fast", payload, signal);
  },

  async scorePlanogram(planogram, signal) {
    return apiPost("/score-planogram", { planogram }, signal);
  },

  async diagnostics(planogram, signal) {
    return apiPost("/planogram-diagnostics", { planogram }, signal);
  },

  async validateStrictRules(planogram, signal) {
    return apiPost("/validate-strict-rules", { planogram }, signal);
  },

  async pickingRoute(payload, signal) {
    return apiPost("/picking-route", payload, signal);
  },

  // ---------------------------------------------------------------
  // SHELF / MODULE EDIT OPERATIONS
  // ---------------------------------------------------------------

  async updateFacing(payload, signal) {
    return apiPost("/update-facing", payload, signal);
  },

  async rotateProduct(payload, signal) {
    return apiPost("/rotate-product", payload, signal);
  },

  async moveProduct(payload, signal) {
    return apiPost("/move-product", payload, signal);
  },

  async removeProduct(payload, signal) {
    return apiPost("/remove-product", payload, signal);
  },

  async addProductToShelf(payload, signal) {
    return apiPost("/add-product-to-shelf", payload, signal);
  },

  async reorderShelf(payload, signal) {
    return apiPost("/reorder-shelf", payload, signal);
  },

  async applyModuleRule(payload, signal) {
    return apiPost("/apply-module-rule", payload, signal);
  },

  async applyShelfRule(payload, signal) {
    return apiPost("/apply-shelf-rule", payload, signal);
  },

  async optimizeShelf(payload, signal) {
    return apiPost("/optimize-shelf", payload, signal);
  },

  async optimizeModule(payload, signal) {
    return apiPost("/optimize-module", payload, signal);
  },

  async optimizeSelectedModules(payload, signal) {
    return apiPost("/optimize-selected-modules", payload, signal);
  },

  async suggestEmptySpace(payload, signal) {
    return apiPost("/suggest-empty-space", payload, signal);
  },

  async commitBlockStudio(payload, signal) {
    return apiPost("/commit-block-studio", payload, signal);
  },

  async addModule(payload, signal) {
    return apiPost("/add-module", payload, signal);
  },

  async addShelf(payload, signal) {
    return apiPost("/add-shelf", payload, signal);
  },

  async updateShelfSize(payload, signal) {
    return apiPost("/update-shelf-size", payload, signal);
  },

  // ---------------------------------------------------------------
  // AUTH / STORES / LIBRARIES
  // ---------------------------------------------------------------

  async login(payload, signal) {
    const data = await apiPost("/auth/login", payload, signal);
    return rememberSession(data);
  },

  async logout() {
    forgetSession();
    return { success: true };
  },

  async currentUser(signal) {
    return apiGet("/auth/me", signal);
  },

  async register(payload, signal) {
    return apiPost("/auth/register", payload, signal);
  },

  async getStores() {
    try {
      return await apiGet("/auth/stores");
    } catch (error) {
      console.warn("getStores fallback:", error?.message || error);
      return {
        stores: [
          { store_code: "ACIBADEM", code: "ACIBADEM", name: "Anka (İstanbul)", dmart: "Anka (İstanbul)", city: "İstanbul", region: "İstanbul-Avrupa" },
          { store_code: "GUVEN_FR", code: "GUVEN_FR", name: "Güven (Kocaeli) FR", dmart: "Güven (Kocaeli) FR", city: "Kocaeli", region: "Körfez" },
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

  // ---------------------------------------------------------------
  // OPTIONAL PERSISTENCE / BOOTSTRAP
  // Bu endpointler backend'in DB katmani acik degilse bulunmayabilir.
  // App.jsx zaten hepsini try/catch ile sariyor ("DB kapaliysa local
  // state ile devam et"). Burada graceful fallback donduruyoruz ki
  // "api.X is not a function" hatasi UI'yi kirmasin.
  // ---------------------------------------------------------------

  async bootstrap(store, signal) {
    try {
      return await apiGet(`/bootstrap${buildQuery({ store })}`, signal);
    } catch (error) {
      console.warn("bootstrap unavailable:", error?.message || error);
      return { status: "unavailable" };
    }
  },

  async readiness(store, signal) {
    try {
      return await apiGet(`/readiness${buildQuery({ store })}`, signal);
    } catch (error) {
      console.warn("readiness unavailable:", error?.message || error);
      return null;
    }
  },

  async savePlanogram(store, payload, summary, note, signal) {
    try {
      return await apiPost("/save-planogram", { store, payload, summary, note }, signal);
    } catch (error) {
      console.warn("savePlanogram unavailable:", error?.message || error);
      return { status: "unavailable" };
    }
  },

  async saveLayout(store, payload, note, signal) {
    try {
      return await apiPost("/save-layout", { store, payload, note }, signal);
    } catch (error) {
      console.warn("saveLayout unavailable:", error?.message || error);
      return { status: "unavailable" };
    }
  },

  async createTask(payload, signal) {
    try {
      return await apiPost("/tasks", payload, signal);
    } catch (error) {
      console.warn("createTask unavailable:", error?.message || error);
      return { status: "unavailable" };
    }
  },

  async getBasketAffinity(skus, store, signal) {
    try {
      return await apiPost("/basket-affinity", { skus, store }, signal);
    } catch (error) {
      console.warn("getBasketAffinity unavailable:", error?.message || error);
      return { affinity_map: {} };
    }
  },
};

export default api;

// ---- Plonagram compatibility API methods ----
api.catalogStatus = api.catalogStatus || function catalogStatus(storeCode = "AUTO", signal) {
  return request(`/catalog/status?store_code=${encodeURIComponent(storeCode || "AUTO")}`, { signal });
};

api.latestAbc = api.latestAbc || function latestAbc(storeCode = "AUTO", signal) {
  return request(`/abc/${encodeURIComponent(storeCode || "AUTO")}/latest`, { signal });
};

api.uploadCatalog = api.uploadCatalog || function uploadCatalog(storeCode = "AUTO", file, signal) {
  const form = new FormData();
  form.append("file", file);
  return request(`/catalog/upload?store_code=${encodeURIComponent(storeCode || "AUTO")}`, {
    method: "POST",
    body: form,
    signal
  });
};

api.uploadAbc = api.uploadAbc || function uploadAbc(storeCode = "AUTO", file, signal) {
  const form = new FormData();
  form.append("file", file);
  return request(`/abc/upload?store_code=${encodeURIComponent(storeCode || "AUTO")}`, {
    method: "POST",
    body: form,
    signal
  });
};

api.productLibrary = api.productLibrary || function productLibrary(limit = 500, offset = 0, signal) {
  return request(`/master-products?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`, { signal });
};

api.searchProductLibrary = api.searchProductLibrary || function searchProductLibrary(q = "", signal) {
  return request(`/master-products/search?q=${encodeURIComponent(q || "")}`, { signal });
};
// ---- /Plonagram compatibility API methods ----

// ---- Plonagram Store DNA compatibility overrides ----
api.generateStoreDnaEasy = async function generateStoreDnaEasy(payload = {}, signal) {
  const body = payload || {};
  const storeCode =
    body.store_code ||
    body.storeCode ||
    body.depot_code ||
    body.depotCode ||
    body.depot_name ||
    body.depotName ||
    "AUTO";

  try {
    return await request("/store-dna/generate-easy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal
    });
  } catch (err1) {
    try {
      const layout = await request("/default-layout", { signal });
      return {
        status: "success",
        source: "frontend_default_layout_fallback",
        store_code: storeCode,
        store_dna: body,
        layout,
        planogram: layout
      };
    } catch (err2) {
      const fallbackLayout = {
        store_code: storeCode,
        route_strategy: "LOCAL_STORE_DNA_FALLBACK",
        aisles: []
      };

      return {
        status: "success",
        source: "frontend_local_fallback",
        store_code: storeCode,
        store_dna: body,
        layout: fallbackLayout,
        planogram: fallbackLayout
      };
    }
  }
};

api.catalogStatus = async function catalogStatus(storeCode = "AUTO", signal) {
  try {
    return await request(`/catalog/status?store_code=${encodeURIComponent(storeCode || "AUTO")}`, { signal });
  } catch (err) {
    return {
      status: "missing",
      store_code: storeCode || "AUTO",
      catalog_loaded: false,
      row_count: 0,
      message: "catalog_status_endpoint_missing"
    };
  }
};

api.latestAbc = async function latestAbc(storeCode = "AUTO", signal) {
  try {
    return await request(`/abc/${encodeURIComponent(storeCode || "AUTO")}/latest`, { signal });
  } catch (err) {
    return {
      status: "missing",
      store_code: storeCode || "AUTO",
      abc_loaded: false,
      row_count: 0,
      message: "abc_latest_endpoint_missing"
    };
  }
};
// ---- /Plonagram Store DNA compatibility overrides ----
