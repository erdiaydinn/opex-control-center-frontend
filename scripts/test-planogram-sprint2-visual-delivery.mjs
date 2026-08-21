import process from "node:process";

import { normalizePlanogramAssetManifest } from "../src/modules/planogram/planogramAssetManifest.js";
import {
  buildPlanogramVisualDeliveryPlan,
  PLANOGRAM_VISUAL_DELIVERY_LIMITS,
} from "../src/modules/planogram/planogramVisualDeliveryModel.js";
import {
  buildPlanogramVendorAssetCatalog,
  selectVendorFixtureAsset,
} from "../src/modules/planogram/planogramVendorAssetCatalog.js";
import {
  buildPlanogramUnifiedTwinScene,
  compareUnifiedTwinGeometry,
} from "../src/modules/planogram/planogramUnifiedTwinScene.js";

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

const approvedFixture = {
  id: "4bc7cc43-a9cb-4ed0-a5d1-b04fd0fd6a01",
  status: "approved",
  version_number: 4,
  record_sha256: "a".repeat(64),
  record: {
    fixture_code: "REG-1200-V4",
    fixture_name: "Regular gondola 1200",
    fixture_type: "REGULAR_SHELF",
    source_ref: "survey://fixture/REG-1200-V4",
  },
};
const staleFixture = {
  ...approvedFixture,
  id: "aa8e70d7-860e-40ed-bf37-8c1f7528de26",
  version_number: 3,
  record_sha256: "b".repeat(64),
};
const rejectedFixture = {
  ...approvedFixture,
  id: "3cb0d4bd-9a0b-4b9d-aaf9-a1ead4cbdcee",
  status: "rejected",
  record: { ...approvedFixture.record, fixture_code: "REJECTED-1" },
  record_sha256: "c".repeat(64),
};
const vendorCatalog = buildPlanogramVendorAssetCatalog(
  [staleFixture, approvedFixture, rejectedFixture],
  [
    {
      fixture_code: "REG-1200-V4",
      vendor_id: "VENDOR-A",
      variant_key: "DEFAULT",
      model_path: "/planogram-assets/fixtures/vendor-a-reg-near.glb",
      lod_model_paths: { far: "/planogram-assets/fixtures/vendor-a-reg-far.glb" },
      source_ref: "vendor://VENDOR-A/REG-1200-V4/v8",
      attested: true,
    },
    {
      fixture_code: "REJECTED-1",
      vendor_id: "VENDOR-X",
      variant_key: "DEFAULT",
      model_path: "/planogram-assets/fixtures/rejected.glb",
      source_ref: "vendor://VENDOR-X/rejected",
      attested: true,
    },
  ]
);
if (vendorCatalog.entries.length !== 1) fail("Only current approved fixture catalog rows may receive governed vendor visuals.");
if (vendorCatalog.diagnostics.supersededCatalogVersions !== 1 || vendorCatalog.diagnostics.rejectedCatalogVersions !== 1) {
  fail("Vendor catalog version diagnostics drifted.");
}
const selectedVendor = selectVendorFixtureAsset(vendorCatalog, { fixtureCode: "REG-1200-V4" }, "VENDOR-A");
if (selectedVendor?.modelPath !== "/planogram-assets/fixtures/vendor-a-reg-near.glb") {
  fail("Exact approved fixture code must bind to the attested vendor asset.");
}
if (selectVendorFixtureAsset(vendorCatalog, { fixtureCode: "UNKNOWN" }) !== null) {
  fail("Unknown fixture codes must fail closed instead of type-falling into a vendor asset.");
}
const remoteVendorCatalog = buildPlanogramVendorAssetCatalog([approvedFixture], [{
  fixture_code: "REG-1200-V4",
  vendor_id: "VENDOR-A",
  variant_key: "DEFAULT",
  model_path: "https://cdn.invalid/vendor.glb",
  source_ref: "vendor://VENDOR-A/bad",
  attested: true,
}]);
if (remoteVendorCatalog.entries.length !== 0) fail("Remote vendor GLB must be rejected by the governed catalog.");

const authoredScene = buildPlanogramUnifiedTwinScene({
  authoredModel: {
    contract: "planogram-digital-twin-v1",
    geometryAuthority: "measured-preview-v2",
    architectureSourceRef: "cad://store-42/v3",
    floor: { widthM: 10, depthM: 8 },
    elements: [{ id: "W1", type: "wall", centerXM: 2, centerYM: 1, widthM: 4, depthM: 0.1, rotationDeg: 0, clearanceM: 0, coordinateAuthority: "measured" }],
    modules: [{ key: "A::M1", fixtureType: "REGULAR_SHELF", centerXM: 3, centerYM: 3, widthM: 1, depthM: 0.5, heightM: 2, rotationDeg: 0, coordinateAuthority: "measured" }],
    route: null,
  },
});
const scannedScene = buildPlanogramUnifiedTwinScene({
  reviewedArchitecture: {
    schema_version: 2,
    source_ref: "scan://store-42/review-9",
    floor_width_m: 10,
    floor_depth_m: 8,
    elements: [{ element_id: "W1", element_type: "wall", center_x_m: 2.01, center_y_m: 1, width_m: 4, depth_m: 0.1, rotation_deg: 0 }],
  },
  recognizedFixtures: [{ element_id: "F1", hinted_storage_type: "AMBIENT", center_x_m: 3, center_y_m: 3, width_m: 1, depth_m: 0.5, height_m: 2, rotation_deg: 0 }],
});
if (authoredScene?.contract !== "eay.planogram.unified-twin-scene.v1" || scannedScene?.contract !== authoredScene.contract) {
  fail("Authored and reviewed scan projections must converge on one unified twin scene contract.");
}
if (scannedScene.geometryAuthority !== "reviewed_scan_preview_not_store_dna_authority" || scannedScene.productionReleaseAllowed !== false) {
  fail("Reviewed scan scene must never self-promote to Store DNA or production authority.");
}
const geometryComparison = compareUnifiedTwinGeometry(authoredScene, scannedScene, 0.02);
if (!geometryComparison.comparable || !geometryComparison.withinTolerance) {
  fail("Unified authored/scanned geometry comparison should accept reviewed measurements within tolerance.");
}

console.log("PLANOGRAM_SPRINT2_MANIFEST_V2=PASS");
console.log("PLANOGRAM_SPRINT2_KTX2_FALLBACK=PASS");
console.log("PLANOGRAM_SPRINT2_TEXTURE_ATLAS=PASS");
console.log("PLANOGRAM_SPRINT2_FIXTURE_LOD=PASS");
console.log("PLANOGRAM_SPRINT2_VENDOR_CATALOG=PASS");
console.log("PLANOGRAM_SPRINT2_UNIFIED_TWIN_SCENE=PASS");
console.log("PLANOGRAM_SPRINT2_PRODUCTION_AUTHORITY=FALSE");
