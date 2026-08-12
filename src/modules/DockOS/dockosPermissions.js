import {
  getAuthorizationSnapshot,
} from "../../auth/authorizationStore.js";


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


function emptyScope() {
  return {
    type: "none",
    regions: [],
    warehouses: [],
    suppliers: [],
    costCenters: [],
  };
}


function hasPermission(permissionKey) {
  const snapshot =
    getAuthorizationSnapshot();

  return snapshot.permissions.includes(
    permissionKey
  );
}


export function getCurrentDockOSUser() {
  return (
    getAuthorizationSnapshot().user ||
    {}
  );
}


export function canDockOSFeature(featureKey) {
  if (
    !Object.values(DOCKOS_FEATURES).includes(
      featureKey
    )
  ) {
    return false;
  }

  return hasPermission(
    `feature:dockos:${featureKey}`
  );
}


export function canDockOSAction(actionKey) {
  if (
    !Object.values(DOCKOS_ACTIONS).includes(
      actionKey
    )
  ) {
    return false;
  }

  return hasPermission(
    `action:dockos:${actionKey}`
  );
}


export function getDockOSScope() {
  const snapshot =
    getAuthorizationSnapshot();

  const assignments =
    snapshot.permissionAssignments.filter(
      (item) =>
        snapshot.permissions.includes(
          item.key
        ) &&
        (
          item.key.startsWith(
            "module:dockos:"
          ) ||
          item.key.startsWith(
            "feature:dockos:"
          ) ||
          item.key.startsWith(
            "action:dockos:"
          )
        )
    );

  if (!assignments.length) {
    return emptyScope();
  }

  const result = emptyScope();

  for (const assignment of assignments) {
    const scope = assignment.scope || {};

    // Unrestricted scope must always be explicit.
    if (
      scope.type === "all" &&
      Object.keys(scope).every(
        (key) => key === "type"
      )
    ) {
      return {
        ...emptyScope(),
        type: "all",
      };
    }

    for (const field of [
      "regions",
      "warehouses",
      "suppliers",
      "costCenters",
    ]) {
      if (!Array.isArray(scope[field])) {
        continue;
      }

      for (const rawValue of scope[field]) {
        const value = String(
          rawValue || ""
        ).trim();

        if (
          value &&
          !result[field].includes(value)
        ) {
          result[field].push(value);
        }
      }
    }
  }

  const populated = [
    ["region", result.regions],
    ["warehouse", result.warehouses],
    ["supplier", result.suppliers],
    ["costCenter", result.costCenters],
  ].filter(([, values]) => values.length);

  if (populated.length === 1) {
    result.type = populated[0][0];
  } else if (populated.length > 1) {
    result.type = "compound";
  }

  return result;
}


export function getDockOSPermissionSnapshot() {
  const snapshot =
    getAuthorizationSnapshot();

  return {
    user: snapshot.user || {},
    features: Object.fromEntries(
      Object.values(DOCKOS_FEATURES).map(
        (feature) => [
          feature,
          canDockOSFeature(feature),
        ]
      )
    ),

    actions: Object.fromEntries(
      Object.values(DOCKOS_ACTIONS).map(
        (action) => [
          action,
          canDockOSAction(action),
        ]
      )
    ),

    scope: getDockOSScope(),
  };
}


function normalizeText(value) {
  return String(value || "")
    .trim()
    .toLocaleLowerCase("tr-TR")
    .replace(
      /^yemeksepeti market\s*[,;]?\s*/i,
      ""
    );
}


function valueFromAny(row, keys) {
  for (const key of keys) {
    if (
      row &&
      row[key] !== undefined &&
      row[key] !== null &&
      String(row[key]).trim() !== ""
    ) {
      return row[key];
    }
  }

  return "";
}


const ROW_SCOPE_FIELDS = {
  warehouses: [
    "warehouse_name",
    "dmart_warehouse_name",
    "dest_warehouse_name",
    "destination_warehouse_name",
    "store_name",
    "dmart",
    "detected_store",
  ],

  suppliers: [
    "supplier",
    "supplier_name",
    "vendor_name",
    "detected_supplier",
    "po_supplier",
  ],

  regions: [
    "region",
    "region_name",
    "area",
    "area_name",
    "zone",
  ],

  costCenters: [
    "cost_center",
    "costCenter",
    "cost_center_name",
  ],
};


export function filterRowsByDockOSScope(
  rows
) {
  if (!Array.isArray(rows)) {
    return [];
  }

  const scope = getDockOSScope();

  if (scope.type === "all") {
    return rows;
  }

  if (
    !scope ||
    scope.type === "none"
  ) {
    return [];
  }

  // Defense in depth only. Backend/RLS remains
  // authoritative for actual data isolation.
  return rows.filter((row) => {
    for (const [
      scopeField,
      rowKeys,
    ] of Object.entries(
      ROW_SCOPE_FIELDS
    )) {
      const allowed =
        Array.isArray(scope[scopeField])
          ? scope[scopeField]
          : [];

      if (!allowed.length) {
        continue;
      }

      const normalizedAllowed =
        new Set(
          allowed.map(normalizeText)
        );

      const actual = normalizeText(
        valueFromAny(row, rowKeys)
      );

      if (
        !actual ||
        !normalizedAllowed.has(actual)
      ) {
        return false;
      }
    }

    return true;
  });
}


export function getDockOSPermissionClassNames() {
  const snapshot =
    getDockOSPermissionSnapshot();

  const classNames = [];

  Object.entries(
    snapshot.features
  ).forEach(([key, value]) => {
    classNames.push(
      value
        ? `dockos-feature-${key}-on`
        : `dockos-feature-${key}-off`
    );
  });

  Object.entries(
    snapshot.actions
  ).forEach(([key, value]) => {
    classNames.push(
      value
        ? `dockos-action-${key}-on`
        : `dockos-action-${key}-off`
    );
  });

  classNames.push(
    `dockos-scope-${
      snapshot.scope?.type || "none"
    }`
  );

  return classNames.join(" ");
}
