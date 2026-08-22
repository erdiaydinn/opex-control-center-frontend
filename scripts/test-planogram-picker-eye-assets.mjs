import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_PICKER_EYE_MESSAGES } from "../src/platform/i18n/planogramPickerEyeMessages.js";
import { normalizeCandidateBundle } from "../src/modules/planogram/planogramCandidateBundle.js";
import { normalizePlanogramAssetManifest } from "../src/modules/planogram/planogramAssetManifest.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const englishKeys = Object.keys(PLANOGRAM_PICKER_EYE_MESSAGES.en).sort();
for (const { code } of SUPPORTED_LOCALES) {
  const table = PLANOGRAM_PICKER_EYE_MESSAGES[code];
  if (!table) fail(`Missing Picker Eye locale: ${code}`);
  if (JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(englishKeys)) {
    fail(`Picker Eye locale coverage drifted: ${code}`);
  }
}

const manifest = {
  version: 1,
  source_ref: "catalog://asset-release-2026-08",
  product_assets: [
    {
      sku: "SKU-1",
      front_image_path: "/planogram-assets/products/SKU-1.webp",
      source_ref: "catalog://SKU-1",
      attested: true,
    },
  ],
  fixture_assets: [
    {
      fixture_type: "CHILLED",
      model_path: "/planogram-assets/fixtures/chilled.glb",
      source_ref: "fixture://chilled-v1",
      attested: true,
    },
  ],
};
const normalized = normalizePlanogramAssetManifest(manifest);
if (!normalized || normalized.product_assets[0].sku !== "SKU-1") fail("Valid governed same-origin asset manifest was rejected.");

for (const forged of [
  { ...manifest, product_assets: [{ ...manifest.product_assets[0], front_image_path: "https://tracker.invalid/sku.webp" }] },
  { ...manifest, product_assets: [{ ...manifest.product_assets[0], front_image_path: "data:image/png;base64,AA" }] },
  { ...manifest, fixture_assets: [{ ...manifest.fixture_assets[0], model_path: "//cdn.invalid/chilled.glb" }] },
  { ...manifest, fixture_assets: [{ ...manifest.fixture_assets[0], model_path: "/planogram-assets/fixtures/chilled.fbx" }] },
  { ...manifest, product_assets: [{ ...manifest.product_assets[0], front_image_path: "/assets/products/SKU-1.webp" }] },
  { ...manifest, fixture_assets: [{ ...manifest.fixture_assets[0], model_path: "/assets/fixtures/chilled.glb" }] },
  { ...manifest, product_assets: [manifest.product_assets[0], manifest.product_assets[0]] },
]) {
  if (normalizePlanogramAssetManifest(forged) !== null) fail("Unsafe, legacy-namespace, or ambiguous asset manifest was accepted.");
}

const bundle = normalizeCandidateBundle({
  products: [{ sku: "SKU-1" }],
  layout: { aisles: [] },
  store_dna: {},
  order_baskets: [{ skus: ["SKU-1"] }],
  asset_manifest: manifest,
});
if (!bundle?.asset_manifest || bundle.asset_manifest.authority !== "request_supplied_preview_assets") {
  fail("Candidate bundle dropped the safe preview asset manifest.");
}
if (normalizeCandidateBundle({ ...bundle, asset_manifest: { ...manifest, product_assets: [{ ...manifest.product_assets[0], front_image_path: "https://evil.invalid/a.webp" }] } }) !== null) {
  fail("Candidate bundle accepted an unsafe remote asset manifest.");
}

const component = fs.readFileSync("src/modules/planogram/PlanogramPickerEyePreview.jsx", "utf8");
for (const needle of [
  "GLTFLoader",
  "buildProductAssetIndex",
  "buildFixtureAssetIndex",
  "pickerEntryM",
  "EYE_HEIGHT_M = 1.62",
  "front_image_path",
  "model_path",
]) {
  if (!component.includes(needle)) fail(`Picker Eye asset contract missing: ${needle}`);
}
const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
if (!studio.includes("<PlanogramPickerEyePreview")) fail("Planogram Studio does not expose Picker Eye preview.");

console.log("Planogram Picker Eye governed same-origin pack and fixture asset boundary: PASS");
