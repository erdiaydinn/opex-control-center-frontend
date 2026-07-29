const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

async function parseJson(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.detail || data?.message || `HTTP ${res.status}`);
  }
  return data;
}

export async function uploadAndMergeABC(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/data-pipeline/abc/upload-merge`, {
    method: "POST",
    body: fd,
  });
  return parseJson(res);
}

export async function parseABC(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/data-pipeline/abc/parse`, {
    method: "POST",
    body: fd,
  });
  return parseJson(res);
}

export async function getCatalogStatus() {
  const res = await fetch(`${API_BASE}/data-pipeline/catalog/status`);
  return parseJson(res);
}
