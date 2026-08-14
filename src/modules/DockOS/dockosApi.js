import {
  apiFetch as authenticatedApiFetch,
} from "../../api/client.js";

import {
  filterRowsByDockOSScope,
} from "./dockosPermissions.js";


const REQUEST_TIMEOUT_MS = 15000;


// Scope is never sent by the browser as authorization input.
// Backend must derive scope from authenticated principal / DB / RLS.
function appendScopeParams(params) {
  return params;
}


async function apiFetch(path, options = {}) {
  const controller =
    new AbortController();

  const timeout = window.setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MS
  );

  try {
    return await authenticatedApiFetch(
      path,
      {
        ...options,
        signal: controller.signal,
      }
    );
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(
        "DockOS API iste?i zaman a??m?na u?rad?."
      );
    }

    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function normalizeRows(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.rows)
      ? payload.rows
      : Array.isArray(payload?.data)
        ? payload.data
        : [];

  return filterRowsByDockOSScope(rows);
}

export async function healthCheck() {
  return apiFetch("/dockos/health");
}

export async function getPurchaseOrders(supplierName = "", warehouseName = "") {
  const params = new URLSearchParams();
  if (supplierName) params.set("supplier_name", supplierName);
  if (warehouseName) params.set("warehouse_name", warehouseName);
  appendScopeParams(params);
  return normalizeRows(await apiFetch(`/dockos/live-purchase-orders?${params.toString()}`));
}

export async function importPurchaseOrders(payload) {
  return apiFetch("/dockos/purchase-orders/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getSlots(input = {}) {
  const params = new URLSearchParams();
  if (typeof input === "string") {
    if (input) params.set("warehouse_name", input);
  } else {
    Object.entries(input || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim()) {
        params.set(key, value);
      }
    });
  }
  appendScopeParams(params);
  return normalizeRows(await apiFetch(`/dockos/slots?${params.toString()}`));
}

export async function bulkUpdateCapacity(payload) {
  return apiFetch("/dockos/slots/capacity/bulk", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function blockSlotDates(payload) {
  return apiFetch("/dockos/slots/capacity/block-dates", { method: "POST", body: JSON.stringify(payload) });
}

export async function editSlotCapacity(payload) {
  return apiFetch("/dockos/slots/capacity/edit", { method: "PUT", body: JSON.stringify(payload) });
}

export async function deleteSlotCapacity({ warehouse_name, date, slot }) {
  const params = new URLSearchParams({ warehouse_name, date, slot });
  return apiFetch(`/dockos/slots/capacity?${params.toString()}`, { method: "DELETE" });
}

export async function getSupplierCapacity(input = {}) {
  const params = new URLSearchParams();
  Object.entries(input || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) params.set(key, value);
  });
  return normalizeRows(await apiFetch(`/dockos/supplier-capacity?${params.toString()}`));
}

export async function getSupplierDailyLimits(input = {}) {
  const params = new URLSearchParams();
  Object.entries(input || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) params.set(key, value);
  });
  return normalizeRows(await apiFetch(`/dockos/supplier-daily-limits?${params.toString()}`));
}

export async function updateSupplierDailyLimit(payload) {
  return apiFetch("/dockos/supplier-daily-limits", { method: "PUT", body: JSON.stringify(payload) });
}

export async function bulkUpdateSupplierCapacity(payload) {
  return apiFetch("/dockos/supplier-capacity/bulk", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function bulkUpdateSupplierCapacityMatrix(payload) {
  return apiFetch("/dockos/supplier-capacity/matrix", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function createReservation(payload) {
  return apiFetch("/dockos/reservations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getReservations(input = {}) {
  const params = new URLSearchParams();
  Object.entries(input || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) {
      params.set(key, value);
    }
  });
  appendScopeParams(params);
  return normalizeRows(await apiFetch(`/dockos/reservations?${params.toString()}`));
}

export async function updateReservationArrival(reservationNo, payload) {
  return apiFetch(`/dockos/reservations/${encodeURIComponent(reservationNo)}/arrival-check`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function cancelReservation(reservationNo, adminOverride = false, reason = "") {
  return apiFetch(
    `/dockos/reservations/${encodeURIComponent(reservationNo)}/cancel?admin_override=${adminOverride}&reason=${encodeURIComponent(reason)}`,
    { method: "POST" },
  );
}

export async function editReservationAdmin(reservationNo, payload) {
  return apiFetch(`/dockos/reservations/${encodeURIComponent(reservationNo)}/admin-edit`, { method: "PUT", body: JSON.stringify(payload) });
}

export async function updateReservationStatus(reservationNo, payload) {
  return apiFetch(`/dockos/reservations/${encodeURIComponent(reservationNo)}/status`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getAuditLog(limit = 200) {
  return normalizeRows(await apiFetch(`/dockos/audit-log?limit=${encodeURIComponent(limit)}`));
}

export async function askAnalytics(question, filters = {}) {
  return apiFetch("/dockos/analytics/ask", {
    method: "POST",
    body: JSON.stringify({ question, filters }),
  });
}

export async function executeAdminCommand(payload) {
  return apiFetch("/dockos/admin/command/execute", { method: "POST", body: JSON.stringify(payload) });
}

export async function getNotificationOutbox(limit = 200) {
  return normalizeRows(await apiFetch(`/dockos/notifications/outbox?limit=${encodeURIComponent(limit)}`));
}

export async function processDueNotifications() {
  return apiFetch("/dockos/notifications/process-due", { method: "POST" });
}

export async function getWarehouses(supplierName = "") {
  const params = new URLSearchParams();
  if (supplierName) params.set("supplier_name", supplierName);
  return normalizeRows(await apiFetch(`/dockos/warehouses?${params.toString()}`));
}

export async function getMySuppliers() { return normalizeRows(await apiFetch("/dockos/my-suppliers")); }

export async function getSupplierAccessMappings() { return normalizeRows(await apiFetch("/dockos/supplier-access")); }
export async function saveSupplierAccessMapping(payload) { return apiFetch("/dockos/supplier-access", { method: "PUT", body: JSON.stringify(payload) }); }
export async function deleteSupplierAccessMapping(email) { return apiFetch(`/dockos/supplier-access/${encodeURIComponent(email)}`, { method: "DELETE" }); }

export async function createManualPurchaseOrder(payload) { return apiFetch("/dockos/purchase-orders/manual", {method:"POST", body:JSON.stringify(payload)}); }

export async function getKpis(input={}) { const p=new URLSearchParams(); Object.entries(input).forEach(([k,v])=>{if(v)p.set(k,v)}); return apiFetch(`/dockos/kpis?${p}`); }

export async function getSuppliers() {
  return normalizeRows(await apiFetch("/dockos/suppliers"));
}

export async function getSettings() {
  return apiFetch("/dockos/settings");
}

export async function updateSettings(payload) {
  return apiFetch("/dockos/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
