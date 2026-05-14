const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

export async function getPurchaseOrders(supplierName = "", warehouseName = "") {
  const params = new URLSearchParams();

  if (supplierName) params.append("supplier_name", supplierName);
  if (warehouseName) params.append("warehouse_name", warehouseName);

  try {
    const res = await fetch(
      `${API_BASE}/river/live-purchase-orders?${params.toString()}`
    );

    if (!res.ok) throw new Error("Canlı PO alınamadı");

    const data = await res.json();

    if (data?.rows) return data.rows;

    return [];
  } catch (err) {
    console.warn("Live PO fallback:", err);
    return [];
  }
}

export async function getSlots(warehouseName = "") {
  const saved = localStorage.getItem("dockos_capacity_rows");
  const rows = saved ? JSON.parse(saved) : [];

  return rows
    .filter((row) => row.warehouse === warehouseName)
    .map((row) => ({
      warehouse_name: row.warehouse,
      date: row.date,
      slot: row.hour,
      max_pallet: row.palletLimit,
      max_sku: row.skuLimit,
      remaining_pallet: row.palletLimit - row.usedPallet,
      remaining_sku: row.skuLimit - row.usedSku,
    }));
}

export async function getWarehouses() {
  return [
    { warehouse_name: "Ankara DC" },
    { warehouse_name: "İstanbul Avrupa DC" },
    { warehouse_name: "İstanbul Anadolu DC" },
    { warehouse_name: "İzmir DC" },
  ];
}

export async function createReservation(payload) {
  const savedReservations = localStorage.getItem("dockos_reservations");
  const reservations = savedReservations ? JSON.parse(savedReservations) : [];

  const reservationNo = `RVR-${Date.now()}`;

  const newReservation = {
    reservation_no: reservationNo,
    status: "APPROVED",
    message: "Rezervasyon başarıyla oluşturuldu.",
    created_at: new Date().toISOString(),
    dc_task_status: "WAITING_ARRIVAL_CHECK",
    arrival_check: {
      arrived: null,
      dock_compatible: null,
      on_time: null,
      note: "",
    },
    ...payload,
  };

  localStorage.setItem(
    "dockos_reservations",
    JSON.stringify([newReservation, ...reservations])
  );

  const savedCapacity = localStorage.getItem("dockos_capacity_rows");
  const rows = savedCapacity ? JSON.parse(savedCapacity) : [];

  const updatedRows = rows.map((row) => {
    const sameSlot =
      row.warehouse === payload.warehouse_name &&
      row.date === payload.slot_date &&
      row.hour === payload.selected_slot;

    if (!sameSlot) return row;

    return {
      ...row,
      usedPallet: Math.min(row.palletLimit, row.usedPallet + payload.pallet_count),
      usedSku: Math.min(row.skuLimit, row.usedSku + payload.sku_count),
    };
  });

  localStorage.setItem("dockos_capacity_rows", JSON.stringify(updatedRows));

  return {
    reservation_no: reservationNo,
    status: "APPROVED",
    message: "Rezervasyon başarıyla oluşturuldu.",
  };
}

export async function getReservations() {
  const saved = localStorage.getItem("dockos_reservations");
  return saved ? JSON.parse(saved) : [];
}

export async function cancelReservation(reservationNo) {
  const saved = localStorage.getItem("dockos_reservations");
  const reservations = saved ? JSON.parse(saved) : [];

  const updated = reservations.map((reservation) =>
    reservation.reservation_no === reservationNo
      ? { ...reservation, status: "CANCELLED" }
      : reservation
  );

  localStorage.setItem("dockos_reservations", JSON.stringify(updated));

  return {
    reservation_no: reservationNo,
    status: "CANCELLED",
    message: "Rezervasyon iptal edildi.",
  };
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

export async function updateSlotCapacity(payload) {
  return {
    status: "UPDATED",
    message: "Slot kapasitesi güncellendi.",
    payload,
  };
}