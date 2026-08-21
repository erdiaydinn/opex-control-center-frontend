import { apiGet, apiPost } from "../../api/client.js";
import { getAuthorizationSnapshot } from "../../auth/authorizationStore.js";

const LEGACY_QUEUE_KEY = "opex_inventory_v20_offline_queue";
const QUEUE_KEY_PREFIX = "opex_inventory_v20_offline_queue_tenant";
const DEVICE_KEY = "opex_inventory_v20_device_id";

function currentInventoryTenantId({ required = true } = {}) {
  const tenantId = String(getAuthorizationSnapshot()?.tenantId || "").trim();
  if (!tenantId && required) {
    throw new Error("Inventory tenant context unavailable");
  }
  return tenantId;
}

function queueKey(tenantId) {
  return `${QUEUE_KEY_PREFIX}:${tenantId}`;
}

function purgeLegacyUnscopedQueue() {
  // Never replay the historical unscoped queue. It has no trustworthy tenant
  // provenance and therefore cannot safely cross an authentication transition.
  localStorage.removeItem(LEGACY_QUEUE_KEY);
}

function readTenantQueue(tenantId) {
  try {
    const parsed = JSON.parse(localStorage.getItem(queueKey(tenantId)) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeTenantQueue(tenantId, queue) {
  localStorage.setItem(queueKey(tenantId), JSON.stringify(queue));
}

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
  const tenantId = currentInventoryTenantId();
  purgeLegacyUnscopedQueue();
  const queue = readTenantQueue(tenantId);
  queue.push({
    tenantId,
    documentId,
    scan,
    queuedAt: new Date().toISOString(),
  });
  writeTenantQueue(tenantId, queue);
  return queue.length;
}

export function pendingOfflineScans() {
  const tenantId = currentInventoryTenantId({ required: false });
  if (!tenantId) return 0;
  purgeLegacyUnscopedQueue();
  return readTenantQueue(tenantId).filter((item) => item?.tenantId === tenantId).length;
}

export async function flushOfflineScans() {
  const tenantId = currentInventoryTenantId();
  purgeLegacyUnscopedQueue();
  const queue = readTenantQueue(tenantId);
  const pending = [];
  let synced = 0;
  let blocked = 0;

  for (const item of queue) {
    // A namespaced key is not sufficient authority by itself: refuse replay of
    // malformed/tampered entries whose embedded tenant provenance disagrees.
    if (item?.tenantId !== tenantId) {
      pending.push(item);
      blocked += 1;
      continue;
    }

    try {
      await sendServerScan(item.documentId, {
        ...item.scan,
        source: "OFFLINE_SYNC",
      });
      synced += 1;
    } catch {
      pending.push(item);
    }
  }

  writeTenantQueue(tenantId, pending);
  return { synced, pending: pending.length, blocked };
}
