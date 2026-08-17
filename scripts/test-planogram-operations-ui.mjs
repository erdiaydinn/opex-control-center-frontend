import fs from "node:fs";
import assert from "node:assert/strict";

import { planogramOperationsMessageCoverage } from "../src/platform/i18n/planogramOperationsMessages.js";

const LOCALES = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const coverage = planogramOperationsMessageCoverage(LOCALES);
for (const locale of LOCALES) {
  assert.deepEqual(coverage.missing[locale], [], `Missing Planogram operations messages for ${locale}`);
  assert.deepEqual(coverage.extra[locale], [], `Unexpected Planogram operations messages for ${locale}`);
}

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
const operations = fs.readFileSync("src/modules/planogram/PlanogramOperationsPanel.jsx", "utf8");

assert.match(studio, /PlanogramOperationsPanel/);
assert.match(studio, /\/v1\/planogram\/optimize-preview/);
assert.doesNotMatch(studio, /<iframe|postMessage\(|access_token|VITE_PLANAI_LEGACY_URL/);

for (const path of [
  "/v1/planogram/store-dna/workspace",
  "/v1/planogram/store-dna/bootstrap",
  "/v1/planogram/execution/plans",
  "/v1/planogram/execution/assignments",
]) {
  assert.ok(operations.includes(path), `Missing Planogram operations API contract: ${path}`);
}

assert.match(operations, /geometry_attested/);
assert.match(operations, /physical_truth_attested/);
assert.match(operations, /observation_count/);
assert.match(operations, /deviation_count/);
assert.match(operations, /canAction\("planogram", "approve"\)/);
assert.match(operations, /canAction\("planogram", "edit"\)/);

console.log("PLANOGRAM_OPERATIONS_LOCALES=PASS");
console.log("PLANOGRAM_STORE_DNA_UI=PASS");
console.log("PLANOGRAM_OPTIMIZER_PREVIEW_UI=PASS");
console.log("PLANOGRAM_EXECUTION_COMPLIANCE_UI=PASS");
