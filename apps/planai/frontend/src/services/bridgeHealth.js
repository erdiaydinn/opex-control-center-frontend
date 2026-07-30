export async function checkUrl(url, timeoutMs = 1800) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    await fetch(url, { method: "GET", signal: controller.signal, mode: "no-cors" });
    clearTimeout(timer);
    return { ok: true, url };
  } catch (error) {
    clearTimeout(timer);
    return { ok: false, url, error: error?.message || "offline" };
  }
}

export async function getPlanogramBridgeHealth({ planaiFrontend = "http://localhost:5174", planaiBackend = "http://127.0.0.1:8001" } = {}) {
  const [frontend, backend] = await Promise.all([checkUrl(planaiFrontend), checkUrl(`${planaiBackend}/`)]);
  return { ok: frontend.ok, frontend, backend, checkedAt: new Date().toISOString() };
}
