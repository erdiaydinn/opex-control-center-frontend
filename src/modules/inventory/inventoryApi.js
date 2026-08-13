import { apiGet, apiPost } from "../../api/client.js";

const QUEUE_KEY = "opex_inventory_v20_offline_queue";
const DEVICE_KEY = "opex_inventory_v20_device_id";

export function inventoryDeviceId() {
  let value = localStorage.getItem(DEVICE_KEY);
  if (!value) {
    value = `WEB-${crypto.randomUUID()}`;
    localStorage.setItem(DEVICE_KEY, value);
  }
  return value;
}

export function inventoryHealth() {
  return apiGet("/inventory/health");
}

export function createServerDocument(data) {
  return apiPost("/inventory/documents", data);
}

export function lockServerLocation(documentId, location, deviceId = inventoryDeviceId()) {
  return apiPost(`/inventory/documents/${encodeURIComponent(documentId)}/locations/${encodeURIComponent(location)}/lock`, {
    device_id: deviceId,
    ttl_seconds: 900,
  });
}

export function sendServerScan(documentId, scan) {
  return apiPost(`/inventory/documents/${encodeURIComponent(documentId)}/scans`, scan);
}

export function enqueueOfflineScan(documentId, scan) {
  const queue = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  queue.push({ documentId, scan, queuedAt: new Date().toISOString() });
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  return queue.length;
}

export function pendingOfflineScans() {
  return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]").length;
}

export async function flushOfflineScans() {
  const queue = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  const pending = [];
  let synced = 0;
  for (const item of queue) {
    try {
      await sendServerScan(item.documentId, { ...item.scan, source: "OFFLINE_SYNC" });
      synced += 1;
    } catch {
      pending.push(item);
    }
  }
  localStorage.setItem(QUEUE_KEY, JSON.stringify(pending));
  return { synced, pending: pending.length };
}
