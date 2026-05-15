import {
  canUserFeature,
  getSessionUser,
} from "../../auth/accessConfig.js";
import { filterRowsByDockOSScope, getDockOSScope } from "./dockosPermissions.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

function appendScopeParams(params) {
  const scope = getDockOSScope();

  if (!scope || scope.type === "all") {
    params.set("scope_type", "all");
    return params;
  }

  params.set("scope_type", scope.type || "none");

  if (scope.type === "warehouse") {
    (scope.warehouses || []).forEach((warehouse) => params.append("warehouses", warehouse));
  }

  if (scope.type === "supplier") {
    (scope.suppliers || []).forEach((supplier) => params.append("suppliers", supplier));
  }

  if (scope.type === "region") {
    (scope.regions || []).forEach((region) => params.append("regions", region));
  }

  return params;
}

function normalizeApiPayload(payload) {
  if (Array.isArray(payload)) {
    return filterRowsByDockOSScope(payload);
  }

  if (payload && Array.isArray(payload.rows)) {
    return {
      ...payload,
      rows: filterRowsByDockOSScope(payload.rows),
    };
  }

  if (payload && Array.isArray(payload.data)) {
    return {
      ...payload,
      data: filterRowsByDockOSScope(payload.data),
    };
  }

  return payload;
}

export async function getPurchaseOrders(supplierName = "", warehouseName = "") {
  const sessionUser = getSessionUser();

  if (!sessionUser?.email) {
    throw new Error("Oturum bulunamadı.");
  }

  if (!canUserFeature(sessionUser.email, "dockos", "livePurchaseOrders")) {
    return [];
  }

  const params = new URLSearchParams();

  if (supplierName) params.set("supplier_name", supplierName);
  if (warehouseName) params.set("warehouse_name", warehouseName);

  appendScopeParams(params);

  try {
    const res = await fetch(
      `${API_BASE}/dockos/live-purchase-orders?${params.toString()}`
    );

    if (!res.ok) throw new Error("Canlı PO alınamadı");

    const payload = await res.json();
    return normalizeApiPayload(payload);
  } catch (err) {
    console.error("DockOS API error:", err);
    throw err;
  }
}

export async function createReservation(payload = {}) {
  const sessionUser = getSessionUser();

  if (!sessionUser?.email) {
    throw new Error("Oturum bulunamadı.");
  }

  if (!canUserFeature(sessionUser.email, "dockos", "supplierAppointments")) {
    throw new Error("Tedarikçi randevu oluşturma yetkiniz yok.");
  }

  const res = await fetch(`${API_BASE}/dockos/reservations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-OPEX-User": sessionUser.email,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error("Randevu oluşturulamadı.");
  }

  return res.json();
}

export async function getReservations(paramsInput = {}) {
  const sessionUser = getSessionUser();

  if (!sessionUser?.email) {
    throw new Error("Oturum bulunamadı.");
  }

  if (!canUserFeature(sessionUser.email, "dockos", "supplierAppointments")) {
    return [];
  }

  const params = new URLSearchParams();

  Object.entries(paramsInput || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, value);
    }
  });

  appendScopeParams(params);

  const res = await fetch(`${API_BASE}/dockos/reservations?${params.toString()}`);

  if (!res.ok) {
    throw new Error("Randevu listesi alınamadı.");
  }

  const payload = await res.json();
  return normalizeApiPayload(payload);
}

export async function updateReservation(id, payload = {}) {
  const sessionUser = getSessionUser();

  if (!sessionUser?.email) {
    throw new Error("Oturum bulunamadı.");
  }

  if (!canUserAction(sessionUser.email, "dockos", "edit")) {
    throw new Error("Randevu düzenleme yetkiniz yok.");
  }

  const res = await fetch(`${API_BASE}/dockos/reservations/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-OPEX-User": sessionUser.email,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error("Randevu güncellenemedi.");
  }

  return res.json();
}

export async function deleteReservation(id) {
  const sessionUser = getSessionUser();

  if (!sessionUser?.email) {
    throw new Error("Oturum bulunamadı.");
  }

  if (!canUserAction(sessionUser.email, "dockos", "delete")) {
    throw new Error("Randevu silme yetkiniz yok.");
  }

  const res = await fetch(`${API_BASE}/dockos/reservations/${id}`, {
    method: "DELETE",
    headers: {
      "X-OPEX-User": sessionUser.email,
    },
  });

  if (!res.ok) {
    throw new Error("Randevu silinemedi.");
  }

  return true;
}

export async function getSlots(paramsInput = {}) {
  const sessionUser = getSessionUser();

  if (!sessionUser?.email) {
    throw new Error("Oturum bulunamadı.");
  }

  if (!canUserFeature(sessionUser.email, "dockos", "supplierAppointments")) {
    return [];
  }

  const params = new URLSearchParams();

  Object.entries(paramsInput || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, value);
    }
  });

  appendScopeParams(params);

  const res = await fetch(`${API_BASE}/dockos/slots?${params.toString()}`, {
    headers: {
      "X-OPEX-User": sessionUser.email,
    },
  });

  if (!res.ok) {
    throw new Error("Slot listesi alınamadı.");
  }

  const payload = await res.json();
  return normalizeApiPayload(payload);
}

export async function getWarehouses() {
  const res = await fetch(`${API_BASE}/dockos/warehouses`);

  if (!res.ok) {
    throw new Error("Depo listesi alınamadı.");
  }

  const payload = await res.json();
  return normalizeApiPayload(payload);
}

export async function getSuppliers() {
  const res = await fetch(`${API_BASE}/dockos/suppliers`);

  if (!res.ok) {
    throw new Error("Tedarikçi listesi alınamadı.");
  }

  const payload = await res.json();
  return normalizeApiPayload(payload);
}

export async function updateReservationArrival(reservationNo, arrivalCheck) {
  const saved = localStorage.getItem("dockos_reservations");
  const reservations = saved ? JSON.parse(saved) : [];

  const updated = reservations.map((reservation) =>
    reservation.reservation_no === reservationNo
      ? {
          ...reservation,
          dc_task_status: "ARRIVAL_CHECK_COMPLETED",
          arrival_check: arrivalCheck,
        }
      : reservation
  );

  localStorage.setItem("dockos_reservations", JSON.stringify(updated));

  return {
    reservation_no: reservationNo,
    status: "UPDATED",
    message: "Merkez depo kontrolü kaydedildi.",
  };
}

export async function cancelReservation(reservationNo) {
  const saved = localStorage.getItem("dockos_reservations");
  const reservations = saved ? JSON.parse(saved) : [];

  const updated = reservations.map((reservation) =>
    reservation.reservation_no === reservationNo
      ? {
          ...reservation,
          status: "CANCELLED",
        }
      : reservation
  );

  localStorage.setItem("dockos_reservations", JSON.stringify(updated));

  return {
    reservation_no: reservationNo,
    status: "CANCELLED",
    message: "Rezervasyon iptal edildi.",
  };
}
