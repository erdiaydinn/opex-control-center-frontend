import {
  canUserAction,
  canUserFeature,
  getSessionUser,
  getUserModuleScope,
} from "../../auth/accessConfig.js";

export const DOCKOS_FEATURES = {
  dashboard: "dashboard",
  livePurchaseOrders: "livePurchaseOrders",
  supplierAppointments: "supplierAppointments",
  shipmentDetails: "shipmentDetails",
  vehicleTracking: "vehicleTracking",
  excelUpload: "excelUpload",
  duplicateResolution: "duplicateResolution",
};

export const DOCKOS_ACTIONS = {
  view: "view",
  create: "create",
  edit: "edit",
  approve: "approve",
  export: "export",
  delete: "delete",
};

const ADMIN_EMAILS = new Set([
  "erdi.aydin@yemeksepeti.com",
]);

function normalize(value) {
  return String(value || "").trim().toLocaleLowerCase("tr-TR");
}

export function getCurrentDockOSUser() {
  return getSessionUser() || {};
}

function isAdminUser(user) {
  const email = normalize(user?.email);
  const role = normalize(user?.role || user?.user_role || user?.title);
  const groups = (user?.groups || []).map(normalize);

  return (
    ADMIN_EMAILS.has(email) ||
    ["admin", "superadmin", "opex_admin", "dockos_admin"].includes(role) ||
    groups.some((group) => group.includes("admin") || group.includes("dockos"))
  );
}

function isSupplierUser(user) {
  const role = normalize(user?.role || user?.user_role || user?.title);
  return role.includes("supplier") || role.includes("tedarik");
}

function safeFeatureCheck(user, featureKey) {
  try {
    return Boolean(canUserFeature(user.email, "dockos", featureKey));
  } catch {
    return false;
  }
}

function safeActionCheck(user, actionKey) {
  try {
    return Boolean(canUserAction(user.email, "dockos", actionKey));
  } catch {
    return false;
  }
}

export function canDockOSFeature(featureKey) {
  const user = getCurrentDockOSUser();
  if (!user?.email) return false;

  if (safeFeatureCheck(user, featureKey)) return true;

  // Pilot fallback: Access Control kaydı henüz tamamlanmamış iç kullanıcılar.
  // Bu yalnızca görünürlük katmanıdır; backend yetkisi ayrıca uygulanmalıdır.
  if (isAdminUser(user)) return true;

  if (isSupplierUser(user)) {
    return [
      DOCKOS_FEATURES.dashboard,
      DOCKOS_FEATURES.livePurchaseOrders,
      DOCKOS_FEATURES.supplierAppointments,
      DOCKOS_FEATURES.shipmentDetails,
      DOCKOS_FEATURES.vehicleTracking,
    ].includes(featureKey);
  }

  return featureKey === DOCKOS_FEATURES.dashboard;
}

export function canDockOSAction(actionKey) {
  const user = getCurrentDockOSUser();
  if (!user?.email) return false;

  if (safeActionCheck(user, actionKey)) return true;
  if (isAdminUser(user)) return true;

  if (isSupplierUser(user)) {
    return [DOCKOS_ACTIONS.view, DOCKOS_ACTIONS.create, DOCKOS_ACTIONS.edit].includes(actionKey);
  }

  return actionKey === DOCKOS_ACTIONS.view;
}

export function getDockOSScope() {
  const user = getCurrentDockOSUser();

  if (!user?.email) {
    return { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  try {
    const scope = getUserModuleScope(user.email, "dockos");
    if (scope && scope.type && scope.type !== "none") return scope;
  } catch {
    // fallback below
  }

  if (isAdminUser(user)) {
    return { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  const warehouses = user?.warehouses || user?.warehouse_names || [];
  if (warehouses.length) {
    return { type: "warehouse", regions: [], warehouses, suppliers: [], costCenters: [] };
  }

  const suppliers = user?.suppliers || user?.supplier_names || [];
  if (suppliers.length) {
    return { type: "supplier", regions: [], warehouses: [], suppliers, costCenters: [] };
  }

  return { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };
}

export function getDockOSPermissionSnapshot() {
  const user = getCurrentDockOSUser();
  const scope = getDockOSScope();

  return {
    user,
    isAdmin: isAdminUser(user),
    features: Object.fromEntries(
      Object.values(DOCKOS_FEATURES).map((feature) => [feature, canDockOSFeature(feature)])
    ),
    actions: Object.fromEntries(
      Object.values(DOCKOS_ACTIONS).map((action) => [action, canDockOSAction(action)])
    ),
    scope,
  };
}

function normalizeText(value) {
  return String(value || "")
    .trim()
    .toLocaleLowerCase("tr-TR")
    .replace(/^yemeksepeti market\s*[,;]?\s*/i, "");
}

function valueFromAny(row, keys) {
  for (const key of keys) {
    if (row && row[key] !== undefined && row[key] !== null && String(row[key]).trim() !== "") {
      return row[key];
    }
  }
  return "";
}

export function filterRowsByDockOSScope(rows) {
  if (!Array.isArray(rows)) return [];
  const scope = getDockOSScope();

  if (!scope || scope.type === "all") return rows;
  if (scope.type === "none") return [];

  if (scope.type === "warehouse") {
    const allowed = new Set((scope.warehouses || []).map(normalizeText));
    return rows.filter((row) =>
      allowed.has(
        normalizeText(
          valueFromAny(row, [
            "warehouse_name",
            "dmart_warehouse_name",
            "dest_warehouse_name",
            "destination_warehouse_name",
            "store_name",
            "dmart",
            "detected_store",
          ])
        )
      )
    );
  }

  if (scope.type === "supplier") {
    const allowed = new Set((scope.suppliers || []).map(normalizeText));
    return rows.filter((row) =>
      allowed.has(
        normalizeText(
          valueFromAny(row, [
            "supplier",
            "supplier_name",
            "vendor_name",
            "detected_supplier",
            "po_supplier",
          ])
        )
      )
    );
  }

  if (scope.type === "region") {
    const allowed = new Set((scope.regions || []).map(normalizeText));
    return rows.filter((row) =>
      allowed.has(
        normalizeText(
          valueFromAny(row, ["region", "region_name", "area", "area_name", "zone"])
        )
      )
    );
  }

  return rows;
}

export function getDockOSPermissionClassNames() {
  const snapshot = getDockOSPermissionSnapshot();
  const classNames = [];

  Object.entries(snapshot.features).forEach(([key, value]) => {
    classNames.push(value ? `dockos-feature-${key}-on` : `dockos-feature-${key}-off`);
  });

  Object.entries(snapshot.actions).forEach(([key, value]) => {
    classNames.push(value ? `dockos-action-${key}-on` : `dockos-action-${key}-off`);
  });

  classNames.push(`dockos-scope-${snapshot.scope?.type || "none"}`);
  return classNames.join(" ");
}
