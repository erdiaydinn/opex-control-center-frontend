import { getAccessToken } from "../auth/tokenStore.js";


const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "/api";


function requireAccessToken() {
  const token = getAccessToken();

  if (!token) {
    throw new Error(
      "Authenticated access token is required."
    );
  }

  return token;
}


function buildHeaders(options = {}) {
  const headers = new Headers(
    options.headers || {}
  );

  // Client-supplied identity is never authoritative.
  headers.delete("X-User-Email");
  headers.delete("X-OPEX-User");
  headers.delete("X-OPEX-Role");

  const isFormData =
    typeof FormData !== "undefined" &&
    options.body instanceof FormData;

  if (
    options.body != null &&
    !isFormData &&
    !headers.has("Content-Type")
  ) {
    headers.set(
      "Content-Type",
      "application/json"
    );
  }

  // Callers cannot override central authentication.
  headers.set(
    "Authorization",
    `Bearer ${requireAccessToken()}`
  );

  return headers;
}


async function readError(response, fallback) {
  try {
    const payload = await response.json();

    if (
      payload &&
      typeof payload.detail === "string" &&
      payload.detail.trim()
    ) {
      return payload.detail;
    }
  } catch {
    // Use non-sensitive fallback.
  }

  return fallback;
}


export async function apiFetch(path, options = {}) {
  const response = await fetch(
    `${API_BASE}${path}`,
    {
      ...options,
      headers: buildHeaders(options),
    }
  );

  if (!response.ok) {
    throw new Error(
      await readError(
        response,
        `API error: ${response.status}`
      )
    );
  }

  const responseText = await response.text();

  if (!responseText) {
    return null;
  }

  return JSON.parse(responseText);
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


export function apiDelete(path) {
  return apiFetch(path, {
    method: "DELETE",
  });
}


export function apiPatch(path, data = {}) {
  return apiFetch(path, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}


export function apiUpload(path, formData) {
  return apiFetch(path, {
    method: "POST",
    body: formData,
  });
}


export async function apiDownload(path) {
  const response = await fetch(
    `${API_BASE}${path}`,
    {
      method: "GET",
      headers: buildHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error(
      await readError(
        response,
        `Download error: ${response.status}`
      )
    );
  }

  return response.blob();
}
