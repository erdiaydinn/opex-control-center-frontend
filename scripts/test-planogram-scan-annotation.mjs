import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_SCAN_ANNOTATION_MESSAGES } from "../src/platform/i18n/planogramScanAnnotationMessages.js";
import { PLANOGRAM_SCAN_UNCERTAINTY_MESSAGES } from "../src/platform/i18n/planogramScanUncertaintyMessages.js";
import {
  annotationToolDefaults,
  PLANOGRAM_SCAN_ANNOTATION_TOOLS,
  safePlanogramScanAnnotationPreview,
} from "../src/modules/planogram/planogramScanAnnotation.js";
import {
  buildPlanogramUncertaintyResolutions,
  isPlanogramUncertaintyReviewComplete,
  PLANOGRAM_SCAN_UNCERTAINTY_TYPES,
} from "../src/modules/planogram/planogramScanUncertainty.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const englishKeys = Object.keys(PLANOGRAM_SCAN_ANNOTATION_MESSAGES.en).sort();
const uncertaintyEnglishKeys = Object.keys(PLANOGRAM_SCAN_UNCERTAINTY_MESSAGES.en).sort();
for (const { code } of SUPPORTED_LOCALES) {
  const table = PLANOGRAM_SCAN_ANNOTATION_MESSAGES[code];
  if (!table) fail(`Missing scan annotation locale: ${code}`);
  if (JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(englishKeys)) {
    fail(`Scan annotation locale coverage drifted: ${code}`);
  }
  const uncertaintyTable = PLANOGRAM_SCAN_UNCERTAINTY_MESSAGES[code];
  if (!uncertaintyTable) fail(`Missing scan uncertainty locale: ${code}`);
  if (JSON.stringify(Object.keys(uncertaintyTable).sort()) !== JSON.stringify(uncertaintyEnglishKeys)) {
    fail(`Scan uncertainty locale coverage drifted: ${code}`);
  }
}

for (const required of ["picker_entry", "picker_exit", "inbound", "dispatch", "no_go", "technical", "emergency_exit"]) {
  if (!PLANOGRAM_SCAN_ANNOTATION_TOOLS.includes(required)) fail(`Missing annotation tool: ${required}`);
  const defaults = annotationToolDefaults(required);
  if (!(defaults.widthM > 0) || !(defaults.depthM > 0)) fail(`Invalid annotation defaults: ${required}`);
}
for (const requiredType of ["wall", "column", "door", "opening", "chiller", "freezer", "fixture"]) {
  if (!PLANOGRAM_SCAN_UNCERTAINTY_TYPES.includes(requiredType)) fail(`Missing uncertainty type: ${requiredType}`);
}

const uncertainRegions = [
  { element_id: "uncertain-1", source_element_type: "unknown" },
  { element_id: "uncertain-2", source_element_type: "fixture" },
];
const completeChoices = {
  "uncertain-1": { decision: "confirm", classified_type: "chiller" },
  "uncertain-2": { decision: "reject" },
};
if (!isPlanogramUncertaintyReviewComplete(uncertainRegions, completeChoices)) {
  fail("Complete uncertainty review was rejected.");
}
const uncertaintyResolutions = buildPlanogramUncertaintyResolutions(uncertainRegions, completeChoices);
if (uncertaintyResolutions.length !== 2) fail("Uncertainty decisions were not normalized.");
if (uncertaintyResolutions[0].classified_type !== "chiller" || uncertaintyResolutions[1].decision !== "reject") {
  fail("Uncertainty resolution content drifted.");
}
if (isPlanogramUncertaintyReviewComplete(uncertainRegions, { "uncertain-1": { decision: "confirm" } })) {
  fail("Unknown uncertain geometry was accepted without a type.");
}

const fingerprint = "a".repeat(64);
const safeResponse = {
  preview_only: true,
  input_authority: "fingerprint_bound_human_review_unattested",
  store_dna_approval_allowed: false,
  production_release_allowed: false,
  installation_approval_allowed: false,
  result: {
    scan_fingerprint: fingerprint,
    store_dna_authority: false,
    maker_checker_approved: false,
    production_authority: false,
    installation_approval_allowed: false,
    auto_store_dna_promotion_allowed: false,
  },
};
if (!safePlanogramScanAnnotationPreview(safeResponse, fingerprint)) {
  fail("Safe fingerprint-bound annotation preview was rejected.");
}
for (const mutate of [
  (row) => { row.store_dna_approval_allowed = true; },
  (row) => { row.result.store_dna_authority = true; },
  (row) => { row.result.maker_checker_approved = true; },
  (row) => { row.result.production_authority = true; },
  (row) => { row.result.auto_store_dna_promotion_allowed = true; },
  (row) => { row.result.scan_fingerprint = "b".repeat(64); },
]) {
  const forged = structuredClone(safeResponse);
  mutate(forged);
  if (safePlanogramScanAnnotationPreview(forged, fingerprint) !== null) {
    fail("Scan annotation client accepted an authority or fingerprint leak.");
  }
}

const workspace = fs.readFileSync("src/modules/planogram/PlanogramScanAnnotationWorkspace.jsx", "utf8");
for (const needle of [
  "/v1/planogram/store-scan/annotate-preview",
  "expected_scan_fingerprint",
  "safePlanogramScanAnnotationPreview",
  "classified_type",
  "operational_elements",
  "uncertainty_resolutions: uncertaintyResolutions",
  "buildPlanogramUncertaintyResolutions",
  "isPlanogramUncertaintyReviewComplete",
  "<PlanogramScanUncertaintyLayer",
  "<PlanogramScanUncertaintyReview",
  "uncertaintyResolutions={uncertaintyResolutions}",
  "reviewedResult={reviewedResult}",
  "rotatedRectSvgPoints",
  "onKeyDown={handleMapKeyDown}",
  "tabIndex={0}",
  "KEYBOARD_STEP_M = 0.25",
]) {
  if (!workspace.includes(needle)) fail(`Scan annotation workspace contract missing: ${needle}`);
}
for (const forbidden of [
  "/store-dna/bootstrap",
  "/store-dna/approve",
  "store_dna_approved: true",
  "production_authority: true",
]) {
  if (workspace.includes(forbidden)) fail(`Scan annotation workspace leaked authority path: ${forbidden}`);
}
const scanPanel = fs.readFileSync("src/modules/planogram/PlanogramStoreScanPanel.jsx", "utf8");
if (!scanPanel.includes("<PlanogramScanAnnotationWorkspace") || !scanPanel.includes("<PlanogramScanUncertaintyLayer")) {
  fail("Store Scan review does not expose uncertainty visualization and visual annotation.");
}
const fixturePanel = fs.readFileSync("src/modules/planogram/PlanogramFixtureBindingPanel.jsx", "utf8");
for (const needle of [
  "reviewed_recognized_fixtures",
  "uncertainty_resolutions: uncertaintyResolutions || []",
  "uncertaintyResolutions={uncertaintyResolutions}",
]) {
  if (!fixturePanel.includes(needle)) fail(`Fixture binding uncertainty propagation missing: ${needle}`);
}
const optimizerPanel = fs.readFileSync("src/modules/planogram/PlanogramScannedOptimizerPanel.jsx", "utf8");
if (!optimizerPanel.includes("uncertainty_resolutions: uncertaintyResolutions || []")) {
  fail("Scanned optimizer does not preserve fingerprint-bound uncertainty decisions.");
}

console.log("Planogram fingerprint-bound visual Store Scan annotation and uncertainty review: PASS");
