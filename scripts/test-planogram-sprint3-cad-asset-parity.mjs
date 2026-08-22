import process from "node:process";

import { PLANOGRAM_CAD_OVERLAY_CONTRACT } from "../src/modules/planogram/planogramCadAdvanced.js";
import { buildPlanogramDigitalTwinModel } from "../src/modules/planogram/planogramDigitalTwinModel.js";
import { buildPlanogramVisualDeliveryPlan } from "../src/modules/planogram/planogramVisualDeliveryModel.js";
import { buildPlanogramVisualQualityPlan } from "../src/modules/planogram/planogramVisualQualityModel.js";

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
          products: [{ sku: "ENGINE-SKU", facing_count: 2, width_cm: 8, height_cm: 18, depth_cm: 7 }],
        }],
      }],
    }],
  },
};

const candidate = {
  layout: {
    aisles: [{ aisle_id: "A", modules: [{ module_id: 1, center_x_m: 2, center_y_m: 2, width_m: 1, depth_m: 0.5 }] }],
  },
  store_dna: {
    architecture: {
      schema_version: 2,
      coordinate_system: "cartesian_m_centered_rect",
      source: "human_reviewed_store_scan",
      source_ref: "scan://SPRINT3/cad-assets",
      floor_width_m: 40,
      floor_depth_m: 20,
      elements: [{ element_id: "ENTRY", element_type: "picker_entry", center_x_m: 1, center_y_m: 1, width_m: 0.4, depth_m: 0.4 }],
    },
    cad_overlay: {
      contract: PLANOGRAM_CAD_OVERLAY_CONTRACT,
      preview_only: true,
      production_release_allowed: false,
      physical_truth_attested: false,
      authority: "human_cad_preview_not_store_dna_authority",
      nodes: [{
        nodeId: "CAD-ENDCAP-1",
        nodeType: "fixture",
        geometry: { centerXM: 30, centerYM: 10, widthM: 0.9, depthM: 0.6, heightM: 1.8, rotationDeg: 31 },
        provenance: { source: "human", sourceRef: "cad-session-ui" },
        metadata: {
          fixtureType: "ENDCAP",
          fixtureCode: "ENDCAP-0900",
          shelfCount: 4,
          dimensionAuthority: "human_cad_preview",
          cadOverlay: true,
          productionReleaseAllowed: false,
        },
      }],
    },
  },
};

const manifest = {
  product_assets: [{
    sku: "ENGINE-SKU",
    front_image_path: "/planogram-assets/products/engine-sku.webp",
    source_ref: "pim://engine-sku/front-v1",
    attested: true,
  }],
  fixture_assets: [{
    fixture_type: "ENDCAP",
    model_path: "/planogram-assets/fixtures/endcap-near.glb",
    lod_model_paths: {
      medium: "/planogram-assets/fixtures/endcap-medium.glb",
      far: "/planogram-assets/fixtures/endcap-far.glb",
    },
    source_ref: "vendor://fixture/endcap/v3",
    attested: true,
  }],
};

const model = buildPlanogramDigitalTwinModel(engineResult, candidate);
if (!model || model.cadFixtures.length !== 1) fail("CAD fixture did not reach the Digital Twin model.");
const visual = buildPlanogramVisualQualityPlan(model, manifest);
const delivery = buildPlanogramVisualDeliveryPlan(model, manifest, { ktx2: true, textureAtlas: true });
if (!visual || !delivery) fail("CAD visual planning did not produce both quality and delivery plans.");
if (visual.productionReleaseAllowed !== false || delivery.productionReleaseAllowed !== false) fail("CAD visual asset planning self-promoted production authority.");
if (visual.geometryAuthority !== "canonical_store_scene" || delivery.geometryAuthority !== "canonical_store_scene") fail("GLB delivery replaced canonical StoreScene geometry authority.");
if (visual.fixtureInstances.length !== 1) fail(`CAD-only fixture GLB was not selected exactly once: ${visual.fixtureInstances.length}`);
const fixture = visual.fixtureInstances[0];
if (fixture.moduleKey !== "CAD-ENDCAP-1" || fixture.fixtureType !== "ENDCAP") fail("CAD fixture visual identity drifted.");
if (fixture.sourceKind !== "cad_overlay_preview" || fixture.coordinateAuthority !== "human_cad_preview" || fixture.previewOnly !== true) fail("CAD fixture preview authority was lost in visual planning.");
if (fixture.visualAssetAuthority !== "attested_same_origin_glb" || fixture.geometryAuthority !== "canonical_store_scene") fail("CAD fixture GLB gained geometry authority.");
if (fixture.targetEnvelopeM.widthM !== 0.9 || fixture.targetEnvelopeM.depthM !== 0.6 || fixture.targetEnvelopeM.heightM !== 1.8) fail("CAD fixture GLB target envelope drifted from authored metric geometry.");
if (fixture.modelPath !== "/planogram-assets/fixtures/endcap-medium.glb" || fixture.lodQuality !== "medium") fail(`CAD fixture deterministic LOD selection drifted: ${fixture.modelPath} / ${fixture.lodQuality}`);
if (visual.productTextures.length !== 1 || visual.productTextures[0].sku !== "ENGINE-SKU") fail("Engine product texture plan regressed while adding CAD fixture assets.");
if (visual.productTextures.some((row) => row.moduleKey === "CAD-ENDCAP-1")) fail("CAD fixture invented product texture evidence.");
const endcapDelivery = delivery.fixtures.find((row) => row.fixtureType === "ENDCAP");
if (!endcapDelivery || endcapDelivery.mode !== "lod" || endcapDelivery.levels.length !== 3) fail("CAD-only fixture type did not reach governed GLB/LOD delivery.");
if (delivery.products.length !== 1 || delivery.products[0].sku !== "ENGINE-SKU") fail("Product delivery scope drifted from engine SKU authority.");

const hostileModel = structuredClone(model);
hostileModel.cadFixtures[0].productionReleaseAllowed = true;
const hostileVisual = buildPlanogramVisualQualityPlan(hostileModel, manifest);
const hostileDelivery = buildPlanogramVisualDeliveryPlan(hostileModel, manifest, {});
if (hostileVisual.fixtureInstances.length !== 0 || hostileDelivery.fixtures.some((row) => row.fixtureType === "ENDCAP")) fail("Invalid CAD fixture authority was allowed to consume governed GLB assets.");
if (hostileVisual.diagnostics.rejectedCadFixtureAuthority !== 1 || hostileDelivery.diagnostics.rejectedCadFixtureAuthority !== 1) fail("Rejected CAD visual authority is not observable.");

const unattestedManifest = structuredClone(manifest);
unattestedManifest.fixture_assets[0].attested = false;
const unattestedVisual = buildPlanogramVisualQualityPlan(model, unattestedManifest);
const unattestedDelivery = buildPlanogramVisualDeliveryPlan(model, unattestedManifest, {});
if (unattestedVisual.fixtureInstances.length !== 0 || unattestedDelivery.fixtures.some((row) => row.fixtureType === "ENDCAP")) fail("Unattested CAD fixture GLB entered the renderer plan.");

console.log("SPRINT3_CAD_GOVERNED_GLTF_VISUAL_PARITY=PASS");
console.log("SPRINT3_CAD_GOVERNED_LOD_DELIVERY=PASS");
console.log("SPRINT3_CAD_GLTF_METRIC_ENVELOPE_AUTHORITY=PASS");
console.log("SPRINT3_CAD_PRODUCT_EVIDENCE_ISOLATED=PASS");
console.log("SPRINT3_CAD_VISUAL_AUTHORITY_FAIL_CLOSED=PASS");
console.log("SPRINT3_CAD_VISUAL_PRODUCTION_AUTHORITY=FALSE");
