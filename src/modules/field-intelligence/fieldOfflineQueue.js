const DB_NAME = "eay-field-offline-v1";
const DB_VERSION = 1;
const EVENTS = "events";
const META = "meta";
const ATTACHMENTS = "attachments";

function requireBrowserCapability(condition, message) {
  if (!condition) throw new Error(message);
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("IndexedDB request failed"));
  });
}

function transactionDone(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("IndexedDB transaction failed"));
    transaction.onabort = () => reject(transaction.error || new Error("IndexedDB transaction aborted"));
  });
}

export async function openFieldOfflineDb() {
  requireBrowserCapability(typeof indexedDB !== "undefined", "IndexedDB is required for Field offline mode");
  const request = indexedDB.open(DB_NAME, DB_VERSION);
  request.onupgradeneeded = () => {
    const db = request.result;
    if (!db.objectStoreNames.contains(EVENTS)) {
      const events = db.createObjectStore(EVENTS, { keyPath: "clientSubmissionId" });
      events.createIndex("state", "state", { unique: false });
      events.createIndex("capturedAt", "capturedAt", { unique: false });
      events.createIndex("deviceSequence", ["deviceId", "deviceSequence"], { unique: true });
    }
    if (!db.objectStoreNames.contains(META)) db.createObjectStore(META, { keyPath: "key" });
    if (!db.objectStoreNames.contains(ATTACHMENTS)) {
      const attachments = db.createObjectStore(ATTACHMENTS, { keyPath: "attachmentId" });
      attachments.createIndex("eventId", "eventId", { unique: false });
      attachments.createIndex("state", "state", { unique: false });
    }
  };
  return requestResult(request);
}

async function getMeta(key) {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(META, "readonly");
  const value = await requestResult(tx.objectStore(META).get(key));
  await transactionDone(tx);
  db.close();
  return value?.value;
}

async function setMeta(key, value) {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(META, "readwrite");
  tx.objectStore(META).put({ key, value });
  await transactionDone(tx);
  db.close();
}

export async function getOrCreateFieldDeviceId() {
  let value = await getMeta("deviceId");
  if (value) return value;
  requireBrowserCapability(globalThis.crypto?.randomUUID, "Secure random UUID support is required");
  value = globalThis.crypto.randomUUID();
  await setMeta("deviceId", value);
  return value;
}

async function nextDeviceSequence() {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(META, "readwrite");
  const store = tx.objectStore(META);
  const current = await requestResult(store.get("deviceSequence"));
  const next = Number(current?.value || 0) + 1;
  store.put({ key: "deviceSequence", value: next });
  await transactionDone(tx);
  db.close();
  return next;
}

async function getOrCreateAttachmentKey() {
  let key = await getMeta("attachmentKey");
  if (key) return key;
  requireBrowserCapability(globalThis.crypto?.subtle, "WebCrypto is required for encrypted offline attachments");
  key = await globalThis.crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  await setMeta("attachmentKey", key);
  return key;
}

async function sha256Hex(buffer) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function encryptAttachment(file) {
  requireBrowserCapability(file instanceof Blob, "Attachment must be a Blob or File");
  const key = await getOrCreateAttachmentKey();
  const plaintext = await file.arrayBuffer();
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await globalThis.crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return {
    ciphertext,
    iv: iv.buffer,
    fingerprint: await sha256Hex(plaintext),
    mimeType: file.type || "application/octet-stream",
    size: file.size,
  };
}

async function decryptAttachment(record) {
  const key = await getOrCreateAttachmentKey();
  const plaintext = await globalThis.crypto.subtle.decrypt(
    { name: "AES-GCM", iv: new Uint8Array(record.iv) },
    key,
    record.ciphertext,
  );
  return new Blob([plaintext], { type: record.mimeType });
}

function assertSafePayload(value, path = "payload") {
  if (typeof value === "string") {
    if (/^data:/i.test(value) || /;base64,/i.test(value)) throw new Error(`${path} may not contain raw/base64 attachment data`);
    return;
  }
  if (value instanceof Blob) throw new Error(`${path} may not contain raw Blob/File data`);
  if (Array.isArray(value)) {
    value.forEach((entry, index) => assertSafePayload(entry, `${path}[${index}]`));
    return;
  }
  if (value && typeof value === "object") {
    Object.entries(value).forEach(([key, entry]) => assertSafePayload(entry, `${path}.${key}`));
  }
}

export async function enqueueFieldOfflineEvidence({ missionId, locationId, targetFingerprint, payload, attachments = [] }) {
  requireBrowserCapability(globalThis.crypto?.randomUUID && globalThis.crypto?.subtle, "Secure WebCrypto support is required");
  assertSafePayload(payload);
  const deviceId = await getOrCreateFieldDeviceId();
  const deviceSequence = await nextDeviceSequence();
  const clientSubmissionId = globalThis.crypto.randomUUID();
  const capturedAt = new Date().toISOString();

  const encryptedAttachments = [];
  for (const attachment of attachments) {
    const encrypted = await encryptAttachment(attachment.file);
    encryptedAttachments.push({
      attachmentId: globalThis.crypto.randomUUID(),
      eventId: clientSubmissionId,
      fieldKey: attachment.fieldKey,
      captureSource: attachment.captureSource || "camera_claim",
      captureSessionId: globalThis.crypto.randomUUID(),
      ...encrypted,
      state: "pending",
      attempts: 0,
      lastError: null,
      receiptId: null,
      receiptMediaType: null,
      receiptByteSize: null,
    });
  }

  const db = await openFieldOfflineDb();
  const tx = db.transaction([EVENTS, ATTACHMENTS], "readwrite");
  tx.objectStore(EVENTS).add({
    clientSubmissionId,
    missionId,
    locationId,
    targetFingerprint,
    payload,
    deviceId,
    deviceSequence,
    capturedAt,
    state: encryptedAttachments.length ? "awaiting_attachment" : "queued",
    attempts: 0,
    lastError: null,
  });
  const attachmentStore = tx.objectStore(ATTACHMENTS);
  encryptedAttachments.forEach((attachment) => attachmentStore.add(attachment));
  await transactionDone(tx);
  db.close();
  return { clientSubmissionId, deviceId, deviceSequence };
}

export async function listFieldOfflineQueue() {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(EVENTS, "readonly");
  const items = await requestResult(tx.objectStore(EVENTS).getAll());
  await transactionDone(tx);
  db.close();
  return items.sort((a, b) => a.deviceSequence - b.deviceSequence);
}

async function attachmentsForEvent(eventId) {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(ATTACHMENTS, "readonly");
  const records = await requestResult(tx.objectStore(ATTACHMENTS).index("eventId").getAll(eventId));
  await transactionDone(tx);
  db.close();
  return records;
}

async function putEvent(event) {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(EVENTS, "readwrite");
  tx.objectStore(EVENTS).put(event);
  await transactionDone(tx);
  db.close();
}

async function putAttachment(attachment) {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(ATTACHMENTS, "readwrite");
  tx.objectStore(ATTACHMENTS).put(attachment);
  await transactionDone(tx);
  db.close();
}

async function removeEvent(eventId) {
  const attachments = await attachmentsForEvent(eventId);
  const db = await openFieldOfflineDb();
  const tx = db.transaction([EVENTS, ATTACHMENTS], "readwrite");
  tx.objectStore(EVENTS).delete(eventId);
  attachments.forEach((attachment) => tx.objectStore(ATTACHMENTS).delete(attachment.attachmentId));
  await transactionDone(tx);
  db.close();
}

async function prepareAttachments(event, uploadAttachment) {
  const attachments = await attachmentsForEvent(event.clientSubmissionId);
  if (!attachments.length) return { ...event, state: "queued", evidenceObjects: [] };

  const nextPayload = structuredClone(event.payload);
  const evidenceObjects = [];
  for (const attachment of attachments) {
    if (attachment.state !== "uploaded") {
      try {
        const blob = await decryptAttachment(attachment);
        const result = await uploadAttachment({
          blob,
          fingerprint: attachment.fingerprint,
          fieldKey: attachment.fieldKey,
          captureSource: attachment.captureSource,
          captureSessionId: attachment.captureSessionId,
          clientSubmissionId: event.clientSubmissionId,
          missionId: event.missionId,
          locationId: event.locationId,
        });
        if (
          !result?.receipt_id
          || result?.sha256 !== attachment.fingerprint
          || result?.media_type !== attachment.mimeType
          || Number(result?.byte_size) !== Number(attachment.size)
        ) {
          throw new Error("private attachment uploader returned an invalid server receipt contract");
        }
        attachment.state = "uploaded";
        attachment.receiptId = result.receipt_id;
        attachment.receiptMediaType = result.media_type;
        attachment.receiptByteSize = Number(result.byte_size);
        attachment.attempts += 1;
        attachment.lastError = null;
        await putAttachment(attachment);
      } catch (error) {
        attachment.state = "retry";
        attachment.attempts += 1;
        attachment.lastError = error?.message || "attachment upload failed";
        await putAttachment(attachment);
        const blocked = { ...event, state: "awaiting_attachment", attempts: event.attempts + 1, lastError: attachment.lastError };
        await putEvent(blocked);
        return blocked;
      }
    }
    nextPayload[attachment.fieldKey] = attachment.receiptId;
    evidenceObjects.push({
      receipt_id: attachment.receiptId,
      field_key: attachment.fieldKey,
      sha256: attachment.fingerprint,
      media_type: attachment.receiptMediaType || attachment.mimeType,
      byte_size: attachment.receiptByteSize || attachment.size,
      capture_session_id: attachment.captureSessionId,
    });
  }

  const ready = { ...event, payload: nextPayload, evidenceObjects, state: "queued", lastError: null };
  await putEvent(ready);
  return ready;
}

export async function drainFieldOfflineQueue({ syncBatch, uploadAttachment, batchSize = 25 }) {
  requireBrowserCapability(typeof syncBatch === "function", "syncBatch adapter is required");
  requireBrowserCapability(typeof uploadAttachment === "function", "private attachment uploader adapter is required");
  if (typeof navigator !== "undefined" && navigator.onLine === false) return { synced: 0, remaining: (await listFieldOfflineQueue()).length };

  const queued = await listFieldOfflineQueue();
  const ready = [];
  for (const event of queued) {
    if (["conflict", "stale_assignment"].includes(event.state)) continue;
    const prepared = await prepareAttachments(event, uploadAttachment);
    if (prepared.state === "queued") ready.push(prepared);
    if (ready.length >= batchSize) break;
  }
  if (!ready.length) return { synced: 0, remaining: (await listFieldOfflineQueue()).length };

  const response = await syncBatch({
    events: ready.map((event) => ({
      client_submission_id: event.clientSubmissionId,
      mission_id: event.missionId,
      location_id: event.locationId,
      device_id: event.deviceId,
      device_sequence: event.deviceSequence,
      target_fingerprint: event.targetFingerprint,
      captured_at: event.capturedAt,
      payload: event.payload,
      evidence_objects: event.evidenceObjects || [],
    })),
  });

  let synced = 0;
  for (const outcome of response?.outcomes || []) {
    const event = ready.find((candidate) => candidate.clientSubmissionId === outcome.client_submission_id);
    if (!event) continue;
    if (["accepted", "idempotent_replay"].includes(outcome.decision)) {
      await removeEvent(event.clientSubmissionId);
      synced += 1;
      continue;
    }
    const nextState = outcome.decision === "stale_assignment" ? "stale_assignment" : outcome.decision === "conflict" ? "conflict" : outcome.decision === "blocked" ? "blocked" : "queued";
    await putEvent({ ...event, state: nextState, attempts: event.attempts + 1, lastError: outcome.reason || outcome.decision });
  }

  return { synced, remaining: (await listFieldOfflineQueue()).length };
}

export async function retryBlockedFieldOfflineEvent(clientSubmissionId) {
  const db = await openFieldOfflineDb();
  const tx = db.transaction(EVENTS, "readwrite");
  const store = tx.objectStore(EVENTS);
  const event = await requestResult(store.get(clientSubmissionId));
  if (event && event.state === "blocked") store.put({ ...event, state: "queued", lastError: null });
  await transactionDone(tx);
  db.close();
}
