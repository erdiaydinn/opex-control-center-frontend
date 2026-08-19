import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_FIXTURE_BINDING_MESSAGES } from "../src/platform/i18n/planogramFixtureBindingMessages.js";
import {
  normalizePlanogramFixtureBindings,
  safePlanogramFixtureLayoutPreview,
} from "../src/modules/planogram/planogramFixtureBindings.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const englishKeys = Object.keys(PLANOGRAM_FIXTURE_BINDING_MESSAGES.en).sort();
for (const { code } of SUPPORTED_LOCALES) {
  const table = PLANOGRAM_FIXTURE_BINDING_MESSAGES[code];
  if (!table) fail(`Missing fixture binding locale: ${code}`);
  if (JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(englishKeys)) {
    fail(`Fixture binding locale coverage drifted: ${code}`);
  }
}

const valid = {
  bindings: [{
    scan_fixture_element_id: "fixture-1",
    fixture_id: "GONDOLA-001",
    aisle_id: "A01",
    side: "L",
    position: 1,
    fixture_type: "steel_rack",
    storage_type: "AMBIENT",
    shelf_count: 3,
    fixture_width_cm: 120,
    fixture_height_cm: 180,
    fixture_depth_cm: 60,
    shelf_width_cm: 110,
    shelf_height_cm: 50,
    shelf_depth_cm: 50,
    shelf_max_weight_kg: 45,
    shelf_zone_types: ["bottom", "eye", "top"],
    source_ref: "fixture-master://GONDOLA-001/v2",
    attested: true,
  }],
};
const normalized = normalizePlanogramFixtureBindings(valid, ["fixture-1"]);
if (!normalized || normalized[0].fixture_id !== "GONDOLA-001") {
  fail("Valid scanned fixture binding was rejected.");
}
for (const forged of [
  { bindings: [{ ...valid.bindings[0], attested: false }] },
  { bindings: [{ ...valid.bindings[0], scan_fixture_element_id: "unknown-fixture" }] },
  { bindings: [{ ...valid.bindings[0], shelf_zone_types: ["eye"] }] },
  { bindings: [{ ...valid.bindings[0], source_ref: "" }] },
  { bindings: [valid.bindings[0], { ...valid.bindings[0], fixture_id: "GONDOLA-002" }] },
]) {
  if (normalizePlanogramFixtureBindings(forged, ["fixture-1"]) !== null) {
    fail("Unsafe/ambiguous scanned fixture binding was accepted.");
  }
}

const fingerprint = "a".repeat(64);
const safeResponse = {
  preview_only: true,
  input_authority: "fingerprint_bound_human_fixture_binding_unattested",
  store_dna_approval_allowed: false,
  physical_layout_release_allowed: false,
  production_release_allowed: false,
  installation_approval_allowed: false,
  capex_approval_allowed: false,
  result: {
    scan_fingerprint: fingerprint,
    physical_layout_authority: false,
    store_dna_authority: false,
    v4_v5_production_eligible: false,
    relocation_execution_allowed: false,
    installation_approval_allowed: false,
    capex_approval_allowed: false,
  },
};
if (!safePlanogramFixtureLayoutPreview(safeResponse, fingerprint)) {
  fail("Safe scanned fixture layout response was rejected.");
}
for (const mutate of [
  (row) => { row.physical_layout_release_allowed = true; },
  (row) => { row.result.physical_layout_authority = true; },
  (row) => { row.result.v4_v5_production_eligible = true; },
  (row) => { row.result.relocation_execution_allowed = true; },
  (row) => { row.result.scan_fingerprint = "b".repeat(64); },
]) {
  const forged = structuredClone(safeResponse);
  mutate(forged);
  if (safePlanogramFixtureLayoutPreview(forged, fingerprint) !== null) {
    fail("Fixture binding UI accepted an authority/fingerprint leak.");
  }
}

const panel = fs.readFileSync("src/modules/planogram/PlanogramFixtureBindingPanel.jsx", "utf8");
for (const needle of [
  "/v1/planogram/store-scan/fixture-layout-preview",
  "safePlanogramFixtureLayoutPreview",
  "normalizePlanogramFixtureBindings",
  "recognized_fixtures",
  "fixture_binding_coverage_pct",
  "rotatedRectSvgPoints",
]) {
  if (!panel.includes(needle)) fail(`Fixture binding UI contract missing: ${needle}`);
}
const workspace = fs.readFileSync("src/modules/planogram/PlanogramScanAnnotationWorkspace.jsx", "utf8");
if (!workspace.includes("<PlanogramFixtureBindingPanel")) {
  fail("Reviewed Store Scan does not expose fixture catalog binding.");
}
if (!workspace.includes("reviewedResult?.reviewed_draft_ready")) {
  fail("Fixture binding is not gated by reviewed scan readiness.");
}

console.log("Planogram scanned fixture catalog binding boundary: PASS");
