import fs from "node:fs";
import process from "node:process";

import {
  buildPlanogramVisualQualityPlan,
  PLANOGRAM_VISUAL_QUALITY_LIMITS,
} from "../src/modules/planogram/planogramVisualQualityModel.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const renderer = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
const qualityConfig = JSON.parse(fs.readFileSync("config/eay_planogram_visual_quality_v1.json", "utf8"));

for (const [needle, label] of [
  ["buildPlanogramVisualQualityPlan", "governed visual plan binding"],
  ['await import("three/examples/jsm/loaders/GLTFLoader.js")', "dynamic governed GLB loading"],
  ['await import("three/examples/jsm/environments/RoomEnvironment.js")', "PBR reflection environment"],
  ["new THREE.PMREMGenerator(renderer)", "PMREM environment projection"],
  ["new THREE.TextureLoader()", "packshot texture runtime"],
  ["candidate?.asset_manifest", "candidate asset manifest binding"],
  ["assetPlan.targetEnvelopeM", "canonical metric fixture envelope"],
  ["fallback.visible = false", "fallback hidden only after GLB success"],
  ["attested_same_origin_packshot", "attested packshot visual authority"],
  ["attested_same_origin_glb", "attested GLB visual authority"],
  ["buildFacingInstances(THREE, model, visualPlan)", "real facing transform reuse"],
  ["addTexturedFacingOverlays", "textured facing overlay runtime"],
  ["addGovernedFixtureAssets", "governed fixture replacement runtime"],
  ["MeshPhysicalMaterial", "PBR material baseline"],
  ["ACESFilmicToneMapping", "filmic tone mapping"],
  ["maxProductInstances3d", "bounded product geometry"],
  ["data-visual-quality-contract", "observable visual quality contract"],
]) {
  if (!renderer.includes(needle)) fail(`Sprint 1 renderer missing ${label}: ${needle}`);
}

if (/from\s+["']three["']/.test(renderer)) {
  fail("Sprint 1 must preserve dynamic Three.js code splitting.");
}
if (/https?:\/\//.test(renderer)) {
  fail("Canonical Digital Twin must not introduce hard-coded remote visual asset URLs.");
}
if (renderer.includes("production_release_allowed ?") || renderer.includes("productionReleaseAllowed ?")) {
  fail("Preview visual quality must never unlock production publication.");
}

const model = {
  modules: [
    {
      key: "A:M1",
      aisleId: "A",
      moduleId: "M1",
      fixtureType: "regular_shelf",
      widthM: 1.25,
      depthM: 0.62,
      heightM: 2.1,
      shelfCount: 2,
      shelves: [
        { products: [{ sku: "SKU-1", facing_count: 4 }] },
        { products: [] },
      ],
    },
  ],
};
const manifest = {
  product_assets: [{
    sku: "SKU-1",
    front_image_path: "/planogram-assets/products/sku-1.webp",
    source_ref: "pim://SKU-1/front-v1",
    attested: true,
  }],
  fixture_assets: [{
    fixture_type: "REGULAR_SHELF",
    model_path: "/planogram-assets/fixtures/regular-shelf.glb",
    source_ref: "vendor://REGULAR_SHELF/v1",
    attested: true,
  }],
};
const plan = buildPlanogramVisualQualityPlan(model, manifest);
if (!plan) fail("Sprint 1 visual quality plan was not generated.");
if (plan.fixtureInstances.length !== 1 || plan.productTextures.length !== 1) {
  fail("Attested GLB and packshot must both enter the governed render plan.");
}
if (plan.fixtureInstances[0].targetEnvelopeM.widthM !== 1.25
  || plan.fixtureInstances[0].targetEnvelopeM.depthM !== 0.62
  || plan.fixtureInstances[0].targetEnvelopeM.heightM !== 2.1) {
  fail("GLB target envelope must remain exactly canonical StoreScene geometry.");
}
if (plan.productTextures[0].facingCount !== 4) {
  fail("Packshot runtime plan must preserve the real facing count.");
}
if (plan.productionReleaseAllowed !== false) {
  fail("Sprint 1 visual plan must remain preview-only for release authority.");
}
if (qualityConfig.rendering.max_textured_product_skus !== PLANOGRAM_VISUAL_QUALITY_LIMITS.maxTexturedProductSkus
  || qualityConfig.rendering.max_textured_product_facings !== PLANOGRAM_VISUAL_QUALITY_LIMITS.maxTexturedProductFacings) {
  fail("Visual-quality config and runtime budget limits drifted.");
}
if (qualityConfig.visual_truth.geometry_authority !== "canonical_store_scene") {
  fail("Visual quality config must preserve canonical StoreScene geometry authority.");
}
if (qualityConfig.production_release_allowed !== false || qualityConfig.claim_market_leader !== false) {
  fail("Sprint 1 must not promote production or market-leader claims.");
}

console.log("PLANOGRAM_SPRINT1_GOVERNED_GLBS=PASS");
console.log("PLANOGRAM_SPRINT1_PACKSHOT_FACINGS=PASS");
console.log("PLANOGRAM_SPRINT1_PBR_ENVIRONMENT=PASS");
console.log("PLANOGRAM_SPRINT1_METRIC_FALLBACK=PASS");
console.log("PLANOGRAM_SPRINT1_PRODUCTION_AUTHORITY=FALSE");
