import { apiGet, apiPost, apiPut, apiUpload, apiDownload } from "../../api/client.js";

const SAFE_RECRUITMENT_BACKEND_ERROR = "İşe alım işlemi tamamlanamadı. Lütfen tekrar deneyin.";

function camelKey(key) { return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()); }
function camel(value) {
  if (Array.isArray(value)) return value.map(camel);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [camelKey(key), camel(item)]));
  return value;
}

async function safeBackendRequest(request, fallback = SAFE_RECRUITMENT_BACKEND_ERROR) {
  try {
    return camel(await request);
  } catch (error) {
    const safe = new Error(fallback);
    safe.name = "RecruitmentBackendError";
    safe.cause = error;
    throw safe;
  }
}

let primedRecruitmentBootstrap = null;

export function primeRecruitmentBootstrap(value) {
  primedRecruitmentBootstrap = value;
}

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
export async function decideRecruitmentRequest(id, decision, note) {
  return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(id)}/decision`, { decision, note }));
}
export async function importRecruitmentHrActual(rows, sourceName, asOf) {
  return safeBackendRequest(apiPost("/recruitment/hr-actual/import", {
    source_name: sourceName,
    as_of: asOf,
    rows,
  }), "HR Actual verisi yüklenemedi. Dosya ve yetkileri kontrol edin.");
}
export async function registerRecruitmentCandidate(requestId, values) {
  return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates`, values));
}
export async function uploadRecruitmentCandidateEvidence(requestId, candidateId, file) {
  const form = new FormData(); form.append("file", file);
  return safeBackendRequest(apiUpload(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/evidence`, form));
}
export async function decideRecruitmentCandidate(requestId, candidateId, decision, note) {
  return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/decision`, { decision, note }));
}
export async function activateRecruitmentHire(requestId, values) {
  return safeBackendRequest(apiPost(`/recruitment/requests/${encodeURIComponent(requestId)}/hires`, values));
}
export async function downloadRecruitmentCandidateEvidence(requestId, candidateId, digest, filename) {
  const blob = await safeBackendRequest(apiDownload(`/recruitment/requests/${encodeURIComponent(requestId)}/candidates/${encodeURIComponent(candidateId)}/evidence/${encodeURIComponent(digest)}`));
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename || `${candidateId}-kanit`; anchor.click();
  URL.revokeObjectURL(url);
}
export async function saveRecruitmentSettings(values) { return safeBackendRequest(apiPut("/recruitment/settings", values)); }
export async function saveRecruitmentNorm(values) { return safeBackendRequest(apiPut("/recruitment/norms", values)); }
export async function retryRecruitmentEmail(id) { return safeBackendRequest(apiPost(`/recruitment/email-outbox/${encodeURIComponent(id)}/retry`, {})); }
export async function downloadRecruitmentEvidence(id, filename) {
  const blob = await safeBackendRequest(apiDownload(`/recruitment/requests/${encodeURIComponent(id)}/evidence`));
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename || `${id}-istifa-belgesi`; anchor.click();
  URL.revokeObjectURL(url);
}
