import fs from "node:fs";

const read = (path) => fs.readFileSync(path, "utf8");
const need = (text, token, message) => {
  if (!text.includes(token)) throw new Error(message);
};

const studio = read("src/modules/planogram/PlanogramStudio.jsx");
const storeScan = read("src/modules/planogram/PlanogramStoreScanPanel.jsx");
const annotation = read("src/modules/planogram/PlanogramScanAnnotationWorkspace.jsx");
const binding = read("src/modules/planogram/PlanogramFixtureBindingPanel.jsx");
const panel = read("src/modules/planogram/PlanogramScannedOptimizerPanel.jsx");
const sanitizer = read("src/modules/planogram/planogramScannedOptimizer.js");
const messages = read("src/platform/i18n/planogramScannedOptimizerMessages.js");
const adapter = read("services/core-api/app/modules/planogram/scanned_optimizer_adapter.py");
const schemas = read("services/core-api/app/modules/planogram/store_scan_binding_schemas.py");

need(studio, "optimizationCandidate={candidate}", "Studio does not pass the candidate bundle into Store Scan");
need(storeScan, "optimizationCandidate={optimizationCandidate}", "Store Scan does not forward candidate evidence");
need(annotation, "PlanogramFixtureBindingPanel", "Annotation workspace no longer mounts fixture binding");
need(annotation, "optimizationCandidate={optimizationCandidate}", "Annotation workspace drops candidate evidence");
need(binding, "PlanogramScannedOptimizerPanel", "Fixture binding does not mount scanned optimizer");
need(binding, "result.layout_draft_ready", "Scanned optimizer is not gated by completed fixture layout review");
need(binding, "fixtureBindings={effectiveBindings}", "Reviewed/imported fixture binding evidence is not forwarded to V6");
need(panel, "/v1/planogram/store-scan/optimize-preview", "V6 API route is not called by the product surface");
need(panel, "fixture_bindings: fixtureBindings", "V6 request does not carry reviewed fixture binding evidence");
need(panel, "PlanogramDigitalTwin", "V6 result does not render Digital Twin output");
need(panel, "PlanogramPickerEyePreview", "V6 result does not render Picker Eye output");
need(panel, "expected_scan_fingerprint", "V6 request is not fingerprint-bound");
need(panel, "order_baskets: baskets", "V6 request does not carry anonymized baskets");
need(panel, "representativeRouteOverlay", "V6 selected basket route is not projected into the Digital Twin");
need(panel, "rankedCandidates", "V6 alternatives are not ranked on the product surface");
need(panel, "architecture_route_objective_v2", "V6 route overlay is not wired to the arbitrary-angle Twin contract");
need(adapter, "picker_tour_evidence_v2", "Server does not expose bounded selected-tour evidence");
need(adapter, "basket_ref", "Server route evidence is not anonymized to basket references");
need(adapter, "index >= 3", "Server route evidence is not bounded to three representative baskets");
need(schemas, "PlanogramOrderBasket", "V6 API no longer reuses the SKU-only anonymized basket contract");
need(sanitizer, "fingerprint_bound_scanned_v2_optimizer_unattested", "V6 sanitizer authority contract drifted");
need(sanitizer, "response.production_release_allowed", "V6 sanitizer does not fail closed on production release");
need(sanitizer, "result.global_optimum_claim", "V6 sanitizer does not reject global-optimum authority leaks");

if (/['\"]order_id['\"]\s*:/.test(adapter) || /\border_id\s*:/.test(schemas)) {
  throw new Error("Raw order identity leaked into the V6 public evidence contract");
}

const requestStart = panel.indexOf('apiPost("/v1/planogram/store-scan/optimize-preview"');
const requestEnd = panel.indexOf("});", requestStart);
if (requestStart < 0 || requestEnd < 0) throw new Error("Unable to isolate V6 request payload");
const requestBlock = panel.slice(requestStart, requestEnd);
if (/\blayout\s*:/.test(requestBlock) || /\bstore_dna\s*:/.test(requestBlock)) {
  throw new Error("Client attempted to provide layout or Store DNA authority to V6");
}

for (const locale of ["en", "tr", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"]) {
  const marker = locale === "pt-BR" ? '"pt-BR":' : `${locale}:{`;
  need(messages, marker, `V6 locale missing: ${locale}`);
}

console.log("PLANOGRAM_SCANNED_V6_STUDIO_CHAIN=PASS");
console.log("PLANOGRAM_SCANNED_V6_RANKED_ALTERNATIVES=PASS");
console.log("PLANOGRAM_SCANNED_V6_SELECTED_ROUTE_OVERLAY=PASS");
console.log("PLANOGRAM_SCANNED_V6_ROUTE_EVIDENCE_ANONYMIZED=PASS");
console.log("PLANOGRAM_SCANNED_V6_RAW_ORDER_IDENTITY=ABSENT");
console.log("PLANOGRAM_SCANNED_V6_ROUTE_EVIDENCE_LIMIT=3");
console.log("PLANOGRAM_SCANNED_V6_CLIENT_LAYOUT_AUTHORITY=FALSE");
console.log("PLANOGRAM_SCANNED_V6_STORE_DNA_AUTHORITY=FALSE");
console.log("PLANOGRAM_SCANNED_V6_DIGITAL_TWIN=PASS");
console.log("PLANOGRAM_SCANNED_V6_PICKER_EYE=PASS");
console.log("PLANOGRAM_SCANNED_V6_GLOBAL_OPTIMUM_CLAIM=FALSE");
