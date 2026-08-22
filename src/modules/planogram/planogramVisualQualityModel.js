import {
  buildFixtureAssetIndex,
  buildProductAssetIndex,
  PLANOGRAM_ASSET_LIMITS,
} from "./planogramAssetManifest.js";

const MAX_TEXTURED_PRODUCT_SKUS = 48;
const MAX_TEXTURED_PRODUCT_FACINGS = 320;
const MAX_GOVERNED_FIXTURE_INSTANCES = 1000;
const MEDIUM_LOD_DISTANCE_M = 6;
const FAR_LOD_DISTANCE_M = 14;

function finitePositive(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function finiteCoordinate(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
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
  const fixtureType = String(module?.fixtureType ?? module?.fixture_type ?? "").toLowerCase();
  if (fixtureType.includes("pallet")) return 0.18;
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

function cadVisualFixtureEligible(module) {
  return module?.sourceKind === "cad_overlay_preview"
    && module?.coordinateAuthority === "human_cad_preview"
    && module?.productionReleaseAllowed === false
    && module?.physicalTruthAttested === false;
}

function visualFocusPoint(model) {
  const picker = model?.route?.pickerEntryM;
  if (Array.isArray(picker) && picker.length >= 2) {
    const xM = finiteCoordinate(picker[0]);
    const yM = finiteCoordinate(picker[1]);
    if (xM != null && yM != null) return Object.freeze({ xM, yM, source: "picker_entry" });
  }
  const widthM = finitePositive(model?.floor?.widthM);
  const depthM = finitePositive(model?.floor?.depthM);
  if (widthM != null && depthM != null) {
    return Object.freeze({ xM: widthM / 2, yM: depthM / 2, source: "floor_center" });
  }
  return Object.freeze({ xM: 0, yM: 0, source: "origin_fallback" });
}

function moduleDistanceM(module, focus) {
  const xM = finiteCoordinate(module?.centerXM ?? module?.center_x_m);
  const yM = finiteCoordinate(module?.centerYM ?? module?.center_y_m);
  if (xM == null || yM == null) return 0;
  return Math.hypot(xM - focus.xM, yM - focus.yM);
}

function governedLodPath(asset, distanceM) {
  const near = asset?.model_path;
  const medium = asset?.lod_model_paths?.medium;
  const far = asset?.lod_model_paths?.far;
  if (
    distanceM >= FAR_LOD_DISTANCE_M
    && safeGovernedPath(far, PLANOGRAM_ASSET_LIMITS.fixtureAssetPrefix)
    && /\.glb(\?.*)?$/i.test(far)
  ) {
    return Object.freeze({ modelPath: far, quality: "far" });
  }
  if (
    distanceM >= MEDIUM_LOD_DISTANCE_M
    && safeGovernedPath(medium, PLANOGRAM_ASSET_LIMITS.fixtureAssetPrefix)
    && /\.glb(\?.*)?$/i.test(medium)
  ) {
    return Object.freeze({ modelPath: medium, quality: "medium" });
  }
  return Object.freeze({ modelPath: near, quality: "near" });
}

export function buildPlanogramVisualQualityPlan(model, assetManifest) {
  if (!model || !Array.isArray(model.modules)) return null;

  const fixtureIndex = buildFixtureAssetIndex(assetManifest);
  const productIndex = buildProductAssetIndex(assetManifest);
  const fixtureInstances = [];
  const productTextures = [];
  const textureSkuSet = new Set();
  const focus = visualFocusPoint(model);
  const cadFixtures = Array.isArray(model.cadFixtures) ? model.cadFixtures : [];
  const visualFixtures = [...model.modules, ...cadFixtures.filter(cadVisualFixtureEligible)];
  let acceptedTexturedFacings = 0;
  let rejectedUnattestedFixtures = 0;
  let rejectedUnattestedProducts = 0;
  let rejectedCadFixtureAuthority = cadFixtures.length - visualFixtures.length + model.modules.length;
  let skippedFixtureBudget = 0;
  let skippedTextureSkuBudget = 0;
  let skippedFacingBudget = 0;
  let usedMediumLod = 0;
  let usedFarLod = 0;

  for (let moduleIndex = 0; moduleIndex < visualFixtures.length; moduleIndex += 1) {
    const module = visualFixtures[moduleIndex];
    const moduleKey = moduleStableKey(module, moduleIndex);
    const fixtureKey = moduleFixtureKey(module);
    const envelope = moduleEnvelope(module);
    const fixtureAsset = fixtureIndex.get(fixtureKey);

    if (!fixtureAsset) continue;
    if (!visualAssetEligible(fixtureAsset, /\.glb(\?.*)?$/i, PLANOGRAM_ASSET_LIMITS.fixtureAssetPrefix)) {
      rejectedUnattestedFixtures += 1;
    } else if (!envelope) {
      rejectedUnattestedFixtures += 1;
    } else if (fixtureInstances.length >= MAX_GOVERNED_FIXTURE_INSTANCES) {
      skippedFixtureBudget += 1;
    } else {
      const distanceM = moduleDistanceM(module, focus);
      const lod = governedLodPath(fixtureAsset, distanceM);
      if (lod.quality === "medium") usedMediumLod += 1;
      if (lod.quality === "far") usedFarLod += 1;
      fixtureInstances.push(Object.freeze({
        moduleKey,
        fixtureType: fixtureKey,
        modelPath: lod.modelPath,
        sourceRef: fixtureAsset.source_ref,
        targetEnvelopeM: envelope,
        sourceKind: String(module?.sourceKind || "engine_planogram"),
        coordinateAuthority: String(module?.coordinateAuthority || "canonical_store_scene"),
        previewOnly: module?.sourceKind === "cad_overlay_preview",
        productionReleaseAllowed: false,
        geometryAuthority: "canonical_store_scene",
        visualAssetAuthority: "attested_same_origin_glb",
        fallbackPolicy: "metric_primitive_until_asset_load_success",
        lodQuality: lod.quality,
        lodDistanceM: Math.round(distanceM * 100) / 100,
        lodFocusSource: focus.source,
        lodPolicy: "deterministic_focus_distance_preview",
      }));
    }
  }

  for (let moduleIndex = 0; moduleIndex < model.modules.length; moduleIndex += 1) {
    const module = model.modules[moduleIndex];
    const moduleKey = moduleStableKey(module, moduleIndex);
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
    lod: Object.freeze({
      focusSource: focus.source,
      mediumDistanceM: MEDIUM_LOD_DISTANCE_M,
      farDistanceM: FAR_LOD_DISTANCE_M,
    }),
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
      rejectedCadFixtureAuthority,
      skippedFixtureBudget,
      skippedTextureSkuBudget,
      skippedFacingBudget,
      usedMediumLod,
      usedFarLod,
    }),
  });
}

export const PLANOGRAM_VISUAL_QUALITY_LIMITS = Object.freeze({
  maxFixtureInstances: MAX_GOVERNED_FIXTURE_INSTANCES,
  maxTexturedProductSkus: MAX_TEXTURED_PRODUCT_SKUS,
  maxTexturedProductFacings: MAX_TEXTURED_PRODUCT_FACINGS,
  mediumLodDistanceM: MEDIUM_LOD_DISTANCE_M,
  farLodDistanceM: FAR_LOD_DISTANCE_M,
});
