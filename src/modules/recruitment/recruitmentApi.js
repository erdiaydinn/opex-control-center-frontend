import { apiGet, apiPost, apiPut, apiUpload, apiDownload, publicApiPost, publicApiUpload } from "../../api/client.js";

const SAFE_RECRUITMENT_BACKEND_ERROR = "İşe alım işlemi tamamlanamadı. Lütfen tekrar deneyin.";
const SAFE_CLIENT_STATUSES = new Set([400, 404, 409, 422]);

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

async function safeBackendRequest(request, fallback = SAFE_RECRUITMENT_BACKEND_ERROR) {
  try {
    return camel(await request);
  } catch (error) {
    let message = fallback;
    if (error?.status === 401) message = "Oturum süresi doldu. Lütfen yeniden giriş yapın.";
    else if (error?.status === 403) message = "Bu işlem için yetkiniz bulunmuyor.";
    else if (SAFE_CLIENT_STATUSES.has(Number(error?.status)) && typeof error?.message === "string" && error.message.trim()) {
      message = error.message.trim().slice(0, 500);
    }
    const supportRef = error?.requestId ? ` (Ref: ${error.requestId})` : "";
    const safe = new Error(`${message}${supportRef}`);
    safe.name = "RecruitmentBackendError";
    safe.status = error?.status || 0;
    safe.code = error?.code || null;
    safe.requestId = error?.requestId || null;
    safe.cause = error;
    throw safe;
  }
}

let primedRecruitmentBootstrap = null;

export function primeRecruitmentBootstrap(value) { primedRecruitmentBootstrap = value; }

export async function loadRecruitment() {
  if (primedRecruitmentBootstrap) {
    const value = primedRecruitmentBootstrap;
    primedRecruitmentBootstrap = null;
    return value;
  }
  return safeBackendRequest(apiGet("/recruitment/bootstrap"), "İşe alım verileri alınamadı. Lütfen tekrar deneyin.");
}
export async function evaluateRecruitment(params) {
  const query = new URLSearchParams(params);
  return safeBackendRequest(apiGet(`/recruitment/evaluate?${query}`));
}
export async function createRecruitmentRequest(values) { return safeBackendRequest(apiPost("/recruitment/requests", values)); }
export async function uploadRecruitmentEvidence(id, file) {
  const form = new FormData(); form.append("file", file);
  return safeBackendRequest(apiUpload(`/recruitment/requests/${encodeURIComponent(id)}/evidence`, form));
}
export async function decideRecruitmentRequest(id, decision, note) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(id)}/decision`, { decision, note })); }
export async function importRecruitmentHrActual(rows, sourceName, asOf) { return safeBackendRequest(apiPost("/recruitment/hr-actual/import", { source_name: sourceName, as_of: asOf, rows }), "HR Actual verisi yüklenemedi. Dosya ve yetkileri kontrol edin."); }
export async function registerRecruitmentCandidate(requestId, values) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates`, values)); }
export async function uploadRecruitmentCandidateEvidence(requestId, candidateId, file, documentType = "OTHER") {
  const form = new FormData(); form.append("file", file); form.append("document_type", documentType);
  return safeBackendRequest(apiUpload(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/evidence`, form));
}
export async function issueRecruitmentCandidateUploadCapability(requestId, candidateId, documentType, expiresInMinutes = 1440) {
  return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/upload-capabilities`, { document_type: documentType, expires_in_minutes: expiresInMinutes }));
}
export async function uploadCandidateEvidenceWithCapability(capability, documentType, file) {
  const form = new FormData(); form.append("file", file); form.append("document_type", documentType);
  return safeBackendRequest(publicApiUpload("/recruitment/candidate-upload/evidence", form, { "X-EAY-Upload-Capability": capability }), "Belge yüklenemedi. Bağlantı kullanılmış veya süresi dolmuş olabilir.");
}
export async function verifyRecruitmentCandidateDocument(requestId, candidateId, values) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/document-verifications`, values)); }
export async function attestRecruitmentCandidateDocument(requestId, candidateId, evidenceSha256, note) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/document-verifications/attest`, { evidence_sha256: evidenceSha256, note })); }
export async function decideRecruitmentCandidate(requestId, candidateId, decision, note) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/decision`, { decision, note })); }
export async function activateRecruitmentHire(requestId, values) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/hires`, values)); }
export async function downloadRecruitmentCandidateEvidence(requestId, candidateId, digest, filename) {
  const blob = await safeBackendRequest(apiDownload(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/evidence/${encodeURIComponent(digest)}`));
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
  try { anchor.href = url; anchor.download = filename || `${candidateId}-kanit`; anchor.rel = "noopener"; anchor.click(); }
  finally { URL.revokeObjectURL(url); }
}
export async function saveRecruitmentSettings(values) { return safeBackendRequest(apiPut("/recruitment/settings", values)); }
export async function saveRecruitmentNorm(values) { return safeBackendRequest(apiPut("/recruitment/norms", values)); }
export async function retryRecruitmentEmail(id) { return safeBackendRequest(apiPost(`/recruitment/email-outbox/${encodeURIComponent(id)}/retry`, {})); }
export async function downloadRecruitmentEvidence(id, filename) {
  const blob = await safeBackendRequest(apiDownload(`/recruitment/requests/${encodeURIComponent(id)}/evidence`));
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
  try { anchor.href = url; anchor.download = filename || `${id}-istifa-belgesi`; anchor.rel = "noopener"; anchor.click(); }
  finally { URL.revokeObjectURL(url); }
}

// Governed orchestration
export async function listRecruitmentPipelines() { return safeBackendRequest(apiGet("/recruitment/orchestration/pipelines")); }
export async function assignRecruitmentPipeline(requestId, candidateId, templateId) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/pipeline`, { template_id: templateId })); }
export async function transitionRecruitmentStage(requestId, candidateId, toStage, reason = "") { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/pipeline/transition`, { to_stage: toStage, reason })); }
export async function loadCandidateOrchestration(requestId, candidateId) { return safeBackendRequest(apiGet(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/orchestration`)); }
export async function submitRecruitmentScorecard(requestId, candidateId, competencies, recommendation, conflictDeclared = false) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/interviews/scorecards`, { competencies, recommendation, conflict_declared: conflictDeclared })); }
export async function addRecruitmentCandidateNote(requestId, candidateId, noteType, visibility, body) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/notes`, { note_type: noteType, visibility, body })); }
export async function createRecruitmentOffer(requestId, candidateId, packageValues, expiresInHours = 168) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/offers`, { package: packageValues, expires_in_hours: expiresInHours })); }
export async function issueRecruitmentOfferCapability(offerId, expiresInHours = 168) { return safeBackendRequest(apiPost(`/recruitment/offers/${encodeURIComponent(offerId)}/decision-capabilities`, { expires_in_hours: expiresInHours })); }
export async function updateRecruitmentOnboardingTask(taskId, status, note = "") { return safeBackendRequest(apiPost(`/recruitment/onboarding/tasks/${encodeURIComponent(taskId)}`, { status, note })); }
export async function loadMyRecruitmentOnboardingTasks(includeTerminal = false) { return safeBackendRequest(apiGet(`/recruitment/onboarding/tasks?include_terminal=${includeTerminal ? "true" : "false"}`), "Onboarding görevleri alınamadı. Lütfen tekrar deneyin."); }
export async function loadRecruitmentOrchestrationAnalytics() { return safeBackendRequest(apiGet("/recruitment/orchestration/analytics")); }

// Interview scheduling
export async function listRecruitmentInterviewSchedules(requestId, candidateId) { return safeBackendRequest(apiGet(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/interviews`)); }
export async function createRecruitmentInterviewSchedule(requestId, candidateId, values) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/interviews`, values)); }
export async function setRecruitmentInterviewScheduleStatus(scheduleId, status) { return safeBackendRequest(apiPost(`/recruitment/interviews/${encodeURIComponent(scheduleId)}/status`, { status })); }
export async function issueRecruitmentInterviewCapability(requestId, candidateId, scheduleId, expiresInHours = 168) { return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/interviews/${encodeURIComponent(scheduleId)}/booking-capabilities`, { expires_in_hours: expiresInHours })); }

// Candidate-facing capability API. No employee access token is ever attached.
export async function viewCandidateOffer(capability) { return safeBackendRequest(publicApiPost("/public/recruitment/offer", { capability }), "Teklif bağlantısı geçersiz veya süresi dolmuş olabilir."); }
export async function decideCandidateOffer(capability, decision) { return safeBackendRequest(publicApiPost("/public/recruitment/offer/decision", { capability, decision }), "Teklif kararı kaydedilemedi. Bağlantı kullanılmış veya süresi dolmuş olabilir."); }
export async function viewCandidateInterview(capability) { return safeBackendRequest(publicApiPost("/public/recruitment/interview", { capability }), "Mülakat bağlantısı geçersiz veya süresi dolmuş olabilir."); }
export async function mutateCandidateInterview(capability, action, slotId = null) { return safeBackendRequest(publicApiPost("/public/recruitment/interview/decision", { capability, action, slot_id: slotId }), "Mülakat seçimi kaydedilemedi. Link kullanılmış, süresi dolmuş veya slot dolmuş olabilir."); }
