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

export function getCurrentDockOSUser() {
  return getSessionUser();
}

export function canDockOSFeature(featureKey) {
  const user = getCurrentDockOSUser();
  if (!user?.email) return false;
  return canUserFeature(user.email, "dockos", featureKey);
}

export function canDockOSAction(actionKey) {
  const user = getCurrentDockOSUser();
  if (!user?.email) return false;
  return canUserAction(user.email, "dockos", actionKey);
}

export function getDockOSScope() {
  const user = getCurrentDockOSUser();
  if (!user?.email) {
    return {
      type: "none",
      regions: [],
      warehouses: [],
      suppliers: [],
      costCenters: [],
    };
  }

  return getUserModuleScope(user.email, "dockos");
}

export function getDockOSPermissionSnapshot() {
  const scope = getDockOSScope();

  return {
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
  if (!Array.isArray(rows)) return rows;

  const scope = getDockOSScope();

  if (!scope || scope.type === "all") return rows;
  if (scope.type === "none") return [];

  if (scope.type === "warehouse") {
    const allowed = new Set((scope.warehouses || []).map(normalizeText));

    if (!allowed.size) return [];

    return rows.filter((row) => {
      const warehouse = normalizeText(
        valueFromAny(row, [
          "warehouse_name",
          "dmart_warehouse_name",
          "dest_warehouse_name",
          "destination_warehouse_name",
          "store_name",
          "dmart",
          "detected_store",
        ])
      );

      return allowed.has(warehouse);
    });
  }

  if (scope.type === "supplier") {
    const allowed = new Set((scope.suppliers || []).map(normalizeText));

    if (!allowed.size) return [];

    return rows.filter((row) => {
      const supplier = normalizeText(
        valueFromAny(row, [
          "supplier",
          "supplier_name",
          "vendor_name",
          "detected_supplier",
          "po_supplier",
        ])
      );

      return allowed.has(supplier);
    });
  }

  if (scope.type === "region") {
    const allowed = new Set((scope.regions || []).map(normalizeText));

    if (!allowed.size) return [];

    return rows.filter((row) => {
      const region = normalizeText(
        valueFromAny(row, [
          "region",
          "region_name",
          "area",
          "area_name",
          "zone",
        ])
      );

      return allowed.has(region);
    });
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
