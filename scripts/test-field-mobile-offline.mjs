import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(path, "utf8");

const app = read("src/App.jsx");
const mobile = read("src/modules/field-intelligence/FieldMobileCapture.jsx");
const queue = read("src/modules/field-intelligence/fieldOfflineQueue.js");
const messages = read("src/modules/field-intelligence/fieldMobileMessages.js");
const css = read("src/modules/field-intelligence/field-mobile.css");
const routes = read("services/core-api/app/intelligence_routes.py");
const uploadRoutes = read("services/core-api/app/field_evidence_object_routes.py");
const uploadAuthority = read("services/core-api/app/modules/field_intelligence/evidence_object_upload.py");
const integrity = read("services/core-api/app/modules/field_intelligence/evidence_integrity.py");
const schemas = read("services/core-api/app/modules/field_intelligence/schemas.py");
const offline = read("services/core-api/app/modules/field_intelligence/mobile_offline.py");
const migration = read("services/core-api/alembic/versions/0021_field_mobile_offline.py");
const uploadMigration = read("services/core-api/alembic/versions/0024_field_evidence_object_upload.py");
const catalog = JSON.parse(read("config/module_catalog.json"));

assert.match(app, /path="\/field-intelligence\/mobile"/);
assert.match(app, /ProtectedRoute moduleKey="field_intelligence"/);
assert.match(app, /FieldMobileCapture/);
assert.match(mobile, /\/v1\/field\/offline-sync/);
assert.match(mobile, /\/v1\/field\/evidence-objects\//);
assert.match(mobile, /X-EAY-Content-SHA256/);
assert.match(mobile, /window\.addEventListener\("online"/);
assert.match(mobile, /window\.addEventListener\("offline"/);
assert.match(mobile, /capture="environment"/);
assert.match(mobile, /deviceTrustBoundary/);
assert.match(mobile, /cameraTrustBoundary/);
assert.doesNotMatch(mobile, /private_evidence_transport_unavailable/);

assert.match(queue, /indexedDB\.open/);
assert.doesNotMatch(queue, /localStorage|sessionStorage/);
assert.match(queue, /AES-GCM/);
assert.match(queue, /generateKey\([^;]+false, \["encrypt", "decrypt"\]/s, "offline attachment key must remain non-extractable");
assert.match(queue, /SHA-256/);
assert.match(queue, /deviceSequence/);
assert.match(queue, /deviceId/);
assert.match(queue, /awaiting_attachment/);
assert.match(queue, /stale_assignment/);
assert.match(queue, /conflict/);
assert.match(queue, /idempotent_replay/);
assert.match(queue, /raw\/base64 attachment data/);
assert.match(queue, /evidence_objects/);
assert.match(queue, /receipt_id/);
assert.match(queue, /capture_session_id/);
assert.doesNotMatch(queue, /readAsDataURL|data:image/);

for (const token of ["blocked", "conflict", "staleAssignment", "awaitingAttachment", "syncNow", "reconnect"]) {
  assert.ok(messages.includes(token), `mobile locale contract missing ${token}`);
}
assert.match(messages, /FIELD_MOBILE_MESSAGES = Object\.freeze\(\{ tr, en, de, ar, fr, es, it, nl, pl, "pt-BR": ptBR \}\)/);

assert.match(routes, /@router\.post\("\/field\/offline-sync"\)/);
assert.match(routes, /@router\.put\("\/field\/templates\/\{template_id\}\/\{template_version\}\/evidence-policy"\)/);
assert.match(routes, /canonical App Attest\/Play Integrity\/camera attestation providers/);
assert.doesNotMatch(routes, /trusted_device_ids\s*=\s*payload|camera_attested_submission_ids\s*=\s*payload/);
assert.match(uploadRoutes, /@router\.post\("\/\{field_key\}"/);
assert.match(uploadRoutes, /action:field_intelligence:submitEvidence/);
assert.match(uploadRoutes, /production_storage_evidence": False/);
assert.match(uploadAuthority, /OPEX_FIELD_EVIDENCE_STORE_URL/);
assert.match(uploadAuthority, /OPEX_FIELD_EVIDENCE_STORE_TOKEN_FILE/);
assert.match(uploadAuthority, /follow_redirects=False/);
assert.match(uploadAuthority, /private Field evidence store is not configured/);
assert.match(uploadAuthority, /storage_receipt_hash/);
assert.doesNotMatch(uploadRoutes, /storage_receipt\s*:/, "raw storage provider receipt must not be returned by the browser route");

assert.match(schemas, /class OfflineEvidenceEvent/);
assert.match(schemas, /device_sequence: int = Field\(gt=0\)/);
assert.match(schemas, /target_fingerprint: str = Field\(pattern=r"\^\[0-9a-f\]\{64\}\$"\)/);
assert.match(schemas, /class OfflineSyncBatch/);
assert.match(schemas, /max_length=100/);
assert.match(schemas, /class EvidencePolicy/);
assert.match(schemas, /evidence_objects: tuple\[EvidenceObjectClaim/);

assert.match(offline, /decision": "idempotent_replay"/);
assert.match(offline, /decision": "conflict"/);
assert.match(offline, /decision": "stale_assignment"/);
assert.match(offline, /decision": "blocked"/);
assert.match(offline, /verify_evidence_authority/);
assert.match(offline, /authority_fingerprint/);
assert.match(offline, /field_template_evidence_policies/);
assert.match(integrity, /client_submission_id=CAST\(:client_submission_id AS UUID\)/);
assert.match(integrity, /field_key=:field_key/);
assert.match(integrity, /managed-device policy requires authoritative device attestation/);
assert.match(integrity, /camera-only policy requires authoritative capture attestation/);

assert.match(migration, /down_revision: str = "0020_field_ui_operations"/);
assert.match(migration, /field_offline_receipts/);
assert.match(migration, /field_template_evidence_policies/);
assert.match(migration, /uq_field_offline_device_sequence/);
assert.match(migration, /uq_field_offline_client_submission/);
assert.match(migration, /FORCE ROW LEVEL SECURITY/);
assert.match(migration, /append_only/);
assert.match(uploadMigration, /down_revision: str = "0023_field_governed_promotion"/);
assert.match(uploadMigration, /client_submission_id/);
assert.match(uploadMigration, /storage_receipt_hash/);
assert.match(uploadMigration, /GRANT INSERT ON TABLE field_evidence_object_receipts/);

assert.match(css, /min-height:\s*48px/);
assert.match(css, /:focus-visible/);
assert.match(css, /prefers-reduced-motion/);
assert.match(css, /forced-colors/);
assert.match(css, /\[dir="rtl"\]/);

const fieldProduct = catalog.commercial_modules.find((item) => item.key === "field_intelligence");
assert.ok(fieldProduct, "Field product catalog entry is required");
assert.ok(fieldProduct.channels.includes("mobile"), "mobile channel must be enabled only after the real item 9 surface exists");
for (const capability of [
  "mobile_web_offline_queue",
  "reconnect_replay",
  "device_sequence_conflict_detection",
  "encrypted_attachment_retry",
  "stale_assignment_detection",
  "camera_only_policy_gate",
  "managed_device_policy_gate",
]) {
  assert.ok(fieldProduct.capabilities.includes(capability), `missing mobile Field capability ${capability}`);
}

console.log("Field Intelligence mobile/offline receipt-authority contract passed");
