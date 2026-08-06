import { apiGet, apiPost, apiPut, apiUpload, apiDownload } from "../../api/client.js";

function camelKey(key) { return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()); }
function camel(value) {
  if (Array.isArray(value)) return value.map(camel);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [camelKey(key), camel(item)]));
  return value;
}

export async function loadRecruitment() { return camel(await apiGet("/recruitment/bootstrap")); }
export async function evaluateRecruitment(params) {
  const query = new URLSearchParams(params);
  return camel(await apiGet(`/recruitment/evaluate?${query}`));
}
export async function createRecruitmentRequest(values) { return camel(await apiPost("/recruitment/requests", values)); }
export async function uploadRecruitmentEvidence(id, file) {
  const form = new FormData(); form.append("file", file);
  return camel(await apiUpload(`/recruitment/requests/${encodeURIComponent(id)}/evidence`, form));
}
export async function decideRecruitmentRequest(id, decision, note) {
  return camel(await apiPost(`/recruitment/requests/${encodeURIComponent(id)}/decision`, { decision, note }));
}
export async function saveRecruitmentSettings(values) { return camel(await apiPut("/recruitment/settings", values)); }
export async function saveRecruitmentNorm(values) { return camel(await apiPut("/recruitment/norms", values)); }
export async function retryRecruitmentEmail(id) { return camel(await apiPost(`/recruitment/email-outbox/${encodeURIComponent(id)}/retry`, {})); }
export async function downloadRecruitmentEvidence(id, filename) {
  const blob = await apiDownload(`/recruitment/requests/${encodeURIComponent(id)}/evidence`);
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename || `${id}-istifa-belgesi`; anchor.click();
  URL.revokeObjectURL(url);
}

