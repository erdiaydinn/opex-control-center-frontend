import { getAccessToken } from "../auth/tokenStore.js";


const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";
const PUBLIC_PREFIXES = ["/public/recruitment/"];
const PUBLIC_EXACT_PATHS = new Set(["/recruitment/candidate-upload/evidence"]);


export class ApiError extends Error {
  constructor(message, { status = 0, code = null, requestId = null, payload = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.payload = payload;
  }
}


function requireAccessToken() {
  const token = getAccessToken();
  if (!token) throw new ApiError("Authenticated access token is required.", { status: 401, code: "AUTH_REQUIRED" });
  return token;
}


function buildHeaders(options = {}) {
  const headers = new Headers(options.headers || {});
  // Client-supplied identity is never authoritative.
  headers.delete("X-User-Email");
  headers.delete("X-OPEX-User");
  headers.delete("X-OPEX-Role");
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body != null && !isFormData && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  // Callers cannot override central authentication.
  headers.set("Authorization", `Bearer ${requireAccessToken()}`);
  return headers;
}


function buildPublicHeaders(options = {}) {
  const headers = new Headers(options.headers || {});
  headers.delete("Authorization");
  headers.delete("Cookie");
  headers.delete("X-User-Email");
  headers.delete("X-OPEX-User");
  headers.delete("X-OPEX-Role");
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body != null && !isFormData && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return headers;
}


function assertPublicPath(path) {
  const value = String(path);
  if (!PUBLIC_EXACT_PATHS.has(value) && !PUBLIC_PREFIXES.some((prefix) => value.startsWith(prefix))) {
    throw new ApiError("Public API path is not allow-listed.", { status: 0, code: "PUBLIC_PATH_REJECTED" });
  }
}


function errorDetails(payload, fallback) {
  if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
    return { message: payload.detail.trim(), code: null };
  }
  if (payload && payload.detail && typeof payload.detail === "object") {
    const message = typeof payload.detail.message === "string" ? payload.detail.message.trim() : "";
    const code = typeof payload.detail.code === "string" ? payload.detail.code.trim() : null;
    if (message) return { message, code };
  }
  return { message: fallback, code: null };
}


async function readPayload(response) {
  const responseText = await response.text();
  if (!responseText) return null;
  try { return JSON.parse(responseText); } catch { return null; }
}


function errorFromResult(result, fallbackPrefix = "API error") {
  const detail = errorDetails(result.data, `${fallbackPrefix}: ${result.status}`);
  return new ApiError(detail.message, {
    status: result.status,
    code: detail.code,
    requestId: result.requestId,
    payload: result.data,
  });
}


export async function apiFetchWithStatus(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers: buildHeaders(options) });
  return {
    ok: response.ok,
    status: response.status,
    requestId: response.headers.get("x-request-id"),
    data: await readPayload(response),
  };
}


export async function apiFetch(path, options = {}) {
  const result = await apiFetchWithStatus(path, options);
  if (!result.ok) throw errorFromResult(result);
  return result.data;
}


export function apiGet(path) { return apiFetch(path, { method: "GET" }); }
export function apiPost(path, data = {}) { return apiFetch(path, { method: "POST", body: JSON.stringify(data) }); }
export function apiPut(path, data = {}) { return apiFetch(path, { method: "PUT", body: JSON.stringify(data) }); }
export function apiDelete(path) { return apiFetch(path, { method: "DELETE" }); }
export function apiPatch(path, data = {}) { return apiFetch(path, { method: "PATCH", body: JSON.stringify(data) }); }
export function apiUpload(path, formData) { return apiFetch(path, { method: "POST", body: formData }); }


export async function publicApiPost(path, data = {}) {
  assertPublicPath(path);
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: buildPublicHeaders({ body: data }),
    body: JSON.stringify(data),
    credentials: "omit",
    cache: "no-store",
    referrerPolicy: "no-referrer",
  });
  const result = {
    ok: response.ok,
    status: response.status,
    requestId: response.headers.get("x-request-id"),
    data: await readPayload(response),
  };
  if (!result.ok) throw errorFromResult(result, "Candidate portal error");
  return result.data;
}


export async function publicApiUpload(path, formData, headers = {}) {
  assertPublicPath(path);
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: buildPublicHeaders({ body: formData, headers }),
    body: formData,
    credentials: "omit",
    cache: "no-store",
    referrerPolicy: "no-referrer",
  });
  const result = {
    ok: response.ok,
    status: response.status,
    requestId: response.headers.get("x-request-id"),
    data: await readPayload(response),
  };
  if (!result.ok) throw errorFromResult(result, "Candidate upload error");
  return result.data;
}


export async function apiDownload(path) {
  const response = await fetch(`${API_BASE}${path}`, { method: "GET", headers: buildHeaders(), cache: "no-store" });
  if (!response.ok) {
    const result = {
      ok: false,
      status: response.status,
      requestId: response.headers.get("x-request-id"),
      data: await readPayload(response),
    };
    throw errorFromResult(result, "Download error");
  }
  return response.blob();
}
