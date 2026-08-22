import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_STORE_SCAN_MESSAGES } from "../src/platform/i18n/planogramStoreScanMessages.js";
import {
  normalizePlanogramStoreScanBundle,
  safePlanogramStoreScanPreview,
} from "../src/modules/planogram/planogramStoreScanBundle.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const englishKeys = Object.keys(PLANOGRAM_STORE_SCAN_MESSAGES.en).sort();
for (const { code } of SUPPORTED_LOCALES) {
  const table = PLANOGRAM_STORE_SCAN_MESSAGES[code];
  if (!table) fail(`Missing Store Scan locale: ${code}`);
  if (JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(englishKeys)) {
    fail(`Store Scan locale coverage drifted: ${code}`);
  }
}

const valid = {
  store_code: "TEST-STORE",
  provider: "apple_roomplan",
  source_ref: "scan-session:test-001",
  floor_width_m: 12,
  floor_depth_m: 8,
  elements: [
    {
      element_id: "wall-1",
      element_type: "wall",
      x_m: 0,
      y_m: 0,
      width_m: 12,
      depth_m: 0.1,
      rotation_deg: 17,
      confidence: 0.99,
    },
  ],
};
const normalized = normalizePlanogramStoreScanBundle(valid);
if (!normalized || normalized.elements[0].rotation_deg !== 17) {
  fail("Valid arbitrary-angle Store Scan bundle was rejected.");
}
for (const forged of [
  { ...valid, raw_media: "base64..." },
  { ...valid, video_bytes: [1, 2, 3] },
  { ...valid, provider: "browser_camera_guess" },
  { ...valid, elements: [{ ...valid.elements[0], image_url: "https://example.invalid/raw.jpg" }] },
]) {
  if (normalizePlanogramStoreScanBundle(forged) !== null) {
    fail("Store Scan bundle boundary accepted raw media or an unsupported field/provider.");
  }
}

const safeResponse = {
  preview_only: true,
  input_authority: "request_supplied_measured_scan_unattested",
  production_release_allowed: false,
  store_scan: {
    scan_fingerprint: "a".repeat(64),
    raw_media_persisted: false,
    production_evidence: false,
    promotable_to_store_dna: false,
  },
};
if (!safePlanogramStoreScanPreview(safeResponse)) fail("Safe Store Scan preview was rejected.");
for (const mutate of [
  (row) => { row.production_release_allowed = true; },
  (row) => { row.store_scan.production_evidence = true; },
  (row) => { row.store_scan.promotable_to_store_dna = true; },
  (row) => { row.store_scan.raw_media_persisted = true; },
]) {
  const forged = structuredClone(safeResponse);
  mutate(forged);
  if (safePlanogramStoreScanPreview(forged) !== null) {
    fail("Store Scan UI accepted a truth/authority leak.");
  }
}

const component = fs.readFileSync("src/modules/planogram/PlanogramStoreScanPanel.jsx", "utf8");
for (const needle of [
  "/v1/planogram/store-scan/normalize-preview",
  "safePlanogramStoreScanPreview",
  "normalizePlanogramStoreScanBundle",
  "rotatedRectSvgPoints",
  "scan_fingerprint",
  "rawMedia",
]) {
  if (!component.includes(needle)) fail(`Store Scan review contract missing: ${needle}`);
}
const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
if (!studio.includes("<PlanogramStoreScanPanel")) {
  fail("Planogram Studio does not expose Store Scan review.");
}

console.log("Planogram Store Scan review and raw-media truth boundary: PASS");
