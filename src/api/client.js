const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export function getDemoEmail() {
  return localStorage.getItem("opex_demo_email") || "";
}

export async function apiFetch(path, options = {}) {
  const email = getDemoEmail();

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-User-Email": email,
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `API error: ${response.status}`);
  }

  const text = await response.text();

  if (!text) {
    return null;
  }

  return JSON.parse(text);
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
