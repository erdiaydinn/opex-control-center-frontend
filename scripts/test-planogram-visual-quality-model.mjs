import process from "node:process";

import {
  buildPlanogramVisualQualityPlan,
  PLANOGRAM_VISUAL_QUALITY_LIMITS,
} from "../src/modules/planogram/planogramVisualQualityModel.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

function fixtureModule(index = 1) {
  return {
    key: `A:M${index}`,
    aisleId: "A",
    moduleId: `M${index}`,
    fixtureType: "regular_shelf",
    widthM: 1,
    depthM: 0.6,
    heightM: 2.1,
    shelfCount: 2,
    shelves: [
      {
        products: [
          { sku: "sku-1", facing_count: 3 },
          { sku: "sku-unattested", facing_count: 2 },
        ],
      },
      { products: [] },
    ],
  };
}

const manifest = {
  product_assets: [
    {
      sku: "SKU-1",
      front_image_path: "/planogram-assets/products/sku-1.webp",
      source_ref: "pim://sku-1/front-v4",
      attested: true,
    },
    {
      sku: "SKU-UNATTESTED",
      front_image_path: "/planogram-assets/products/sku-unattested.webp",
      source_ref: "preview://sku-unattested",
      attested: false,
    },
  ],
  fixture_assets: [
    {
      fixture_type: "REGULAR_SHELF",
      model_path: "/planogram-assets/fixtures/regular-shelf.glb",
      source_ref: "vendor://fixture/regular-shelf/v2",
      attested: true,
    },
  ],
};

const plan = buildPlanogramVisualQualityPlan({ modules: [fixtureModule()] }, manifest);
if (!plan) fail("Visual quality plan must be generated for a digital twin model.");
if (plan.contract !== "eay.planogram.visual-quality-plan.v1") fail("Visual quality contract drifted.");
if (plan.geometryAuthority !== "canonical_store_scene") fail("Visual assets must never replace StoreScene geometry authority.");
if (plan.productionReleaseAllowed !== false) fail("Visual quality must not promote production release authority.");
if (plan.fixtureInstances.length !== 1) fail("Attested fixture GLB should be selected exactly once.");
if (plan.fixtureInstances[0].modelPath !== "/planogram-assets/fixtures/regular-shelf.glb") fail("Fixture model path drifted.");
if (plan.fixtureInstances[0].targetEnvelopeM.widthM !== 1 || plan.fixtureInstances[0].targetEnvelopeM.heightM !== 2.1) {
  fail("Fixture visual asset must remain bounded by the canonical metric envelope.");
}
if (plan.productTextures.length !== 1) fail("Only attested packshots should enter high-fidelity rendering.");
if (plan.productTextures[0].sku !== "SKU-1" || plan.productTextures[0].facingCount !== 3) {
  fail("Packshot plan must preserve normalized SKU and real facing count.");
}
if (plan.diagnostics.rejectedUnattestedProducts !== 1) fail("Unattested product packshot rejection must remain observable.");

const remoteManifest = structuredClone(manifest);
remoteManifest.fixture_assets[0].model_path = "https://cdn.example.com/fixture.glb";
remoteManifest.product_assets[0].front_image_path = "//cdn.example.com/sku.webp";
const remotePlan = buildPlanogramVisualQualityPlan({ modules: [fixtureModule()] }, remoteManifest);
if (remotePlan.fixtureInstances.length !== 0 || remotePlan.productTextures.length !== 0) {
  fail("Visual planner must independently fail closed on remote asset paths.");
}

const manyProducts = Array.from({ length: 80 }, (_, index) => ({
  sku: `SKU-${index + 100}`,
  facing_count: 10,
}));
const budgetModule = fixtureModule(2);
budgetModule.shelves = [{ products: manyProducts }];
const budgetManifest = {
  fixture_assets: [],
  product_assets: manyProducts.map((product) => ({
    sku: product.sku,
    front_image_path: `/planogram-assets/products/${product.sku.toLowerCase()}.webp`,
    source_ref: `pim://${product.sku}`,
    attested: true,
  })),
};
const budgetPlan = buildPlanogramVisualQualityPlan({ modules: [budgetModule] }, budgetManifest);
if (budgetPlan.budgets.usedTexturedProductSkus > PLANOGRAM_VISUAL_QUALITY_LIMITS.maxTexturedProductSkus) {
  fail("Texture SKU budget exceeded.");
}
if (budgetPlan.budgets.usedTexturedProductFacings > PLANOGRAM_VISUAL_QUALITY_LIMITS.maxTexturedProductFacings) {
  fail("Textured facing budget exceeded.");
}
if (budgetPlan.diagnostics.skippedFacingBudget <= 0 && budgetPlan.diagnostics.skippedTextureSkuBudget <= 0) {
  fail("Budget pressure must be visible in diagnostics.");
}

console.log("Planogram governed visual quality planning acceptance passed.");
