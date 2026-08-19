import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_SCANNED_TWIN_MESSAGES } from "../src/platform/i18n/planogramScannedTwinMessages.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const englishKeys = Object.keys(PLANOGRAM_SCANNED_TWIN_MESSAGES.en).sort();
for (const { code } of SUPPORTED_LOCALES) {
  const table = PLANOGRAM_SCANNED_TWIN_MESSAGES[code];
  if (!table) fail(`Missing scanned twin locale: ${code}`);
  if (JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(englishKeys)) {
    fail(`Scanned twin locale coverage drifted: ${code}`);
  }
}

const component = fs.readFileSync("src/modules/planogram/PlanogramScannedDigitalTwin.jsx", "utf8");
for (const needle of [
  'import("three")',
  "OrbitControls",
  "reviewed_store_dna_v2_preview",
  "rotation_deg",
  "picker_entry",
  "camera.position.set(picker.center_x_m, 1.62, picker.center_y_m)",
  "recognized_fixtures",
]) {
  if (!component.includes(needle)) fail(`Scanned Digital Twin contract missing: ${needle}`);
}
for (const forbidden of [
  "/store-dna/approve",
  "production_authority: true",
  "installation_approval_allowed: true",
  "maker_checker_approved: true",
]) {
  if (component.includes(forbidden)) fail(`Scanned Digital Twin leaked authority: ${forbidden}`);
}
const workspace = fs.readFileSync("src/modules/planogram/PlanogramScanAnnotationWorkspace.jsx", "utf8");
if (!workspace.includes("<PlanogramScannedDigitalTwin")) {
  fail("Reviewed Store Scan does not open the Scanned Digital Twin.");
}
if (!workspace.includes("reviewedResult?.reviewed_draft_ready")) {
  fail("Scanned Digital Twin is not gated by reviewed draft readiness.");
}

console.log("Planogram reviewed Store Scan 3D Digital Twin boundary: PASS");
