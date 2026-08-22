import process from "node:process";

import { PLANOGRAM_CAD_OVERLAY_CONTRACT } from "../src/modules/planogram/planogramCadAdvanced.js";
import { buildPlanogramDigitalTwinModel } from "../src/modules/planogram/planogramDigitalTwinModel.js";
import { buildPlanogramUnifiedTwinScene } from "../src/modules/planogram/planogramUnifiedTwinScene.js";
import {
  buildPlanogramWalkthroughNavigation,
  resolvePlanogramWalkthroughStep,
} from "../src/modules/planogram/planogramWalkthroughNavigation.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const engineResult = {
  planogram: {
    aisles: [{
      aisle_id: "A",
      modules: [{
        module_id: 1,
        fixture_type: "REGULAR_SHELF",
        shelves: [{
          shelf_no: 1,
          shelf_width_cm: 100,
          shelf_depth_cm: 50,
          products: [{ sku: "ENGINE-SKU", facing_count: 2, sales_qty_7d: 12, width_cm: 8, height_cm: 18, depth_cm: 7 }],
        }],
      }],
    }],
  },
};

const candidate = {
  layout: {
    aisles: [{
      aisle_id: "A",
      modules: [{ module_id: 1, center_x_m: 2, center_y_m: 2, width_m: 1, depth_m: 0.5, rotation_deg: 0 }],
    }],
  },
  store_dna: {
    architecture: {
      schema_version: 2,
      coordinate_system: "cartesian_m_centered_rect",
      source: "human_reviewed_store_scan",
      source_ref: "scan://SPRINT3/cad-twin",
      floor_width_m: 10,
      floor_depth_m: 8,
      elements: [
        { element_id: "ENTRY", element_type: "picker_entry", center_x_m: 1, center_y_m: 1, width_m: 0.4, depth_m: 0.4, rotation_deg: 0 },
        { element_id: "WALL", element_type: "wall", center_x_m: 7, center_y_m: 3, width_m: 2, depth_m: 0.12, rotation_deg: 17 },
      ],
    },
    cad_overlay: {
      contract: PLANOGRAM_CAD_OVERLAY_CONTRACT,
      preview_only: true,
      production_release_allowed: false,
      physical_truth_attested: false,
      authority: "human_cad_preview_not_store_dna_authority",
      nodes: [{
        nodeId: "CAD-FIXTURE-1",
        nodeType: "fixture",
        parentId: null,
        geometry: { centerXM: 5, centerYM: 4, widthM: 1, depthM: 0.5, heightM: 2, rotationDeg: 23 },
        locked: false,
        provenance: { source: "human", sourceRef: "cad-session-ui" },
        metadata: {
          fixtureType: "REGULAR_SHELF",
          fixtureCode: "GONDOLA-1000",
          shelfCount: 5,
          dimensionAuthority: "human_cad_preview",
          cadOverlay: true,
          productionReleaseAllowed: false,
        },
      }],
    },
  },
};

const model = buildPlanogramDigitalTwinModel(engineResult, candidate);
if (!model) fail("CAD overlay candidate did not build a Digital Twin model.");
if (model.stats.moduleCount !== 1 || model.stats.placedProductCount !== 1 || model.stats.facingCount !== 2) {
  fail(`CAD overlay polluted engine KPI authority: ${JSON.stringify(model.stats)}`);
}
if (model.stats.cadFixtureCount !== 1 || model.cadFixtures.length !== 1) fail("CAD fixture projection count drifted.");
if (model.geometryAuthority !== "mixed-engine-and-human-cad-preview") fail(`Mixed CAD preview authority missing: ${model.geometryAuthority}`);
if (model.engineGeometryAuthority !== "measured-preview-v2") fail(`Engine geometry authority was overwritten: ${model.engineGeometryAuthority}`);
if (model.productionReleaseAllowed !== false || model.cadOverlay.productionReleaseAllowed !== false || model.cadOverlay.physicalTruthAttested !== false) fail("CAD Twin preview self-promoted production authority.");
if (model.cadOverlay.rejected || !model.cadOverlay.contractValid || model.cadOverlay.fixtureCount !== 1) fail("Valid CAD overlay was rejected or de-authorized.");

const cadFixture = model.cadFixtures[0];
if (cadFixture.key !== "CAD-FIXTURE-1" || cadFixture.fixtureCode !== "GONDOLA-1000" || cadFixture.fixtureType !== "REGULAR_SHELF") fail("CAD fixture identity drifted in Digital Twin projection.");
if (cadFixture.centerXM !== 5 || cadFixture.centerYM !== 4 || cadFixture.rotationDeg !== 23) fail("CAD fixture metric transform drifted in Digital Twin projection.");
if (cadFixture.coordinateAuthority !== "human_cad_preview" || cadFixture.sourceKind !== "cad_overlay_preview") fail("CAD fixture preview authority drifted.");
if (cadFixture.productCount !== 0 || cadFixture.facingCount !== 0 || cadFixture.sales7d !== 0) fail("CAD fixture invented commercial/product evidence.");

const scene = buildPlanogramUnifiedTwinScene({ authoredModel: model });
if (!scene || scene.productionReleaseAllowed !== false) fail("Unified Twin CAD projection authority drifted.");
if (scene.fixtures.length !== 2) fail(`Unified Twin did not combine engine and CAD fixtures: ${scene.fixtures.length}`);
const sceneCadFixture = scene.fixtures.find((row) => row.id === "CAD-FIXTURE-1");
if (!sceneCadFixture || sceneCadFixture.sourceKind !== "cad_overlay_preview" || sceneCadFixture.previewOnly !== true) fail("CAD fixture did not enter the Unified Twin as preview-only geometry.");
if (sceneCadFixture.coordinateAuthority !== "human_cad_preview" || sceneCadFixture.productionReleaseAllowed !== false || sceneCadFixture.physicalTruthAttested !== false) fail("CAD fixture authority drifted in Unified Twin.");
if (sceneCadFixture.products.length !== 0) fail("CAD fixture fabricated product facings in Unified Twin.");
if (scene.provenance.cadOverlayFixtureCount !== 1 || scene.provenance.cadOverlayRejected !== false) fail("Unified Twin CAD overlay provenance drifted.");

const navigation = buildPlanogramWalkthroughNavigation(scene);
const collisionStep = resolvePlanogramWalkthroughStep(navigation, { x: 4, y: 4 }, { x: 1.2, y: 0 });
if (!collisionStep.blocked) fail("Walk-through did not collide with the authored CAD fixture.");

const malicious = structuredClone(candidate);
malicious.store_dna.cad_overlay.nodes[0].provenance.sourceRef = "https://evil.example/fixture.glb";
const rejected = buildPlanogramDigitalTwinModel(engineResult, malicious);
if (!rejected || rejected.cadOverlay.rejected !== true || rejected.cadFixtures.length !== 0) fail("Malicious CAD overlay did not fail closed in Digital Twin projection.");
if (rejected.stats.moduleCount !== 1 || rejected.stats.facingCount !== 2) fail("Rejected CAD overlay corrupted engine KPI truth.");
if (rejected.geometryAuthority !== rejected.engineGeometryAuthority) fail("Rejected CAD overlay still contaminated geometry authority.");

console.log("SPRINT3_CAD_TWIN_KPI_AUTHORITY_ISOLATED=PASS");
console.log("SPRINT3_CAD_TWIN_METRIC_PROJECTION=PASS");
console.log("SPRINT3_CAD_TWIN_UNIFIED_SCENE=PASS");
console.log("SPRINT3_CAD_TWIN_WALKTHROUGH_COLLISION=PASS");
console.log("SPRINT3_CAD_TWIN_MALICIOUS_OVERLAY_FAIL_CLOSED=PASS");
console.log("SPRINT3_CAD_TWIN_PRODUCTION_AUTHORITY=FALSE");
