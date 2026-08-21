import {
  buildFixtureAssetIndex,
  buildProductAssetIndex,
  PLANOGRAM_ASSET_LIMITS,
} from "./planogramAssetManifest.js";

const MAX_TEXTURED_PRODUCT_SKUS = 48;
const MAX_TEXTURED_PRODUCT_FACINGS = 320;
const MAX_GOVERNED_FIXTURE_INSTANCES = 1000;

function finitePositive(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function normalizeKey(value) {
  return String(value ?? "").trim().toUpperCase();
}

function safeGovernedPath(value, expectedPrefix) {
  const path = String(value ?? "").trim();
  if (!path || !path.startsWith("/") || path.startsWith("//") || path.includes("\\")) return false;
  if (path.includes("#") || /%(?:2e|2f|5c|00)/i.test(path)) return false;
  const pathname = path.split("?", 1)[0];
  if (!pathname.startsWith(expectedPrefix)) return false;
  return !pathname.split("/").some((segment) => segment === "." || segment === "..");
}

function productFacingCount(product) {
  const value = Number(product?.facing_count ?? product?.facing ?? 1);
  if (!Number.isFinite(value)) return 1;
  return Math.max(1, Math.min(40, Math.round(value)));
}

function moduleHeightM(module) {
  const measured = finitePositive(module?.heightM);
  if (measured != null) return measured;
  const shelfCount = Math.max(1, Number(module?.shelfCount || module?.shelves?.length || 1));
  return Math.max(1.5, shelfCount * 0.32);
}

function moduleEnvelope(module) {
  const widthM = finitePositive(module?.widthM);
  const depthM = finitePositive(module?.depthM);
  const heightM = finitePositive(moduleHeightM(module));
  if (widthM == null || depthM == null || heightM == null) return null;
  return Object.freeze({ widthM, depthM, heightM });
}

function moduleFixtureKey(module) {
  return normalizeKey(module?.fixtureType ?? module?.fixture_type);
}

function moduleStableKey(module, index) {
  return String(
    module?.key
      ?? module?.moduleKey
      ?? `${module?.aisleId ?? module?.aisle_id ?? "AISLE"}:${module?.moduleId ?? module?.module_id ?? index + 1}`
  );
}

function productSku(product) {
  return normalizeKey(product?.sku ?? product?.SKU);
}

function collectModuleProducts(module) {
  const rows = [];
  const shelves = Array.isArray(module?.shelves) ? module.shelves : [];
  for (let shelfIndex = 0; shelfIndex < shelves.length; shelfIndex += 1) {
    const products = Array.isArray(shelves[shelfIndex]?.products) ? shelves[shelfIndex].products : [];
    for (let productIndex = 0; productIndex < products.length; productIndex += 1) {
      rows.push({
        shelfIndex,
        productIndex,
        product: products[productIndex],
      });
    }
  }
  return rows;
}

function visualAssetEligible(asset, expectedExtension, expectedPrefix) {
  if (!asset || asset.attested !== true) return false;
  const path = String(asset.model_path ?? asset.front_image_path ?? "");
  if (!safeGovernedPath(path, expectedPrefix)) return false;
  return expectedExtension.test(path);
}

export function buildPlanogramVisualQualityPlan(model, assetManifest) {
  if (!model || !Array.isArray(model.modules)) return null;

  const fixtureIndex = buildFixtureAssetIndex(assetManifest);
  const productIndex = buildProductAssetIndex(assetManifest);
  const fixtureInstances = [];
  const productTextures = [];
  const textureSkuSet = new Set();
  let acceptedTexturedFacings = 0;
  let rejectedUnattestedFixtures = 0;
  let rejectedUnattestedProducts = 0;
  let skippedFixtureBudget = 0;
  let skippedTextureSkuBudget = 0;
  let skippedFacingBudget = 0;

  for (let moduleIndex = 0; moduleIndex < model.modules.length; moduleIndex += 1) {
    const module = model.modules[moduleIndex];
    const moduleKey = moduleStableKey(module, moduleIndex);
    const fixtureKey = moduleFixtureKey(module);
    const envelope = moduleEnvelope(module);
    const fixtureAsset = fixtureIndex.get(fixtureKey);

    if (fixtureAsset) {
      if (!visualAssetEligible(fixtureAsset, /\.glb(\?.*)?$/i, PLANOGRAM_ASSET_LIMITS.fixtureAssetPrefix)) {
        rejectedUnattestedFixtures += 1;
      } else if (!envelope) {
        rejectedUnattestedFixtures += 1;
      } else if (fixtureInstances.length >= MAX_GOVERNED_FIXTURE_INSTANCES) {
        skippedFixtureBudget += 1;
      } else {
        fixtureInstances.push(Object.freeze({
          moduleKey,
          fixtureType: fixtureKey,
          modelPath: fixtureAsset.model_path,
          sourceRef: fixtureAsset.source_ref,
          targetEnvelopeM: envelope,
          geometryAuthority: "canonical_store_scene",
          visualAssetAuthority: "attested_same_origin_glb",
          fallbackPolicy: "metric_primitive_until_asset_load_success",
        }));
      }
    }

    for (const row of collectModuleProducts(module)) {
      const sku = productSku(row.product);
      if (!sku) continue;
      const productAsset = productIndex.get(sku);
      if (!productAsset) continue;
      if (!visualAssetEligible(productAsset, /\.(png|jpe?g|webp|avif)(\?.*)?$/i, PLANOGRAM_ASSET_LIMITS.productAssetPrefix)) {
        rejectedUnattestedProducts += 1;
        continue;
      }

      const facingCount = productFacingCount(row.product);
      const isNewSku = !textureSkuSet.has(sku);
      if (isNewSku && textureSkuSet.size >= MAX_TEXTURED_PRODUCT_SKUS) {
        skippedTextureSkuBudget += facingCount;
        continue;
      }
      const remainingFacingBudget = MAX_TEXTURED_PRODUCT_FACINGS - acceptedTexturedFacings;
      if (remainingFacingBudget <= 0) {
        skippedFacingBudget += facingCount;
        continue;
      }

      const acceptedFacingCount = Math.min(facingCount, remainingFacingBudget);
      if (isNewSku) textureSkuSet.add(sku);
      acceptedTexturedFacings += acceptedFacingCount;
      skippedFacingBudget += Math.max(0, facingCount - acceptedFacingCount);
      productTextures.push(Object.freeze({
        moduleKey,
        shelfIndex: row.shelfIndex,
        productIndex: row.productIndex,
        sku,
        facingCount: acceptedFacingCount,
        frontImagePath: productAsset.front_image_path,
        sourceRef: productAsset.source_ref,
        geometryAuthority: "canonical_store_scene_facing_transform",
        visualAssetAuthority: "attested_same_origin_packshot",
      }));
    }
  }

  return Object.freeze({
    contract: "eay.planogram.visual-quality-plan.v1",
    geometryAuthority: "canonical_store_scene",
    visualAuthority: "attested_same_origin_preview_assets",
    productionReleaseAllowed: false,
    fixtureInstances: Object.freeze(fixtureInstances),
    productTextures: Object.freeze(productTextures),
    budgets: Object.freeze({
      maxFixtureInstances: MAX_GOVERNED_FIXTURE_INSTANCES,
      maxTexturedProductSkus: MAX_TEXTURED_PRODUCT_SKUS,
      maxTexturedProductFacings: MAX_TEXTURED_PRODUCT_FACINGS,
      usedFixtureInstances: fixtureInstances.length,
      usedTexturedProductSkus: textureSkuSet.size,
      usedTexturedProductFacings: acceptedTexturedFacings,
    }),
    diagnostics: Object.freeze({
      rejectedUnattestedFixtures,
      rejectedUnattestedProducts,
      skippedFixtureBudget,
      skippedTextureSkuBudget,
      skippedFacingBudget,
    }),
  });
}

export const PLANOGRAM_VISUAL_QUALITY_LIMITS = Object.freeze({
  maxFixtureInstances: MAX_GOVERNED_FIXTURE_INSTANCES,
  maxTexturedProductSkus: MAX_TEXTURED_PRODUCT_SKUS,
  maxTexturedProductFacings: MAX_TEXTURED_PRODUCT_FACINGS,
});
