import { apiGet, apiPost, apiPut } from "../../api/client.js";


const SAFE_ERROR = "Workforce flexibility operation could not be completed.";

function camelKey(key) { return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()); }
function camel(value) {
  if (Array.isArray(value)) return value.map(camel);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [camelKey(key), camel(item)]));
  }
  return value;
}

async function safe(request, fallback = SAFE_ERROR) {
  try {
    return camel(await request);
  } catch (error) {
    const wrapped = new Error(fallback);
    wrapped.name = "WorkforceFlexibilityError";
    wrapped.cause = error;
    throw wrapped;
  }
}

function demandPayload(values) {
  return {
    worksite_id: values.worksiteId,
    interval_start: values.intervalStart,
    interval_minutes: Number(values.intervalMinutes || 60),
    model_version: values.modelVersion || "generic-work-activity-v1",
    signals: (values.signals || []).map((signal) => ({
      driver_key: signal.driverKey,
      activity_key: signal.activityKey,
      demand_mode: signal.demandMode,
      quantity: Number(signal.quantity || 0),
      source_ref: signal.sourceRef,
    })),
  };
}

export async function loadWorkforceFlexibility(personId) {
  const query = `person_id=${encodeURIComponent(personId)}`;
  const [availability, openShifts] = await Promise.all([
    safe(apiGet(`/workforce/flexibility/availability?${query}`)),
    safe(apiGet(`/workforce/flexibility/open-shifts?${query}`)),
  ]);
  return { availability: availability.rows || [], openShifts: openShifts.rows || [] };
}

export async function loadWorkforceOwnShifts(personId) {
  const result = await safe(apiGet(`/workforce/shifts?person_id=${encodeURIComponent(personId)}`));
  return result.rows || [];
}

export async function saveWorkforceAvailability(personId, values) {
  return safe(apiPut("/workforce/flexibility/availability", {
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
  return safe(apiPost(`/workforce/flexibility/open-shifts/${encodeURIComponent(openShiftId)}/claim`, {
    person_id: String(personId),
  }));
}

export async function loadWorkforceShiftTrades(personId) {
  const result = await safe(apiGet(`/workforce/flexibility/shift-trades?person_id=${encodeURIComponent(personId)}`));
  return result.rows || [];
}

export async function loadWorkforceSwapCandidates(personId, shiftId) {
  const query = new URLSearchParams({ person_id: String(personId), shift_id: String(shiftId) });
  const result = await safe(apiGet(`/workforce/flexibility/shift-trades/candidates?${query.toString()}`));
  return result.rows || [];
}

export async function createWorkforceShiftTrade(values) {
  return safe(apiPost("/workforce/flexibility/shift-trades", {
    person_id: String(values.personId),
    shift_id: String(values.shiftId),
    mode: values.mode,
    target_person_id: values.targetPersonId || null,
    target_shift_id: values.mode === "SWAP" ? String(values.targetShiftId || "") : null,
    note: values.note || "",
  }));
}

export async function acceptWorkforceShiftTrade(tradeId, personId) {
  return safe(apiPost(`/workforce/flexibility/shift-trades/${encodeURIComponent(tradeId)}/accept`, {
    person_id: String(personId),
  }));
}

export async function cancelWorkforceShiftTrade(tradeId, personId) {
  return safe(apiPost(`/workforce/flexibility/shift-trades/${encodeURIComponent(tradeId)}/cancel`, {
    person_id: String(personId),
  }));
}

export async function loadWorkforceShiftTradesAdmin(warehouseId, activeOnly = true) {
  const query = new URLSearchParams({
    warehouse_id: String(warehouseId),
    active_only: activeOnly ? "true" : "false",
  });
  const result = await safe(apiGet(`/workforce/flexibility/shift-trades/admin?${query.toString()}`));
  return result.rows || [];
}

export async function approveWorkforceShiftTrade(tradeId, note = "") {
  return safe(apiPost(`/workforce/flexibility/shift-trades/${encodeURIComponent(tradeId)}/approve`, { note }));
}

export async function rejectWorkforceShiftTrade(tradeId, note = "") {
  return safe(apiPost(`/workforce/flexibility/shift-trades/${encodeURIComponent(tradeId)}/reject`, { note }));
}

export async function loadWorkforceFlexibilityAdmin() {
  const [locations, activities] = await Promise.all([
    safe(apiGet("/workforce/warehouses")),
    safe(apiGet("/workforce/flexibility/activities")),
  ]);
  return { locations: locations.rows || [], activities: activities.rows || [] };
}

export async function loadWorkforceCapabilityPeople() {
  const result = await safe(apiGet("/workforce/people"));
  return result.rows || [];
}

export async function createWorkforceOpenShift(values) {
  return safe(apiPost("/workforce/flexibility/open-shifts", {
    warehouse_id: values.warehouseId,
    date: values.date,
    start: values.start,
    end: values.end,
    break_minutes: Number(values.breakMinutes || 0),
    role: values.role || "Worker",
    activity_keys: Array.isArray(values.activityKeys) ? values.activityKeys : [],
    capacity: Number(values.capacity || 1),
    note: values.note || "",
  }));
}

export async function loadWorkforceActivityTemplate(templateKey) {
  return safe(apiGet(`/workforce/flexibility/activity-templates/${encodeURIComponent(templateKey)}`));
}

export async function approveWorkforceActivity(values) {
  return safe(apiPost("/workforce/flexibility/activities", {
    activity_key: values.activityKey,
    display_name: values.displayName,
    category: values.category,
    unit_key: values.unitKey,
    demand_mode: values.demandMode,
    effective_from: values.effectiveFrom,
    source_ref: values.sourceRef,
    required_skill_keys: values.requiredSkillKeys || [],
    required_certification_keys: values.requiredCertificationKeys || [],
    required_equipment_keys: values.requiredEquipmentKeys || [],
    safety_tags: values.safetyTags || [],
    location_types: values.locationTypes || [],
  }));
}

export async function retireWorkforceActivity(activityKey) {
  return safe(apiPost(`/workforce/flexibility/activities/${encodeURIComponent(activityKey)}/retire`, {}));
}

export async function loadWorkforceLaborStandards(activityKey = "") {
  const query = activityKey ? `?activity_key=${encodeURIComponent(activityKey)}` : "";
  const result = await safe(apiGet(`/workforce/flexibility/labor-standards${query}`));
  return result.rows || [];
}

export async function approveWorkforceLaborStandard(values) {
  return safe(apiPost("/workforce/flexibility/labor-standards", {
    activity_key: values.activityKey,
    seconds_per_unit: Number(values.secondsPerUnit),
    people: Number(values.people || 1),
    effective_from: values.effectiveFrom,
    source_ref: values.sourceRef,
  }));
}

export async function retireWorkforceLaborStandard(activityKey) {
  return safe(apiPost(`/workforce/flexibility/labor-standards/${encodeURIComponent(activityKey)}/retire`, {}));
}

export async function previewWorkforceActivityDemand(values) {
  return safe(apiPost("/workforce/flexibility/demand-preview", demandPayload(values)));
}

export async function previewWorkforceActivityCapacity(values) {
  return safe(apiPost("/workforce/activity-capacity-preview", demandPayload(values)));
}

export async function updateWorkforceEmployeeCapabilities(employeeId, values) {
  return safe(apiPut(`/workforce/flexibility/employees/${encodeURIComponent(employeeId)}/capabilities`, {
    skill_keys: values.skillKeys || [],
    certification_keys: values.certificationKeys || [],
    equipment_keys: values.equipmentKeys || [],
  }));
}

export async function updateWorkforceWorksiteType(worksiteId, locationType) {
  return safe(apiPut(`/workforce/flexibility/worksites/${encodeURIComponent(worksiteId)}/type`, {
    location_type: locationType,
  }));
}
