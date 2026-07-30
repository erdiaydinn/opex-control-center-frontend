
const API_BASE = import.meta?.env?.VITE_PLONAGRAM_API || "http://127.0.0.1:8001";

export async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn("PLONAGRAM_API_GET_FALLBACK", path, err.message);
    return null;
  }
}

export async function apiPost(path, body = {}) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn("PLONAGRAM_API_POST_FALLBACK", path, err.message);
    return null;
  }
}
