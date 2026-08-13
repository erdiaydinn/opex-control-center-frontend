import { getAccessToken } from "../auth/AuthContext.jsx";

const API_BASE = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || "/api";
const LOCAL_PILOT_MODE = String(import.meta.env.VITE_LOCAL_PILOT_MODE || "false").toLowerCase() === "true";

function localPilotHeaders() {
  if (!LOCAL_PILOT_MODE) return {};
  try {
    const user = JSON.parse(localStorage.getItem("opex_current_user") || "null");
    if (!user?.email) return {};
    return {
      "X-Opex-User": user.email,
      "X-Opex-Role": user.role || "viewer",
    };
  } catch {
    return {};
  }
}

export function getDemoEmail() {
  return localStorage.getItem("opex_demo_email") || "";
}

export async function apiFetch(path, options = {}) {
  const token = getAccessToken();
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(!isFormData ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(!token ? localPilotHeaders() : {}),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    if (response.status === 413) {
      throw new Error("Yükleme paketi sunucu sınırını aştı. Güncel sürümde kayıtlar otomatik parçalara ayrılır; sayfayı Ctrl+F5 ile yenileyip tekrar deneyin.");
    }
    throw new Error(err.detail || `API error: ${response.status}`);
  }

  const text = await response.text();

  if (!text) {
    return null;
  }

  return JSON.parse(text);
}

export function apiUpload(path, formData) {
  return apiFetch(path, { method: "POST", body: formData });
}

export async function apiDownload(path) {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(!token ? localPilotHeaders() : {}),
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Download error: ${response.status}`);
  }
  return response.blob();
}

export function apiGet(path) {
  return apiFetch(path, {
    method: "GET",
  });
}

export function apiPost(path, data = {}) {
  return apiFetch(path, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function apiPut(path, data = {}) {
  return apiFetch(path, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function apiPatch(path, data = {}) {
  return apiFetch(path, { method: "PATCH", body: JSON.stringify(data) });
}

export function apiDelete(path) {
  return apiFetch(path, {
    method: "DELETE",
  });
}
