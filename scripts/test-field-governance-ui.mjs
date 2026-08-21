import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(path, "utf8");

const app = read("src/App.jsx");
const workspace = read("src/modules/field-intelligence/FieldGovernanceWorkspace.jsx");
const messages = read("src/modules/field-intelligence/fieldGovernanceMessages.js");
const css = read("src/modules/field-intelligence/field-governance.css");
const routes = read("services/core-api/app/field_governance_routes.py");

assert.match(app, /path="\/field-intelligence\/governance"/);
assert.match(app, /ProtectedRoute moduleKey="field_intelligence"/);
assert.match(app, /FieldGovernanceWorkspace/);

for (const path of [
  "/v1/field/bootstrap",
  "/v1/field/promotions?limit=100",
  "/v1/field/governance/targeting/",
  "/recurrence",
  "/exempt",
  "/v1/field/governance/exports",
]) {
  assert.ok(workspace.includes(path), `governance workspace missing API contract ${path}`);
}

assert.doesNotMatch(workspace, /tenant_id\s*:/, "governance browser must not supply tenant authority");
assert.doesNotMatch(workspace, /role\s*:/, "governance browser must not supply role authority");
assert.doesNotMatch(workspace, /location_ids\s*:/, "governed targeting must not accept browser-authored location lists");
assert.match(workspace, /canAction\("field_intelligence", "manageRecurrence"\)/);
assert.match(workspace, /canAction\("field_intelligence", "exemptTarget"\)/);
assert.match(workspace, /canAction\("field_intelligence", "exportResults"\)/);

for (const permission of [
  "action:field_intelligence:manageRecurrence",
  "action:field_intelligence:exemptTarget",
  "action:field_intelligence:approveExport",
]) {
  assert.ok(routes.includes(permission), `Core governance route missing ${permission}`);
}

for (const route of [
  "/templates/{template_id}/{template_version}/retire",
  "/missions/{mission_id}/recurrence",
  "/missions/{mission_id}/targets/{location_id}/exempt",
  "/targeting/{criterion}",
  "/exports",
  "/exports/{export_request_id}/decision",
]) {
  assert.ok(routes.includes(route), `Core Field governance route missing ${route}`);
}

for (const locale of ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"]) {
  assert.ok(messages.includes(`${JSON.stringify(locale)}:`) || messages.includes(`${locale}:`), `governance messages missing locale ${locale}`);
}
assert.match(messages, /translateFieldGovernance/);

for (const requirement of [
  "min-height: 48px",
  ":focus-visible",
  "prefers-reduced-motion",
  "forced-colors",
  '[dir="rtl"]',
]) {
  assert.ok(css.includes(requirement), `governance accessibility rule missing ${requirement}`);
}

assert.match(workspace, /data-eay-product-state="loading"/);
assert.match(workspace, /data-eay-product-state="error"/);
assert.match(workspace, /data-eay-product-state="empty"/);
assert.match(workspace, /truthBoundary/);

console.log("Field governance UI contract passed");
