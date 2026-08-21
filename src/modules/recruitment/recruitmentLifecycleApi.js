import { apiGet, apiPost } from "../../api/client.js";

const FALLBACK = "İşe alım yaşam döngüsü işlemi tamamlanamadı. Lütfen tekrar deneyin.";
const SAFE = new Set([400, 404, 409, 422]);

function camelKey(key) { return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()); }
function isPlainObject(value) {
  if (!value || Object.prototype.toString.call(value) !== "[object Object]") return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}
function camel(value) {
  if (Array.isArray(value)) return value.map(camel);
  if (isPlainObject(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [camelKey(key), camel(item)]));
  return value;
}
async function safe(request, fallback = FALLBACK) {
  try { return camel(await request); }
  catch (error) {
    let message = fallback;
    if (error?.status === 401) message = "Oturum süresi doldu. Lütfen yeniden giriş yapın.";
    else if (error?.status === 403) message = "Bu işlem için yetkiniz bulunmuyor.";
    else if (SAFE.has(Number(error?.status)) && typeof error?.message === "string" && error.message.trim()) message = error.message.trim().slice(0, 500);
    const ref = error?.requestId ? ` (Ref: ${error.requestId})` : "";
    const safeError = new Error(`${message}${ref}`);
    safeError.status = error?.status || 0;
    safeError.requestId = error?.requestId || null;
    safeError.cause = error;
    throw safeError;
  }
}

export function listOfferApprovals(status = "", limit = 100) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (status) query.set("status", status);
  return safe(apiGet(`/recruitment/offers/approvals?${query}`), "Teklif onay kuyruğu alınamadı.");
}
export function decideOfferApproval(offerId, decision, reason = "") {
  return safe(apiPost(`/recruitment/offers/${encodeURIComponent(offerId)}/approvals`, { decision, reason }));
}
export function issueApprovedOfferCapability(offerId, expiresInHours = 168) {
  return safe(apiPost(`/recruitment/offers/${encodeURIComponent(offerId)}/decision-capabilities`, { expires_in_hours: expiresInHours }));
}
export function listLifecycleCommunications(status = "", limit = 100) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (status) query.set("status", status);
  return safe(apiGet(`/recruitment/communications?${query}`), "Aday iletişim kuyruğu alınamadı.");
}
export function queueCandidateCommunication(requestId, candidateId, values) {
  return safe(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/communications`, values));
}
export function listTalentPool(poolKey = "") {
  const query = poolKey ? `?pool_key=${encodeURIComponent(poolKey)}` : "";
  return safe(apiGet(`/recruitment/talent-pool${query}`), "Talent pool alınamadı.");
}
export function addCandidateToTalentPool(requestId, candidateId, values) {
  return safe(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/talent-pool`, values));
}
export function withdrawTalentMembership(membershipId) {
  return safe(apiPost(`/recruitment/talent-pool/${encodeURIComponent(membershipId)}/withdraw`, {}));
}
export function listOffboardingCases() {
  return safe(apiGet("/recruitment/offboarding"), "Offboarding kayıtları alınamadı.");
}
export function createOffboardingCase(values) {
  return safe(apiPost("/recruitment/offboarding", values));
}
export function updateOffboardingTask(taskId, status, note = "") {
  return safe(apiPost(`/recruitment/offboarding/tasks/${encodeURIComponent(taskId)}`, { status, note }));
}
export function closeOffboardingCase(caseId) {
  return safe(apiPost(`/recruitment/offboarding/${encodeURIComponent(caseId)}/close`, {}));
}
