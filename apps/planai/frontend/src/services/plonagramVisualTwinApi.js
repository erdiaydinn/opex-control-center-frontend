const API_BASE = import.meta.env.VITE_PLANOGRAM_API_BASE || "http://127.0.0.1:8001";

async function postJson(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {}),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} failed: ${res.status} ${text}`);
  }

  return res.json();
}

export async function buildVisualTwinScene(payload) {
  return postJson("/visual-twin/scene-payload", payload);
}