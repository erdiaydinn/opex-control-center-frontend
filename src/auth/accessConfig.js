const ACCESS_STORAGE_KEY = "opex_access_config_v3";
const LEGACY_ACCESS_STORAGE_KEYS = [
  "opex_access_config_v2",
  "opex_access_config_v1",
];
const SESSION_STORAGE_KEY = "opex_current_user";

export const ACCESS_MODULES = [
  { key: "planogram", title: "Planogram Studio", description: "Raf, fixture, facing ve planogram operasyonu" },
  { key: "dockos", title: "DockOS", description: "Sevkiyat, randevu, PO ve depo kabul kontrolü" },
  { key: "budget", title: "Budget Control", description: "PR, PO, fatura ve bütçe görünürlüğü" },
  { key: "academy", title: "OPEX Academy", description: "SOP, eğitim ve bilgi merkezi" },
  { key: "insight", title: "AI Insight Base", description: "Operasyon içgörüsü ve aksiyon önerileri" },
  { key: "cycle_count", title: "Cycle Count Risk", description: "Sayım riski, batch kontrolü ve stok doğruluğu" },
  { key: "admin_access", title: "Access Control", description: "Kullanıcı, grup ve modül erişim yönetimi" },
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
  regions: ["Marmara", "İç Anadolu", "Ege", "Akdeniz", "Karadeniz", "Doğu Anadolu", "Güneydoğu Anadolu"],
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
  suppliers: ["Tedarikçi A", "Tedarikçi B", "Tedarikçi C", "Everyday Roastery", "Yerel Üretici"],
  costCenters: ["OPEX", "DMart Operations", "Inbound", "Finance Ops", "Store Excellence"],
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

function unique(values = []) {
  return [...new Set(values.filter(Boolean))];
}

function createDetailAccess(moduleKey, level = "none") {
  const detailConfig = MODULE_DETAIL_CONFIG[moduleKey];

  if (!detailConfig) {
    return {
      features: {},
      actions: {},
      scope: { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] },
    };
  }

  const full = level === "admin" || level === "super";
  const viewOnly = level === "view";

  return {
    features: detailConfig.features.reduce((acc, feature) => {
      acc[feature.key] = full || viewOnly;
      return acc;
    }, {}),
    actions: detailConfig.actions.reduce((acc, action) => {
      if (full) acc[action.key] = true;
      else if (viewOnly) acc[action.key] = action.key === "view" || action.key === "export";
      else acc[action.key] = false;
      return acc;
    }, {}),
    scope: { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] },
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
  groups: {
    super_admins: {
      id: "super_admins",
      name: "Super Admins",
      description: "Tüm modüller ve tüm yönetim alanları",
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
    dockos_admins: {
      id: "dockos_admins",
      name: "DockOS Admins",
      description: "DockOS yönetimi, PO, sevkiyat ve randevu operasyonları",
      status: "active",
      modules: createModulesForLevel({
        dockos: "admin",
      }),
    },
    construction_team: {
      id: "construction_team",
      name: "İnşaat Ekibi",
      description: "İnşaat, bakım, tadilat, saha geliştirme ve sevkiyat takip görünümü",
      status: "active",
      modules: createModulesForLevel({
        dockos: "view",
        budget: "view",
      }),
    },
    finance_team: {
      id: "finance_team",
      name: "Finans Ekibi",
      description: "Budget, PR, PO, fatura ve maliyet merkezi görünürlüğü",
      status: "active",
      modules: createModulesForLevel({
        budget: "admin",
        dockos: "view",
      }),
    },
    operation_leaders: {
      id: "operation_leaders",
      name: "Operasyon Liderleri",
      description: "Operasyon modüllerinde geniş görüntüleme ve export",
      status: "active",
      modules: createModulesForLevel({
        planogram: "view",
        dockos: "view",
        budget: "view",
        cycle_count: "view",
      }),
    },
    viewers: {
      id: "viewers",
      name: "Viewer",
      description: "Temel görüntüleme grubu",
      status: "active",
      modules: createModulesForLevel({
        planogram: "view",
        dockos: "view",
      }),
    },
  },
  users: {
    "erdi.aydin@yemeksepeti.com": {
      email: "erdi.aydin@yemeksepeti.com",
      name: "Erdi Aydın",
      role: "super_admin",
      status: "active",
      groups: ["super_admins"],
      modules: createModulesForLevel({}),
    },
    "admin@yemeksepeti.com": {
      email: "admin@yemeksepeti.com",
      name: "Admin User",
      role: "admin",
      status: "active",
      groups: ["dockos_admins"],
      modules: createModulesForLevel({
        planogram: "admin",
        budget: "admin",
      }),
    },
    "viewer@yemeksepeti.com": {
      email: "viewer@yemeksepeti.com",
      name: "Viewer User",
      role: "viewer",
      status: "active",
      groups: ["viewers"],
      modules: createModulesForLevel({}),
    },
    "noaccess@yemeksepeti.com": {
      email: "noaccess@yemeksepeti.com",
      name: "No Access User",
      role: "viewer",
      status: "active",
      groups: [],
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

function normalizeModules(modules = {}, role = "viewer") {
  return ACCESS_MODULES.reduce((acc, module) => {
    if (role === "super_admin") acc[module.key] = createModuleAccess(module.key, "super");
    else acc[module.key] = normalizeModuleAccess(module.key, modules[module.key] || {});
    return acc;
  }, {});
}

function normalizeUser(email, user = {}) {
  const cleanEmail = normalizeEmail(email || user.email);
  const existingDefault = DEFAULT_ACCESS_CONFIG.users[cleanEmail];

  const role = user.role || existingDefault?.role || "viewer";

  return {
    email: cleanEmail,
    name: user.name || existingDefault?.name || cleanEmail,
    role,
    status: user.status || existingDefault?.status || "active",
    groups: unique([...(existingDefault?.groups || []), ...(user.groups || [])]),
    modules: normalizeModules(user.modules || existingDefault?.modules || {}, role),
  };
}

function normalizeGroup(id, group = {}) {
  const groupId = String(id || group.id || "").trim();
  const existingDefault = DEFAULT_ACCESS_CONFIG.groups[groupId];

  return {
    id: groupId,
    name: group.name || existingDefault?.name || groupId,
    description: group.description || existingDefault?.description || "",
    status: group.status || existingDefault?.status || "active",
    modules: normalizeModules(group.modules || existingDefault?.modules || {}, "group"),
  };
}

function loadStoredConfig() {
  if (typeof window === "undefined") return null;

  const current = window.localStorage.getItem(ACCESS_STORAGE_KEY);
  if (current) return safeJsonParse(current, null);

  for (const key of LEGACY_ACCESS_STORAGE_KEYS) {
    const value = window.localStorage.getItem(key);
    if (value) return safeJsonParse(value, null);
  }

  return null;
}

export function getAccessConfig() {
  if (typeof window === "undefined") return clone(DEFAULT_ACCESS_CONFIG);

  const parsed = loadStoredConfig();

  if (!parsed || !parsed.users) {
    window.localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(DEFAULT_ACCESS_CONFIG));
    return clone(DEFAULT_ACCESS_CONFIG);
  }

  const merged = clone(DEFAULT_ACCESS_CONFIG);

  Object.entries(parsed.groups || {}).forEach(([id, group]) => {
    const groupId = String(id || group.id || "").trim();
    if (groupId) merged.groups[groupId] = normalizeGroup(groupId, group);
  });

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
    groups: Object.entries(config.groups || {}).reduce((acc, [id, group]) => {
      const groupId = String(id || group.id || "").trim();
      if (groupId) acc[groupId] = normalizeGroup(groupId, group);
      return acc;
    }, {}),
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

function mergeScope(currentScope, incomingScope) {
  const current = currentScope || { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  const incoming = incomingScope || { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };

  if (current.type === "all" || incoming.type === "all") {
    return { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  return {
    type: incoming.type !== "none" ? incoming.type : current.type,
    regions: unique([...(current.regions || []), ...(incoming.regions || [])]),
    warehouses: unique([...(current.warehouses || []), ...(incoming.warehouses || [])]),
    suppliers: unique([...(current.suppliers || []), ...(incoming.suppliers || [])]),
    costCenters: unique([...(current.costCenters || []), ...(incoming.costCenters || [])]),
  };
}

function mergeModuleAccess(moduleKey, list = []) {
  const base = createModuleAccess(moduleKey, "none");

  return list.reduce((acc, item) => {
    if (!item) return acc;

    const normalized = normalizeModuleAccess(moduleKey, item);

    return {
      view: acc.view || normalized.view,
      admin: acc.admin || normalized.admin,
      details: {
        features: Object.keys(base.details.features || {}).reduce((obj, key) => {
          obj[key] = Boolean(acc.details.features?.[key] || normalized.details.features?.[key]);
          return obj;
        }, {}),
        actions: Object.keys(base.details.actions || {}).reduce((obj, key) => {
          obj[key] = Boolean(acc.details.actions?.[key] || normalized.details.actions?.[key]);
          return obj;
        }, {}),
        scope: mergeScope(acc.details.scope, normalized.details.scope),
      },
    };
  }, base);
}

export function getEffectiveAccess(email) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") {
    return createModulesForLevel({});
  }

  if (accessUser.role === "super_admin") {
    return createModulesForLevel(
      ACCESS_MODULES.reduce((acc, module) => {
        acc[module.key] = "super";
        return acc;
      }, {})
    );
  }

  return ACCESS_MODULES.reduce((acc, module) => {
    const groupAccessList = (accessUser.groups || [])
      .map((groupId) => config.groups?.[groupId])
      .filter((group) => group && group.status === "active")
      .map((group) => group.modules?.[module.key]);

    acc[module.key] = mergeModuleAccess(module.key, [
      ...groupAccessList,
      accessUser.modules?.[module.key],
    ]);

    return acc;
  }, {});
}

export function getUserPermissions(email) {
  return getEffectiveAccess(email);
}

export function canUser(email, moduleKey, action = "view") {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = getEffectiveAccess(cleanEmail)?.[moduleKey];

  if (action === "admin") return Boolean(moduleAccess?.admin);
  return Boolean(moduleAccess?.view);
}

export function canUserFeature(email, moduleKey, featureKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = getEffectiveAccess(cleanEmail)?.[moduleKey];

  if (!moduleAccess?.view) return false;
  return Boolean(moduleAccess?.details?.features?.[featureKey]);
}

export function canUserAction(email, moduleKey, actionKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = getEffectiveAccess(cleanEmail)?.[moduleKey];

  if (!moduleAccess?.view) return false;
  return Boolean(moduleAccess?.details?.actions?.[actionKey]);
}

export function getUserModuleScope(email, moduleKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") {
    return { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  if (accessUser.role === "super_admin") {
    return { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  return getEffectiveAccess(cleanEmail)?.[moduleKey]?.details?.scope || {
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
