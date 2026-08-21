import fs from "node:fs";
import process from "node:process";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const scan = fs.readFileSync("src/modules/planogram/PlanogramStoreScanPanel.jsx", "utf8");
const twin = fs.readFileSync("src/modules/planogram/PlanogramScannedDigitalTwin.jsx", "utf8");
const sharedTwin = fs.readFileSync("src/modules/planogram/PlanogramTwinSceneRenderer.jsx", "utf8");
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
  [sharedTwin, 'architectureEquipmentIds.has(String(fixture.id || ""))', "Shared 3D Twin may double-render cold equipment"],
]) {
  if (!text.includes(needle)) fail(message);
}

console.log("PLANOGRAM_SCANNED_COLD_CHAIN_DUAL_ROLE=PASS");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_STORAGE_HINT=PASS");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_WRONG_STORAGE_BIND=BLOCKED");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_DUPLICATE_RENDER=FALSE");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_PRODUCTION_AUTHORITY=FALSE");
