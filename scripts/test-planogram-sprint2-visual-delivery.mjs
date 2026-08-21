import process from "node:process";

import { normalizePlanogramAssetManifest } from "../src/modules/planogram/planogramAssetManifest.js";
import {
  buildPlanogramVisualDeliveryPlan,
  PLANOGRAM_VISUAL_DELIVERY_LIMITS,
} from "../src/modules/planogram/planogramVisualDeliveryModel.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const model = {
  modules: [
    {
      key: "A:M1",
      fixtureType: "regular_shelf",
      shelves: [{ products: [{ sku: "SKU-1" }, { sku: "SKU-2" }] }],
    },
    {
      key: "B:M1",
      fixtureType: "chilled",
      shelves: [{ products: [{ sku: "SKU-3" }] }],
    },
  ],
};

const manifest = normalizePlanogramAssetManifest({
  version: 2,
  source_ref: "vendor-catalog://approved/2026-08-22",
  product_assets: [
    {
      sku: "SKU-1",
      front_image_path: "/planogram-assets/products/sku-1.webp",
      ktx2_path: "/planogram-assets/products/sku-1.ktx2",
      source_ref: "pim://SKU-1/v5",
      attested: true,
    },
    {
      sku: "SKU-2",
      front_image_path: "/planogram-assets/products/sku-2.webp",
      atlas_path: "/planogram-assets/atlases/ambient-a.webp",
      atlas_uv: [0, 0, 0.25, 0.5],
      source_ref: "pim://SKU-2/v7",
      attested: true,
    },
    {
      sku: "SKU-3",
      front_image_path: "/planogram-assets/products/sku-3.webp",
      source_ref: "pim://SKU-3/v1",
      attested: true,
    },
  ],
  fixture_assets: [
    {
      fixture_type: "REGULAR_SHELF",
      model_path: "/planogram-assets/fixtures/regular-near.glb",
      lod_model_paths: {
        medium: "/planogram-assets/fixtures/regular-medium.glb",
        far: "/planogram-assets/fixtures/regular-far.glb",
      },
      source_ref: "vendor://regular/v4",
      attested: true,
    },
    {
      fixture_type: "CHILLED",
      model_path: "/planogram-assets/fixtures/chilled.glb",
      source_ref: "vendor://chilled/v2",
      attested: true,
    },
  ],
});

if (!manifest || manifest.version !== 2) fail("Asset manifest v2 did not normalize.");
if (manifest.fixture_assets[0].lod_model_paths?.far !== "/planogram-assets/fixtures/regular-far.glb") {
  fail("Fixture LOD paths were not preserved.");
}

const capable = buildPlanogramVisualDeliveryPlan(model, manifest, { ktx2: true, textureAtlas: true });
if (!capable || capable.contract !== "eay.planogram.visual-delivery-plan.v2") fail("Sprint 2 delivery contract drifted.");
if (capable.geometryAuthority !== "canonical_store_scene") fail("Visual delivery must never replace StoreScene geometry authority.");
if (capable.productionReleaseAllowed !== false) fail("Visual delivery must remain preview-only for release authority.");
const sku1 = capable.products.find((row) => row.sku === "SKU-1");
const sku2 = capable.products.find((row) => row.sku === "SKU-2");
const sku3 = capable.products.find((row) => row.sku === "SKU-3");
if (sku1?.mode !== "ktx2" || sku1.fallbackPath !== "/planogram-assets/products/sku-1.webp") {
  fail("KTX2 delivery must retain packshot fallback.");
}
if (sku2?.mode !== "atlas" || JSON.stringify(sku2.atlasUv) !== JSON.stringify([0, 0, 0.25, 0.5])) {
  fail("Atlas delivery or UV contract drifted.");
}
if (sku3?.mode !== "packshot") fail("Products without accelerated formats must retain packshot delivery.");
const regular = capable.fixtures.find((row) => row.fixtureType === "REGULAR_SHELF");
if (regular?.mode !== "lod" || regular.levels.length !== 3) fail("Fixture LOD chain missing.");
if (regular.levels[1].distanceM !== PLANOGRAM_VISUAL_DELIVERY_LIMITS.mediumLodDistanceM
  || regular.levels[2].distanceM !== PLANOGRAM_VISUAL_DELIVERY_LIMITS.farLodDistanceM) {
  fail("Fixture LOD thresholds drifted.");
}

const fallback = buildPlanogramVisualDeliveryPlan(model, manifest, { ktx2: false, textureAtlas: false });
if (fallback.products.some((row) => row.mode !== "packshot")) {
  fail("Unsupported acceleration capabilities must fall back to packshots.");
}

for (const forged of [
  {
    version: 2,
    source_ref: "bad://ktx2",
    product_assets: [{
      sku: "SKU-1",
      front_image_path: "/planogram-assets/products/sku-1.webp",
      ktx2_path: "https://cdn.invalid/sku-1.ktx2",
      source_ref: "pim://SKU-1",
      attested: true,
    }],
    fixture_assets: [],
  },
  {
    version: 2,
    source_ref: "bad://atlas",
    product_assets: [{
      sku: "SKU-1",
      front_image_path: "/planogram-assets/products/sku-1.webp",
      atlas_path: "/planogram-assets/atlases/a.webp",
      atlas_uv: [-0.1, 0, 1, 1],
      source_ref: "pim://SKU-1",
      attested: true,
    }],
    fixture_assets: [],
  },
  {
    version: 2,
    source_ref: "bad://lod",
    product_assets: [],
    fixture_assets: [{
      fixture_type: "REGULAR_SHELF",
      model_path: "/planogram-assets/fixtures/regular.glb",
      lod_model_paths: { far: "/planogram-assets/products/not-a-fixture.glb" },
      source_ref: "vendor://regular",
      attested: true,
    }],
  },
]) {
  if (normalizePlanogramAssetManifest(forged) !== null) fail("Unsafe Sprint 2 visual delivery asset was accepted.");
}

console.log("PLANOGRAM_SPRINT2_MANIFEST_V2=PASS");
console.log("PLANOGRAM_SPRINT2_KTX2_FALLBACK=PASS");
console.log("PLANOGRAM_SPRINT2_TEXTURE_ATLAS=PASS");
console.log("PLANOGRAM_SPRINT2_FIXTURE_LOD=PASS");
console.log("PLANOGRAM_SPRINT2_PRODUCTION_AUTHORITY=FALSE");
