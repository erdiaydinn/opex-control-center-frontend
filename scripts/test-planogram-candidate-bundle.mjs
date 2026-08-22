import process from "node:process";

import { normalizeCandidateBundle } from "../src/modules/planogram/planogramCandidateBundle.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

function candidateWithManifest(assetManifest) {
  return {
    products: [{ sku: "SKU-1", product_name: "Governed Product" }],
    layout: { store_code: "TEST", aisles: [{ aisle_id: "A", modules: [] }] },
    store_dna: { store_code: "TEST" },
    mode: "HYBRID",
    asset_manifest: assetManifest,
  };
}

const manifest = {
  version: 1,
  source_ref: "fixture-vendor://approved-catalog/v1",
  product_assets: [
    {
      sku: "sku-1",
      front_image_path: "/planogram-assets/products/sku-1-front.webp",
      source_ref: "pim://sku-1/packshot-v4",
      attested: true,
    },
  ],
  fixture_assets: [
    {
      fixture_type: "regular_shelf",
      model_path: "/planogram-assets/fixtures/regular-shelf.glb",
      source_ref: "vendor://fixture/regular-shelf/v2",
      attested: true,
    },
  ],
};

const normalized = normalizeCandidateBundle(candidateWithManifest(manifest));
if (!normalized) fail("Governed same-origin asset manifest must survive candidate normalization.");
if (normalized.asset_manifest?.authority !== "request_supplied_preview_assets") {
  fail("Asset manifest authority boundary drifted.");
}
if (normalized.asset_manifest.product_assets[0].sku !== "SKU-1") {
  fail("Product asset SKU must be normalized for deterministic lookup.");
}
if (normalized.asset_manifest.fixture_assets[0].fixture_type !== "REGULAR_SHELF") {
  fail("Fixture asset key must be normalized for deterministic lookup.");
}

const externalAsset = structuredClone(manifest);
externalAsset.product_assets[0].front_image_path = "https://cdn.example.com/sku-1.webp";
if (normalizeCandidateBundle(candidateWithManifest(externalAsset))) {
  fail("Remote product asset URLs must not bypass the same-origin visual asset boundary.");
}

const protocolRelativeFixture = structuredClone(manifest);
protocolRelativeFixture.fixture_assets[0].model_path = "//cdn.example.com/regular-shelf.glb";
if (normalizeCandidateBundle(candidateWithManifest(protocolRelativeFixture))) {
  fail("Protocol-relative fixture assets must be rejected.");
}

const wrongFixtureFormat = structuredClone(manifest);
wrongFixtureFormat.fixture_assets[0].model_path = "/planogram-assets/fixtures/regular-shelf.gltf";
if (normalizeCandidateBundle(candidateWithManifest(wrongFixtureFormat))) {
  fail("Fixture preview assets must remain bounded to the governed GLB contract.");
}

const duplicateProductAsset = structuredClone(manifest);
duplicateProductAsset.product_assets.push({ ...duplicateProductAsset.product_assets[0] });
if (normalizeCandidateBundle(candidateWithManifest(duplicateProductAsset))) {
  fail("Duplicate SKU visual assets must be rejected to preserve deterministic authority.");
}

const wrongProductNamespace = structuredClone(manifest);
wrongProductNamespace.product_assets[0].front_image_path = "/api/private/sku-1.webp";
if (normalizeCandidateBundle(candidateWithManifest(wrongProductNamespace))) {
  fail("Same-origin product assets outside the governed product namespace must be rejected.");
}

const wrongFixtureNamespace = structuredClone(manifest);
wrongFixtureNamespace.fixture_assets[0].model_path = "/uploads/regular-shelf.glb";
if (normalizeCandidateBundle(candidateWithManifest(wrongFixtureNamespace))) {
  fail("Same-origin fixture assets outside the governed fixture namespace must be rejected.");
}

const traversalProduct = structuredClone(manifest);
traversalProduct.product_assets[0].front_image_path = "/planogram-assets/products/../fixtures/not-a-product.webp";
if (normalizeCandidateBundle(candidateWithManifest(traversalProduct))) {
  fail("Dot-segment traversal inside the product asset namespace must be rejected.");
}

const encodedTraversalFixture = structuredClone(manifest);
encodedTraversalFixture.fixture_assets[0].model_path = "/planogram-assets/fixtures/%2e%2e/secret.glb";
if (normalizeCandidateBundle(candidateWithManifest(encodedTraversalFixture))) {
  fail("Encoded traversal inside the fixture asset namespace must be rejected.");
}

const fragmentAsset = structuredClone(manifest);
fragmentAsset.product_assets[0].front_image_path = "/planogram-assets/products/sku-1.webp#unexpected";
if (normalizeCandidateBundle(candidateWithManifest(fragmentAsset))) {
  fail("Fragment-bearing governed asset paths must be rejected.");
}

const unattested = structuredClone(manifest);
unattested.product_assets[0].attested = false;
unattested.fixture_assets[0].attested = false;
const normalizedUnattested = normalizeCandidateBundle(candidateWithManifest(unattested));
if (!normalizedUnattested) fail("Unattested preview assets may be carried as data without becoming attested visual truth.");
if (normalizedUnattested.asset_manifest.product_assets[0].attested !== false) {
  fail("Unattested product asset status was silently promoted.");
}

console.log("Planogram candidate governed asset manifest acceptance passed.");
