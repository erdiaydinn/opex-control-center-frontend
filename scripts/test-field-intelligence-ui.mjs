import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(path, "utf8");

const app = read("src/App.jsx");
const registry = read("src/modules/control-center/commandCenterModules.js");
const workspace = read("src/modules/field-intelligence/FieldIntelligenceWorkspace.jsx");
const messages = read("src/modules/field-intelligence/fieldMessages.js");
const css = read("src/modules/field-intelligence/field-intelligence.css");
const schemas = read("services/core-api/app/modules/field_intelligence/schemas.py");
const canonicalRoutes = read("services/core-api/app/intelligence_routes.py");
const migration = read("services/core-api/alembic/versions/0020_field_ui_operations.py");
const catalog = JSON.parse(read("config/module_catalog.json"));

assert.match(app, /path="\/field-intelligence"/);
assert.match(app, /ProtectedRoute moduleKey="field_intelligence"/);
assert.match(app, /FieldIntelligenceWorkspace/);

assert.match(registry, /moduleKey: "field_intelligence"/);
assert.match(registry, /route: "\/field-intelligence"/);
assert.match(registry, /translateField\(locale, "moduleTitle"\)/);

const fieldProduct = catalog.commercial_modules.find((item) => item.key === "field_intelligence");
assert.ok(fieldProduct, "Field Intelligence must be a commercial module");
assert.equal(fieldProduct.standalone, true);
assert.deepEqual(
  fieldProduct.channels,
  ["web", "mobile", "api"],
  "Field channel truth must include the item 9 mobile/offline surface without regressing web/API",
);

for (const capability of [
  "mission_command_center",
  "mission_builder",
  "authoritative_target_snapshots",
  "governed_template_editor",
  "barcode_qr_lot_batch_capture",
  "expiry_quantity_measurement_capture",
  "gps_yes_no_multi_row_capture",
  "evidence_review_and_rework",
  "reminder_and_escalation_intents",
  "field_completion_analytics",
]) {
  assert.ok(fieldProduct.capabilities.includes(capability), `missing Field capability ${capability}`);
}

assert.match(
  messages,
  /FIELD_MESSAGES = Object\.freeze\(\{ tr, en, de, ar, fr, es, it, nl, pl, "pt-BR": ptBR \}\)/,
  "Field locale catalog must stay on the platform ten-locale contract",
);

for (const fieldType of [
  "text",
  "number",
  "select",
  "barcode",
  "qr",
  "photo",
  "lot",
  "batch",
  "expiry",
  "quantity",
  "measurement",
  "gps",
  "yes_no",
  "multi_row",
]) {
  assert.ok(schemas.includes(`"${fieldType}"`), `Core schema missing ${fieldType}`);
  assert.ok(workspace.includes(`"${fieldType}"`), `Field UI missing ${fieldType}`);
}

for (const state of ["loading", "error", "empty", "offline"]) {
  assert.ok(workspace.includes(`state="${state}"`) || workspace.includes(`state={"${state}"}`), `missing ${state} state`);
}
assert.match(workspace, /t\("retry"\)/, "error state must expose retry");
assert.match(workspace, /navigator\.onLine/);
assert.doesNotMatch(workspace, /tenant_id\s*:/, "browser must not submit tenant authority");
assert.doesNotMatch(workspace, /role\s*:/, "browser must not submit role authority");
assert.doesNotMatch(workspace, /FileReader|readAsDataURL|data:image|base64/i, "raw photo transport is forbidden");
assert.match(workspace, /photoUnavailable/);
assert.match(workspace, /crypto\?\.randomUUID|crypto\.randomUUID|randomUUID/);
assert.match(workspace, /\/v1\/field\/bootstrap/);
assert.match(workspace, /\/v1\/field\/missions/);
assert.match(workspace, /\/v1\/field\/evidence/);
assert.match(workspace, /\/v1\/field\/analytics/);
assert.match(workspace, /notification-intents/);

for (const route of [
  "/field/bootstrap",
  "/field/missions/{mission_id}",
  "/field/missions/{mission_id}/activate",
  "/field/missions/{mission_id}/cancel",
  "/field/missions/{mission_id}/targets/{location_id}/evidence",
  "/field/evidence",
  "/field/evidence/{evidence_id}/review",
  "/field/missions/{mission_id}/notification-intents",
  "/field/analytics",
]) {
  assert.ok(canonicalRoutes.includes(route), `canonical Core Field route missing ${route}`);
}
assert.equal(
  fs.existsSync("services/core-api/app/modules/field_intelligence/router.py"),
  false,
  "a second Field router authority must not exist",
);

assert.match(migration, /down_revision: str = "0019_field_intelligence_foundation"/);
assert.match(migration, /field_notification_intents/);
assert.match(migration, /FORCE ROW LEVEL SECURITY/);
assert.match(migration, /uq_field_evidence_client_submission/);
assert.match(migration, /append_only/);

assert.match(css, /min-height:\s*48px/);
assert.match(css, /:focus-visible/);
assert.match(css, /prefers-reduced-motion/);
assert.match(css, /forced-colors/);
assert.match(css, /\[dir="rtl"\]/);

console.log("Field Intelligence UI contract passed");
