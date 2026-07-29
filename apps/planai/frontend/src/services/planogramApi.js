const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function buildScenePayload(planogram) { return request("/scene/build", { method: "POST", body: JSON.stringify({ planogram }) }); }
export function validateStrictRules(planogram) { return request("/validate-strict-rules", { method: "POST", body: JSON.stringify({ planogram }) }); }
export function generatePlanogram(payload) { return request("/generate-planogram", { method: "POST", body: JSON.stringify(payload) }); }
export { API_BASE };
