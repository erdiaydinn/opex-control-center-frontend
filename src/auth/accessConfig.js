const ACCESS_STORAGE_KEY = "opex_access_config_v2";
const LEGACY_ACCESS_STORAGE_KEY = "opex_access_config_v1";
const SESSION_STORAGE_KEY = "opex_current_user";

export const ACCESS_MODULES = [
  {
    key: "planogram",
    title: "Planogram Studio",
    description: "Raf, fixture, facing ve planogram operasyonu",
  },
  {
    key: "dockos",
    title: "DockOS",
    description: "Sevkiyat, randevu, PO ve depo kabul kontrolü",
  },
  {
    key: "budget",
    title: "Budget Control",
    description: "PR, PO, fatura ve bütçe görünürlüğü",
  },
  {
    key: "academy",
    title: "OPEX Academy",
    description: "SOP, eğitim ve bilgi merkezi",
  },
  {
    key: "insight",
    title: "AI Insight Base",
    description: "Operasyon içgörüsü ve aksiyon önerileri",
  },
  {
    key: "cycle_count",
    title: "Cycle Count Risk",
    description: "Sayım riski, batch kontrolü ve stok doğruluğu",
  },
  {
    key: "admin_access",
    title: "Access Control",
    description: "Kullanıcı, grup ve modül erişim yönetimi",
  },
];

export const MODULE_DETAIL_CONFIG = {
  dockos: {
    title: "DockOS Detay Yetkileri",
    features: [
      { key: "dashboard", label: "Dashboard", description: "Genel DockOS özet ekranı" },
      { key: "livePurchaseOrders", label: "Canlı PO", description: "Canlı purchase order ekranı" },
      { key: "supplierAppointments", label: "Tedarikçi Randevu", description: "Tedarikçi randevu akışı" },
      { key: "shipmentDetails", label: "Sevkiyat Detayları", description: "Sevkiyat detay ve zorunlu alanları" },
      { key: "vehicleTracking", label: "Araç / Plaka Takibi", description: "Araç ve plaka alanları" },
      { key: "excelUpload", label: "Excel Upload", description: "Muhasebe / operasyon excel yükleme" },
      { key: "duplicateResolution", label: "Duplicate Karar", description: "Farklı tutarlı duplicate kayıt kararı" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "approve", label: "Onayla" },
      { key: "export", label: "Export" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
        { key: "supplier", label: "Tedarikçi bazlı" },
      ],
    },
  },
  planogram: {
    title: "Planogram Detay Yetkileri",
    features: [
      { key: "layoutView", label: "Layout Görüntüle", description: "Planogram layout ekranını görür" },
      { key: "layoutEdit", label: "Layout Düzenle", description: "Layout üzerinde değişiklik yapar" },
      { key: "fixtureEdit", label: "Fixture Düzenle", description: "Raf, dolap, fixture düzenler" },
      { key: "ruleEdit", label: "Kural Düzenle", description: "Kategori / marka / raf kurallarını yönetir" },
      { key: "productAssign", label: "Ürün Atama", description: "Ürünleri raflara atar" },
      { key: "aiRecommend", label: "AI Öneri", description: "AI planogram önerilerini kullanır" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "approve", label: "Onayla" },
      { key: "export", label: "Export" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
      ],
    },
  },
  budget: {
    title: "Budget Detay Yetkileri",
    features: [
      { key: "dashboard", label: "Dashboard", description: "Bütçe özet ekranı" },
      { key: "purchaseRequests", label: "PR Görünümü", description: "Purchase request kayıtları" },
      { key: "purchaseOrders", label: "PO Görünümü", description: "Purchase order kayıtları" },
      { key: "invoiceTracking", label: "Fatura Takibi", description: "Fatura ve ödeme takip alanı" },
      { key: "costCenter", label: "Cost Center", description: "Maliyet merkezi görünürlüğü" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "approve", label: "Onayla" },
      { key: "export", label: "Export" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
        { key: "cost_center", label: "Cost Center bazlı" },
      ],
    },
  },
};

export const SCOPE_OPTIONS = {
  regions: [
    "Marmara",
    "İç Anadolu",
    "Ege",
    "Akdeniz",
    "Karadeniz",
    "Doğu Anadolu",
    "Güneydoğu Anadolu",
  ],
  warehouses: [
    "Fulya (İstanbul)",
    "Çeliktepe (İstanbul)",
    "Aydınlı (İstanbul) FR",
    "Anka (İstanbul)",
    "Bağcılar Sancak (İstanbul)",
    "Pamukkale (Denizli)",
    "Şükrüpaşa (Edirne)",
    "İsmetpaşa (Çanakkale)",
    "Bostancı (İstanbul)",
    "Göktürk (İstanbul)",
    "Kozyatağı (İstanbul)",
    "Göztepe (İstanbul)",
  ],
  suppliers: [
    "Tedarikçi A",
    "Tedarikçi B",
    "Tedarikçi C",
    "Everyday Roastery",
    "Yerel Üretici",
  ],
  costCenters: [
    "OPEX",
    "DMart Operations",
    "Inbound",
    "Finance Ops",
    "Store Excellence",
  ],
};

function safeJsonParse(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function createDetailAccess(moduleKey, level = "none") {
  const detailConfig = MODULE_DETAIL_CONFIG[moduleKey];

  if (!detailConfig) {
    return {
      features: {},
      actions: {},
      scope: {
        type: "all",
        regions: [],
        warehouses: [],
        suppliers: [],
        costCenters: [],
      },
    };
  }

  const full = level === "admin" || level === "super";
  const viewOnly = level === "view";

  const features = detailConfig.features.reduce((acc, feature) => {
    acc[feature.key] = full || viewOnly;
    return acc;
  }, {});

  const actions = detailConfig.actions.reduce((acc, action) => {
    if (level === "super" || level === "admin") {
      acc[action.key] = true;
    } else if (level === "view") {
      acc[action.key] = action.key === "view" || action.key === "export";
    } else {
      acc[action.key] = false;
    }

    return acc;
  }, {});

  return {
    features,
    actions,
    scope: {
      type: "all",
      regions: [],
      warehouses: [],
      suppliers: [],
      costCenters: [],
    },
  };
}

function createModuleAccess(moduleKey, level = "none") {
  const view = level === "view" || level === "admin" || level === "super";
  const admin = level === "admin" || level === "super";

  return {
    view,
    admin,
    details: createDetailAccess(moduleKey, level),
  };
}

function createModulesForLevel(levelByModule = {}) {
  return ACCESS_MODULES.reduce((acc, module) => {
    acc[module.key] = createModuleAccess(module.key, levelByModule[module.key] || "none");
    return acc;
  }, {});
}

export const DEFAULT_ACCESS_CONFIG = {
  users: {
    "erdi.aydin@yemeksepeti.com": {
      email: "erdi.aydin@yemeksepeti.com",
      name: "Erdi Aydın",
      role: "super_admin",
      status: "active",
      modules: createModulesForLevel({
        planogram: "super",
        dockos: "super",
        budget: "super",
        academy: "super",
        insight: "super",
        cycle_count: "super",
        admin_access: "super",
      }),
    },
    "admin@yemeksepeti.com": {
      email: "admin@yemeksepeti.com",
      name: "Admin User",
      role: "admin",
      status: "active",
      modules: createModulesForLevel({
        planogram: "admin",
        dockos: "admin",
        budget: "admin",
        academy: "none",
        insight: "none",
        cycle_count: "none",
        admin_access: "none",
      }),
    },
    "viewer@yemeksepeti.com": {
      email: "viewer@yemeksepeti.com",
      name: "Viewer User",
      role: "viewer",
      status: "active",
      modules: createModulesForLevel({
        planogram: "view",
        dockos: "view",
        budget: "none",
        academy: "none",
        insight: "none",
        cycle_count: "none",
        admin_access: "none",
      }),
    },
    "noaccess@yemeksepeti.com": {
      email: "noaccess@yemeksepeti.com",
      name: "No Access User",
      role: "viewer",
      status: "active",
      modules: createModulesForLevel({}),
    },
  },
};

function normalizeModuleAccess(moduleKey, access = {}) {
  const base = createModuleAccess(moduleKey, "none");

  return {
    ...base,
    ...access,
    view: Boolean(access.view),
    admin: Boolean(access.admin),
    details: {
      ...base.details,
      ...(access.details || {}),
      features: {
        ...(base.details.features || {}),
        ...(access.details?.features || {}),
      },
      actions: {
        ...(base.details.actions || {}),
        ...(access.details?.actions || {}),
      },
      scope: {
        ...(base.details.scope || {}),
        ...(access.details?.scope || {}),
      },
    },
  };
}

function normalizeUser(email, user = {}) {
  const cleanEmail = normalizeEmail(email || user.email);
  const existingDefault = DEFAULT_ACCESS_CONFIG.users[cleanEmail];

  const normalized = {
    email: cleanEmail,
    name: user.name || existingDefault?.name || cleanEmail,
    role: user.role || existingDefault?.role || "viewer",
    status: user.status || existingDefault?.status || "active",
    modules: {},
  };

  ACCESS_MODULES.forEach((module) => {
    normalized.modules[module.key] = normalizeModuleAccess(
      module.key,
      user.modules?.[module.key] || existingDefault?.modules?.[module.key] || {}
    );

    if (normalized.role === "super_admin") {
      normalized.modules[module.key] = createModuleAccess(module.key, "super");
    }
  });

  return normalized;
}

export function getAccessConfig() {
  if (typeof window === "undefined") return clone(DEFAULT_ACCESS_CONFIG);

  const storedV2 = window.localStorage.getItem(ACCESS_STORAGE_KEY);
  const storedV1 = window.localStorage.getItem(LEGACY_ACCESS_STORAGE_KEY);
  const stored = storedV2 || storedV1;

  const parsed = stored ? safeJsonParse(stored, null) : null;

  if (!parsed || !parsed.users) {
    window.localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(DEFAULT_ACCESS_CONFIG));
    return clone(DEFAULT_ACCESS_CONFIG);
  }

  const merged = clone(DEFAULT_ACCESS_CONFIG);

  Object.entries(parsed.users || {}).forEach(([email, accessUser]) => {
    const cleanEmail = normalizeEmail(email);
    merged.users[cleanEmail] = normalizeUser(cleanEmail, accessUser);
  });

  window.localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(merged));
  return merged;
}

export function saveAccessConfig(config) {
  if (typeof window === "undefined") return;

  const normalized = {
    users: Object.entries(config.users || {}).reduce((acc, [email, accessUser]) => {
      const cleanEmail = normalizeEmail(email);
      acc[cleanEmail] = normalizeUser(cleanEmail, accessUser);
      return acc;
    }, {}),
  };

  window.localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent("opex-access-config-updated", { detail: normalized }));
}

export function getSessionUser() {
  if (typeof window === "undefined") return null;
  return safeJsonParse(window.localStorage.getItem(SESSION_STORAGE_KEY), null);
}

export function saveSessionUser(user) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(user));
}

export function clearSessionUser() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

export function buildUserFromEmail(email) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();

  if (!cleanEmail) return null;

  const existing = config.users[cleanEmail];

  if (existing) {
    return {
      email: cleanEmail,
      name: existing.name || cleanEmail,
      role: existing.role || "viewer",
      status: existing.status || "active",
    };
  }

  return {
    email: cleanEmail,
    name: cleanEmail,
    role: "viewer",
    status: "active",
  };
}

export function getUserPermissions(email) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return {};

  if (accessUser.role === "super_admin") {
    return createModulesForLevel(
      ACCESS_MODULES.reduce((acc, module) => {
        acc[module.key] = "super";
        return acc;
      }, {})
    );
  }

  return accessUser.modules || {};
}

export function canUser(email, moduleKey, action = "view") {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = accessUser.modules?.[moduleKey];

  if (action === "admin") return Boolean(moduleAccess?.admin);
  return Boolean(moduleAccess?.view);
}

export function canUserFeature(email, moduleKey, featureKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = accessUser.modules?.[moduleKey];
  if (!moduleAccess?.view) return false;

  return Boolean(moduleAccess?.details?.features?.[featureKey]);
}

export function canUserAction(email, moduleKey, actionKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = accessUser.modules?.[moduleKey];
  if (!moduleAccess?.view) return false;

  return Boolean(moduleAccess?.details?.actions?.[actionKey]);
}

export function getUserModuleScope(email, moduleKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") {
    return {
      type: "none",
      regions: [],
      warehouses: [],
      suppliers: [],
      costCenters: [],
    };
  }

  if (accessUser.role === "super_admin") {
    return {
      type: "all",
      regions: [],
      warehouses: [],
      suppliers: [],
      costCenters: [],
    };
  }

  return accessUser.modules?.[moduleKey]?.details?.scope || {
    type: "all",
    regions: [],
    warehouses: [],
    suppliers: [],
    costCenters: [],
  };
}

export function isUserSuperAdmin(email) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  return config.users[cleanEmail]?.role === "super_admin";
}
