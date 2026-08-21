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
  "reviewed_store_dna_v2_preview",
  "recognized_fixtures",
  "buildPlanogramUnifiedTwinScene",
  "<PlanogramTwinSceneRenderer",
  "sceneModel.geometryAuthority",
]) {
  if (!component.includes(needle)) fail(`Scanned Digital Twin shared-scene contract missing: ${needle}`);
}

const sharedRenderer = fs.readFileSync("src/modules/planogram/PlanogramTwinSceneRenderer.jsx", "utf8");
for (const needle of [
  'await import("three")',
  "OrbitControls",
  "RoomEnvironment",
  "ACESFilmicToneMapping",
  'row.type === "picker_entry"',
  "camera.position.set(picker.centerXM, 1.62, picker.centerYM)",
  "data-geometry-authority",
  "sceneModel.sourceKind",
]) {
  if (!sharedRenderer.includes(needle)) fail(`Shared Twin renderer contract missing: ${needle}`);
}
if (/from\s+["']three["']/.test(sharedRenderer)) {
  fail("Shared Twin renderer must preserve dynamic Three.js code splitting.");
}

for (const [source, label] of [
  [component, "scanned component"],
  [sharedRenderer, "shared renderer"],
]) {
  for (const forbidden of [
    "/store-dna/approve",
    "production_authority: true",
    "installation_approval_allowed: true",
    "maker_checker_approved: true",
  ]) {
    if (source.includes(forbidden)) fail(`${label} leaked authority: ${forbidden}`);
  }
}

const workspace = fs.readFileSync("src/modules/planogram/PlanogramScanAnnotationWorkspace.jsx", "utf8");
if (!workspace.includes("<PlanogramScannedDigitalTwin")) {
  fail("Reviewed Store Scan does not open the Scanned Digital Twin.");
}
if (!workspace.includes("reviewedResult?.reviewed_draft_ready")) {
  fail("Scanned Digital Twin is not gated by reviewed draft readiness.");
}

console.log("Planogram reviewed Store Scan unified 3D Digital Twin boundary: PASS");
