import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "../../api/client.js";
import { normalizeAttendanceProof } from "./workforceAttendanceProof.js";

export { normalizeAttendanceProof } from "./workforceAttendanceProof.js";

const LOCAL_PILOT_MODE = String(import.meta.env.VITE_LOCAL_PILOT_MODE || "false").toLowerCase() === "true";
const PILOT_DEVICE_IDS = { "100184": "DEVICE-1", "100221": "DEV-4418", "100287": "DEV-7781" };
const IMPORT_BATCH_SIZE = 3000;
const SAFE_WORKFORCE_BACKEND_ERROR = "Workforce işlemi tamamlanamadı. Lütfen tekrar deneyin.";

function camelKey(key) { return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()); }
function camel(value) {
  if (Array.isArray(value)) return value.map(camel);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [camelKey(key), camel(item)]));
  return value;
}

async function safeBackendRequest(request, fallback = SAFE_WORKFORCE_BACKEND_ERROR) {
  try {
    return camel(await request);
  } catch (error) {
    const safe = new Error(fallback);
    safe.name = "WorkforceBackendError";
    safe.cause = error;
    throw safe;
  }
}

export async function loadMobileWorkforce(personId) {
  return safeBackendRequest(apiGet(`/workforce/mobile/bootstrap?person_id=${encodeURIComponent(personId)}`));
}
export async function loadWorkforceFlexibility(personId) {
  const query = `person_id=${encodeURIComponent(personId)}`;
  const [availability, openShifts] = await Promise.all([
    safeBackendRequest(apiGet(`/workforce/flexibility/availability?${query}`)),
    safeBackendRequest(apiGet(`/workforce/flexibility/open-shifts?${query}`)),
  ]);
  return { availability: availability.rows || [], openShifts: openShifts.rows || [] };
}
export async function saveWorkforceAvailability(personId, values) {
  return safeBackendRequest(apiPut("/workforce/flexibility/availability", {
    person_id: String(personId),
    date: values.date,
    available: values.available,
    earliest_start: values.available && values.earliestStart ? values.earliestStart : null,
    latest_end: values.available && values.latestEnd ? values.latestEnd : null,
    preferred_start: values.available && values.preferredStart ? values.preferredStart : null,
    preferred_end: values.available && values.preferredEnd ? values.preferredEnd : null,
    note: values.note || "",
  }));
}
export async function claimWorkforceOpenShift(openShiftId, personId) {
  return safeBackendRequest(apiPost(`/workforce/flexibility/open-shifts/${encodeURIComponent(openShiftId)}/claim`, { person_id: String(personId) }));
}
export async function createWorkforceOpenShift(values) {
  return safeBackendRequest(apiPost("/workforce/flexibility/open-shifts", {
    warehouse_id: values.warehouseId,
    date: values.date,
    start: values.start,
    end: values.end,
    break_minutes: Number(values.breakMinutes || 0),
    role: values.role || "Picker",
    capacity: Number(values.capacity || 1),
    note: values.note || "",
  }));
}
export async function loadAdminWorkforce() { return safeBackendRequest(apiGet("/workforce/admin/bootstrap"), "Backend Workforce verileri alınamadı. Lütfen tekrar deneyin."); }
export async function createShiftRemote(values) { return safeBackendRequest(apiPost("/workforce/shifts", values)); }
export async function approveAttendanceRemote(id, note = "") { return safeBackendRequest(apiPost(`/workforce/attendance/${encodeURIComponent(id)}/approve`, { note })); }
export async function bulkApproveRemote(ids, note = "") { return safeBackendRequest(apiPost("/workforce/attendance/bulk-approve", { attendance_ids: ids, note })); }
export async function correctAttendanceRemote(id, values) { return safeBackendRequest(apiPost(`/workforce/attendance/${encodeURIComponent(id)}/manual-correction`, values)); }
export async function resetDeviceRemote(personId, reason) { return safeBackendRequest(apiPost(`/workforce/devices/${encodeURIComponent(personId)}/reset`, { reason })); }
export async function createDeviceChallengeRemote(personId, deviceId) { return safeBackendRequest(apiPost("/workforce/devices/challenge", { person_id: personId, device_id: deviceId })); }
export async function createRuleRemote(values) { return safeBackendRequest(apiPost("/workforce/rules", values)); }
export async function createAnnouncementRemote(values) { return safeBackendRequest(apiPost("/workforce/announcements", values)); }
export async function saveNotificationPolicyRemote(values) { return safeBackendRequest(apiPut("/workforce/notification-policy", values)); }
export async function saveWarehouseRemote(values) { return safeBackendRequest(apiPost("/workforce/warehouses", values)); }
export async function bulkPatchWarehousesRemote(values) { return safeBackendRequest(apiPatch("/workforce/warehouses", values)); }

async function postImportBatches(path, rows, makePayload, mergeResult, onProgress) {
  const source = Array.isArray(rows) ? rows : [];
  if (!source.length) return mergeResult(null, null, 0);
  let combined = null;
  const batchCount = Math.ceil(source.length / IMPORT_BATCH_SIZE);
  for (let offset = 0, batchIndex = 0; offset < source.length; offset += IMPORT_BATCH_SIZE, batchIndex += 1) {
    const batch = source.slice(offset, offset + IMPORT_BATCH_SIZE);
    const result = await safeBackendRequest(apiPost(path, makePayload(batch, batchIndex, batchCount)));
    combined = mergeResult(combined, result, source.length);
    onProgress?.({ processed: Math.min(offset + batch.length, source.length), total: source.length, batch: batchIndex + 1, batchCount });
  }
  return combined;
}

function sumResult(previous, current, total, numericKeys, arrayKeys = []) {
  const next = previous || { total };
  numericKeys.forEach((key) => { next[key] = Number(next[key] || 0) + Number(current?.[key] || 0); });
  arrayKeys.forEach((key) => { next[key] = [...(next[key] || []), ...(current?.[key] || [])]; });
  next.total = total;
  return next;
}

export async function upsertPeopleRemote(rows, onProgress) {
  return postImportBatches(
    "/workforce/people/bulk-upsert",
    rows,
    (batch) => ({ rows: batch.map((row) => ({
      employee_id: String(row.id), roster_ids: (row.rosterIds || []).map(String), full_name: row.name, tckn: row.nationalId, email: row.email || null, phone: row.phone || null,
      position: row.role || "Picker", warehouse_id: row.warehouse || row.warehouseCode || null,
      employment_start: row.hireDate || null, employment_end: row.terminationDate || null, active: !row.terminationDate,
    })) }),
    (previous, current, total) => sumResult(previous, current, total, ["created", "updated"], ["rosterConflicts"]),
    onProgress,
  );
}
export async function importEmploymentLifecycleRemote(rows, fileName, onProgress) {
  return postImportBatches(
    "/workforce/people/employment-lifecycle/import",
    rows,
    (batch) => ({ file_name: fileName, rows: batch.map((row) => ({ person_id: String(row.personId), employment_start: row.hireDate || null, employment_end: row.terminationDate || null, identity_method: row.identityMethod || "TC" })) }),
    (previous, current, total) => sumResult(previous, current, total, ["matched", "unmatched"]),
    onProgress,
  );
}
export async function importAttendanceRemote(rows, fileName, onProgress) {
  return postImportBatches("/workforce/attendance/import", rows, (batch) => ({ file_name: fileName, rows: batch.map((row) => ({
    id: row.id, shift_id: row.shiftId || "", person_id: String(row.personId), name: row.name, role: row.role || "Picker",
    warehouse: row.warehouse || "", date: row.date, planned: row.planned || "Dosyadan", check_in: row.checkIn === "—" ? null : row.checkIn,
    check_out: row.checkOut === "—" ? null : row.checkOut, break_minutes: Number(row.breakMinutes || 0), net_minutes: Number(row.netMinutes || 0),
    expected_minutes: Number(row.expectedMinutes || 0), status: row.status, approval: row.approval, source: row.source,
    source_person_id: String(row.sourcePersonId || ""), identity_method: row.identityMethod || "",
  })) }), (previous, current, total) => sumResult(previous, current, total, ["inserted", "updated", "protected", "unmatched", "dailyMaxExceptions"]), onProgress);
}
export async function importLeavesRemote(rows, fileName, onProgress) {
  return postImportBatches("/workforce/leaves/import", rows, (batch) => ({ file_name: fileName, rows: batch.map((row) => ({
    id: row.id, person_id: String(row.personId), person_name: row.personName || "", warehouse: row.warehouse || "", type_id: row.typeId,
    category: row.category || "", date: row.date, minutes: Number(row.minutes || 0), approval: row.approval || "Onaylandı",
    note: row.note || "", source: row.source || "Time Off Used", source_person_id: String(row.sourcePersonId || ""), identity_method: row.identityMethod || "",
  })) }), (previous, current, total) => sumResult(previous, current, total, ["inserted", "skipped", "unmatched"]), onProgress);
}
export async function postBreak(shiftId, personId, action) {
  return safeBackendRequest(apiPost(`/workforce/shifts/${encodeURIComponent(shiftId)}/breaks`, { person_id: personId, action: action.toUpperCase() }));
}
export async function postLeave(values) {
  return safeBackendRequest(apiPost("/workforce/leave-requests", values));
}
export async function postCorrection(values) {
  return safeBackendRequest(apiPost("/workforce/correction-requests", values));
}
export async function dismissAnnouncementRemote(id, personId) {
  return safeBackendRequest(apiPost(`/workforce/announcements/${encodeURIComponent(id)}/dismiss`, { person_id: personId }));
}
export async function resolveLeave(id, decision, managerNote) {
  return safeBackendRequest(apiPost(`/workforce/leave-requests/${encodeURIComponent(id)}/resolve`, { decision, manager_note: managerNote }));
}
export async function resolveManagerTask(id, values) {
  return safeBackendRequest(apiPost(`/workforce/manager-tasks/${encodeURIComponent(id)}/resolve`, values));
}
export async function markNotificationRead(id, personId) {
  return safeBackendRequest(apiPost(`/workforce/notifications/${encodeURIComponent(id)}/read?person_id=${encodeURIComponent(personId)}`, {}));
}
export async function removeNotification(id, personId) {
  return safeBackendRequest(apiDelete(`/workforce/notifications/${encodeURIComponent(id)}?person_id=${encodeURIComponent(personId)}`));
}
export async function removeAllNotifications(personId) {
  return safeBackendRequest(apiDelete(`/workforce/notifications?person_id=${encodeURIComponent(personId)}`));
}
export async function postAttendance(shiftId, action, proof) {
  return safeBackendRequest(apiPost(`/workforce/shifts/${encodeURIComponent(shiftId)}/${action}`, proof));
}

async function requestLocalPilotProof(shiftId, personId) {
  const [shiftResponse, warehouseResponse] = await Promise.all([
    safeBackendRequest(apiGet(`/workforce/shifts?person_id=${encodeURIComponent(personId)}`)),
    safeBackendRequest(apiGet("/workforce/warehouses")),
  ]);
  const shift = (shiftResponse.rows || []).find((item) => String(item.id) === String(shiftId));
  const warehouse = (warehouseResponse.rows || []).find((item) => String(item.id) === String(shift?.warehouseId || shift?.warehouse_id));
  const deviceId = PILOT_DEVICE_IDS[String(personId)];
  if (!shift || !warehouse) throw new Error("Yerel pilot için vardiya/depo koordinatı bulunamadı.");
  if (!deviceId) throw new Error("Bu pilot personeli için kayıtlı test cihazı yok.");
  return {
    latitude: Number(warehouse.latitude),
    longitude: Number(warehouse.longitude),
    accuracy_meters: Math.min(5, Number(warehouse.maxAccuracy || warehouse.max_accuracy || 50)),
    device_id: deviceId,
    device_trusted: true,
    local_auth_method: "DEVICE_BIOMETRIC",
    local_auth_at: new Date().toISOString(),
    pilot_simulation: true,
  };
}

export function requestNativeAttendanceProof(action, shiftId, personId) {
  if (LOCAL_PILOT_MODE) return requestLocalPilotProof(shiftId, personId).then((proof) => normalizeAttendanceProof(proof));
  return new Promise((resolve, reject) => {
    const requestId = crypto.randomUUID();
    const timeout = window.setTimeout(() => { window.removeEventListener("opex-native-attendance-proof", receive); reject(new Error("Native cihaz doğrulama yanıtı alınamadı.")); }, 15000);
    function receive(event) {
      if (event.detail?.requestId !== requestId) return;
      window.clearTimeout(timeout); window.removeEventListener("opex-native-attendance-proof", receive);
      if (event.detail.error) reject(new Error("Native cihaz doğrulaması başarısız oldu."));
      else {
        try { resolve(normalizeAttendanceProof(event.detail.proof)); }
        catch (error) { reject(error); }
      }
    }
    window.addEventListener("opex-native-attendance-proof", receive);
    const message = { requestId, action, shiftId, personId };
    if (window.webkit?.messageHandlers?.opexAttendance) window.webkit.messageHandlers.opexAttendance.postMessage(message);
    else if (window.OpexNative?.requestAttendanceProof) window.OpexNative.requestAttendanceProof(JSON.stringify(message));
    else { window.clearTimeout(timeout); window.removeEventListener("opex-native-attendance-proof", receive); reject(new Error("Check-in/out yalnızca kayıtlı native uygulamadan yapılabilir.")); }
  });
}