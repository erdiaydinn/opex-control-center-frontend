import fs from "node:fs";
import process from "node:process";

import { buildPlanogramUnifiedTwinScene } from "../src/modules/planogram/planogramUnifiedTwinScene.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const scan = fs.readFileSync("src/modules/planogram/PlanogramStoreScanPanel.jsx", "utf8");
const twin = fs.readFileSync("src/modules/planogram/PlanogramScannedDigitalTwin.jsx", "utf8");
const fixture = fs.readFileSync("src/modules/planogram/planogramFixtureBindings.js", "utf8");
const backend = fs.readFileSync("services/core-api/app/modules/planogram/store_scan.py", "utf8");
const layout = fs.readFileSync("services/core-api/app/modules/planogram/store_scan_fixture_layout.py", "utf8");

for (const [text, needle, message] of [
  [backend, 'PRODUCT_BEARING_EQUIPMENT_TYPES = {"fixture", "chiller", "freezer"}', "Cold equipment is not product-bearing scan evidence"],
  [backend, '"hinted_storage_type": _equipment_storage_hint(element_type)', "Cold scan storage hint is missing"],
  [backend, 'recognized_temperature_fixture_count', "Cold fixture evidence count is missing"],
  [layout, 'scan_fixture_storage_hint_mismatch', "Server does not fail closed on cold storage hint mismatch"],
  [layout, 'scan_hinted_storage_type', "Physical layout does not preserve scan storage evidence"],
  [fixture, 'catalog.storage_type === storageHint', "Catalog suggestions do not respect scan storage hints"],
  [fixture, 'fixture.storage_type !== storageHint', "Client binding does not fail closed on cold storage mismatch"],
  [scan, 'architectureIds.has(String(fixture.element_id || ""))', "2D Store Scan may double-render cold equipment"],
  [twin, '<PlanogramTwinSceneRenderer', "Reviewed scan no longer uses the governed shared twin renderer"],
]) {
  if (!text.includes(needle)) fail(message);
}

const unified = buildPlanogramUnifiedTwinScene({
  reviewedArchitecture: {
    schema_version: 2,
    source_ref: "scan://cold-chain/review-1",
    floor_width_m: 10,
    floor_depth_m: 8,
    elements: [
      {
        element_id: "COLD-1",
        element_type: "chiller",
        center_x_m: 2,
        center_y_m: 2,
        width_m: 1.2,
        depth_m: 0.7,
        rotation_deg: 0,
      },
      {
        element_id: "WALL-1",
        element_type: "wall",
        center_x_m: 5,
        center_y_m: 1,
        width_m: 4,
        depth_m: 0.1,
        rotation_deg: 0,
      },
    ],
  },
  recognizedFixtures: [
    {
      element_id: "COLD-1",
      fixture_type: "CHILLED",
      hinted_storage_type: "CHILLED",
      center_x_m: 2,
      center_y_m: 2,
      width_m: 1.2,
      depth_m: 0.7,
      height_m: 1.9,
      rotation_deg: 0,
    },
    {
      element_id: "REG-1",
      fixture_type: "REGULAR_SHELF",
      hinted_storage_type: "AMBIENT",
      center_x_m: 5,
      center_y_m: 4,
      width_m: 1,
      depth_m: 0.5,
      height_m: 2,
      rotation_deg: 0,
    },
  ],
});

if (!unified) fail("Reviewed cold-chain scan did not build a unified twin scene.");
if (!unified.architecture.some((row) => row.id === "COLD-1" && row.type === "chiller")) {
  fail("Cold equipment architecture evidence was lost from the unified twin.");
}
if (unified.fixtures.some((row) => row.id === "COLD-1")) {
  fail("Cold equipment present in architecture and recognized fixtures was double-rendered.");
}
if (!unified.fixtures.some((row) => row.id === "REG-1")) {
  fail("Non-duplicate recognized fixture was incorrectly removed.");
}
if (unified.provenance?.deduplicatedColdEquipmentCount !== 1) {
  fail("Cold-equipment deduplication must remain observable in unified-scene provenance.");
}
if (unified.geometryAuthority !== "reviewed_scan_preview_not_store_dna_authority" || unified.productionReleaseAllowed !== false) {
  fail("Cold-chain scan preview must not self-promote to Store DNA or production authority.");
}

console.log("PLANOGRAM_SCANNED_COLD_CHAIN_DUAL_ROLE=PASS");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_STORAGE_HINT=PASS");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_WRONG_STORAGE_BIND=BLOCKED");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_DUPLICATE_RENDER=FALSE");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_PRODUCTION_AUTHORITY=FALSE");
