import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_FIXTURE_BINDING_MESSAGES } from "../src/platform/i18n/planogramFixtureBindingMessages.js";
import { PLANOGRAM_FIXTURE_CATALOG_MESSAGES } from "../src/platform/i18n/planogramFixtureCatalogMessages.js";
import {
  buildPlanogramFixtureBindingsFromSelections,
  normalizePlanogramFixtureBindings,
  normalizePlanogramFixtureCatalog,
  safePlanogramFixtureLayoutPreview,
  suggestPlanogramFixtureCatalogMatches,
} from "../src/modules/planogram/planogramFixtureBindings.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

for (const dictionary of [
  ["binding", PLANOGRAM_FIXTURE_BINDING_MESSAGES],
  ["catalog", PLANOGRAM_FIXTURE_CATALOG_MESSAGES],
]) {
  const [name, messages] = dictionary;
  const englishKeys = Object.keys(messages.en).sort();
  for (const { code } of SUPPORTED_LOCALES) {
    const table = messages[code];
    if (!table) fail(`Missing fixture ${name} locale: ${code}`);
    if (JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(englishKeys)) {
      fail(`Fixture ${name} locale coverage drifted: ${code}`);
    }
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

const catalogPayload = {
  fixtures: [
    Object.fromEntries(Object.entries(valid.bindings[0]).filter(([key]) => ![
      "scan_fixture_element_id",
      "aisle_id",
      "side",
      "position",
    ].includes(key))),
    {
      ...Object.fromEntries(Object.entries(valid.bindings[0]).filter(([key]) => ![
        "scan_fixture_element_id",
        "aisle_id",
        "side",
        "position",
      ].includes(key))),
      fixture_id: "GONDOLA-002",
      fixture_width_cm: 180,
      source_ref: "fixture-master://GONDOLA-002/v1",
    },
  ],
};
const catalog = normalizePlanogramFixtureCatalog(catalogPayload);
if (!catalog || catalog.length !== 2) fail("Valid attested fixture catalog was rejected.");
if (normalizePlanogramFixtureCatalog({ fixtures: [{ ...catalogPayload.fixtures[0], attested: false }] }) !== null) {
  fail("Unattested fixture catalog entry was accepted.");
}
const recognized = [{
  element_id: "fixture-1",
  width_m: 1.19,
  depth_m: 0.61,
  label: "steel rack",
  confidence: 0.95,
}];
const suggestions = suggestPlanogramFixtureCatalogMatches(recognized, catalog);
if (
  suggestions.length !== 1 ||
  suggestions[0].recommended_fixture_id !== "GONDOLA-001" ||
  suggestions[0].recommendation_safe !== true
) {
  fail("Unique dimension-consistent fixture suggestion was not produced deterministically.");
}
const assisted = buildPlanogramFixtureBindingsFromSelections(recognized, catalog, {
  "fixture-1": { fixture_id: "GONDOLA-001", aisle_id: "A01", side: "L", position: 1 },
});
if (!assisted || assisted[0].fixture_id !== "GONDOLA-001") {
  fail("Catalog-assisted human topology selection did not produce a valid binding.");
}
if (buildPlanogramFixtureBindingsFromSelections(recognized, catalog, {
  "fixture-1": { fixture_id: "GONDOLA-001", aisle_id: "", side: "", position: "" },
}) !== null) {
  fail("Catalog assistance fabricated aisle/side/position truth.");
}

const coldCatalog = normalizePlanogramFixtureCatalog({
  fixtures: [
    {
      ...catalogPayload.fixtures[0],
      fixture_id: "AMBIENT-SAME-SIZE",
      fixture_type: "steel_rack",
      storage_type: "AMBIENT",
      source_ref: "fixture-master://AMBIENT-SAME-SIZE/v1",
    },
    {
      ...catalogPayload.fixtures[0],
      fixture_id: "CHILLER-SAME-SIZE",
      fixture_type: "chilled_cabinet",
      storage_type: "CHILLED",
      source_ref: "fixture-master://CHILLER-SAME-SIZE/v1",
    },
  ],
});
const coldRecognized = [{
  element_id: "chiller-scan-1",
  width_m: 1.2,
  depth_m: 0.6,
  label: "+4 chilled cabinet",
  confidence: 0.98,
  source_element_type: "chiller",
  hinted_storage_type: "CHILLED",
}];
const coldSuggestions = suggestPlanogramFixtureCatalogMatches(coldRecognized, coldCatalog);
if (
  coldSuggestions[0]?.recommended_fixture_id !== "CHILLER-SAME-SIZE" ||
  coldSuggestions[0]?.candidates?.some((row) => row.fixture.storage_type !== "CHILLED")
) {
  fail("Cold-chain scan hint did not eliminate incompatible ambient fixture candidates.");
}
if (buildPlanogramFixtureBindingsFromSelections(coldRecognized, coldCatalog, {
  "chiller-scan-1": {
    fixture_id: "AMBIENT-SAME-SIZE",
    aisle_id: "COLD",
    side: "L",
    position: 1,
  },
}) !== null) {
  fail("Client binding accepted an ambient catalog fixture for a CHILLED scan cue.");
}
const chilledBinding = buildPlanogramFixtureBindingsFromSelections(coldRecognized, coldCatalog, {
  "chiller-scan-1": {
    fixture_id: "CHILLER-SAME-SIZE",
    aisle_id: "COLD",
    side: "L",
    position: 1,
  },
});
if (!chilledBinding || chilledBinding[0].storage_type !== "CHILLED") {
  fail("Valid CHILLED catalog fixture could not bind to a CHILLED scan cue.");
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
  "normalizePlanogramFixtureCatalog",
  "suggestPlanogramFixtureCatalogMatches",
  "buildPlanogramFixtureBindingsFromSelections",
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

console.log("PLANOGRAM_SCANNED_FIXTURE_CATALOG_ASSIST=PASS");
console.log("PLANOGRAM_SCANNED_FIXTURE_AMBIGUOUS_AUTO_BIND=FALSE");
console.log("PLANOGRAM_SCANNED_FIXTURE_TOPOLOGY_FABRICATION=FALSE");
console.log("PLANOGRAM_SCANNED_FIXTURE_TOPOLOGY_HUMAN_REVIEW=REQUIRED");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_STORAGE_HINT=PASS");
console.log("PLANOGRAM_SCANNED_COLD_CHAIN_WRONG_STORAGE_BIND=BLOCKED");
console.log("Planogram scanned fixture catalog binding boundary: PASS");