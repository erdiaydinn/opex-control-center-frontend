import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "../../api/client.js";

const LOCAL_PILOT_MODE = String(import.meta.env.VITE_LOCAL_PILOT_MODE || "false").toLowerCase() === "true";
const PILOT_DEVICE_IDS = { "100184": "DEVICE-1", "100221": "DEV-4418", "100287": "DEV-7781" };

function camelKey(key) { return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()); }
function camel(value) {
  if (Array.isArray(value)) return value.map(camel);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [camelKey(key), camel(item)]));
  return value;
}

export async function loadMobileWorkforce(personId) {
  return camel(await apiGet(`/workforce/mobile/bootstrap?person_id=${encodeURIComponent(personId)}`));
}
export async function loadAdminWorkforce() { return camel(await apiGet("/workforce/admin/bootstrap")); }
export async function createShiftRemote(values) { return camel(await apiPost("/workforce/shifts", values)); }
export async function approveAttendanceRemote(id, note = "") { return camel(await apiPost(`/workforce/attendance/${encodeURIComponent(id)}/approve`, { note })); }
export async function bulkApproveRemote(ids, note = "") { return camel(await apiPost("/workforce/attendance/bulk-approve", { attendance_ids: ids, note })); }
export async function correctAttendanceRemote(id, values) { return camel(await apiPost(`/workforce/attendance/${encodeURIComponent(id)}/manual-correction`, values)); }
export async function resetDeviceRemote(personId, reason) { return camel(await apiPost(`/workforce/devices/${encodeURIComponent(personId)}/reset`, { reason })); }
export async function createRuleRemote(values) { return camel(await apiPost("/workforce/rules", values)); }
export async function createAnnouncementRemote(values) { return camel(await apiPost("/workforce/announcements", values)); }
export async function saveNotificationPolicyRemote(values) { return camel(await apiPut("/workforce/notification-policy", values)); }
export async function saveWarehouseRemote(values) { return camel(await apiPost("/workforce/warehouses", values)); }
export async function bulkPatchWarehousesRemote(values) { return camel(await apiPatch("/workforce/warehouses", values)); }
export async function postBreak(shiftId, personId, action) {
  return camel(await apiPost(`/workforce/shifts/${encodeURIComponent(shiftId)}/breaks`, { person_id: personId, action: action.toUpperCase() }));
}
export async function postLeave(values) {
  return camel(await apiPost("/workforce/leave-requests", values));
}
export async function postCorrection(values) {
  return camel(await apiPost("/workforce/correction-requests", values));
}
export async function dismissAnnouncementRemote(id, personId) {
  return apiPost(`/workforce/announcements/${encodeURIComponent(id)}/dismiss`, { person_id: personId });
}
export async function resolveLeave(id, decision, managerNote) {
  return camel(await apiPost(`/workforce/leave-requests/${encodeURIComponent(id)}/resolve`, { decision, manager_note: managerNote }));
}
export async function resolveManagerTask(id, values) {
  return camel(await apiPost(`/workforce/manager-tasks/${encodeURIComponent(id)}/resolve`, values));
}
export async function markNotificationRead(id, personId) {
  return apiPost(`/workforce/notifications/${encodeURIComponent(id)}/read?person_id=${encodeURIComponent(personId)}`, {});
}
export async function removeNotification(id, personId) {
  return apiDelete(`/workforce/notifications/${encodeURIComponent(id)}?person_id=${encodeURIComponent(personId)}`);
}
export async function removeAllNotifications(personId) {
  return apiDelete(`/workforce/notifications?person_id=${encodeURIComponent(personId)}`);
}
export async function postAttendance(shiftId, action, proof) {
  return camel(await apiPost(`/workforce/shifts/${encodeURIComponent(shiftId)}/${action}`, proof));
}

async function requestLocalPilotProof(shiftId, personId) {
  const [shiftResponse, warehouseResponse] = await Promise.all([
    apiGet(`/workforce/shifts?person_id=${encodeURIComponent(personId)}`),
    apiGet("/workforce/warehouses"),
  ]);
  const shift = (shiftResponse.rows || []).find((item) => String(item.id) === String(shiftId));
  const warehouse = (warehouseResponse.rows || []).find((item) => String(item.id) === String(shift?.warehouse_id));
  const deviceId = PILOT_DEVICE_IDS[String(personId)];
  if (!shift || !warehouse) throw new Error("Yerel pilot için vardiya/depo koordinatı bulunamadı.");
  if (!deviceId) throw new Error("Bu pilot personeli için kayıtlı test cihazı yok.");
  return {
    latitude: Number(warehouse.latitude),
    longitude: Number(warehouse.longitude),
    accuracy_meters: Math.min(5, Number(warehouse.max_accuracy || 50)),
    device_id: deviceId,
    device_trusted: true,
    pilot_simulation: true,
  };
}

export function requestNativeAttendanceProof(action, shiftId, personId) {
  if (LOCAL_PILOT_MODE) return requestLocalPilotProof(shiftId, personId);
  return new Promise((resolve, reject) => {
    const requestId = crypto.randomUUID();
    const timeout = window.setTimeout(() => { window.removeEventListener("opex-native-attendance-proof", receive); reject(new Error("Native cihaz doğrulama yanıtı alınamadı.")); }, 15000);
    function receive(event) {
      if (event.detail?.requestId !== requestId) return;
      window.clearTimeout(timeout); window.removeEventListener("opex-native-attendance-proof", receive);
      if (event.detail.error) reject(new Error(event.detail.error)); else resolve(event.detail.proof);
    }
    window.addEventListener("opex-native-attendance-proof", receive);
    const message = { requestId, action, shiftId, personId };
    if (window.webkit?.messageHandlers?.opexAttendance) window.webkit.messageHandlers.opexAttendance.postMessage(message);
    else if (window.OpexNative?.requestAttendanceProof) window.OpexNative.requestAttendanceProof(JSON.stringify(message));
    else { window.clearTimeout(timeout); window.removeEventListener("opex-native-attendance-proof", receive); reject(new Error("Check-in/out yalnızca kayıtlı native uygulamadan yapılabilir.")); }
  });
}
