import {
  buildFixtureAssetIndex,
  buildProductAssetIndex,
} from "./planogramAssetManifest.js";

const DEFAULT_MEDIUM_LOD_DISTANCE_M = 6;
const DEFAULT_FAR_LOD_DISTANCE_M = 14;
const MAX_KTX2_SKUS = 96;
const MAX_ATLAS_SKUS = 192;

function normalizeSku(value) {
  return String(value ?? "").trim().toUpperCase();
}

function normalizeFixtureType(value) {
  return String(value ?? "").trim().toUpperCase();
}

function collectModelSkus(model) {
  const skus = new Set();
  for (const module of model?.modules || []) {
    for (const shelf of module?.shelves || []) {
      for (const product of shelf?.products || []) {
        const sku = normalizeSku(product?.sku ?? product?.SKU);
        if (sku) skus.add(sku);
      }
    }
  }
  return skus;
}

function collectFixtureTypes(model) {
  const fixtureTypes = new Set();
  for (const module of model?.modules || []) {
    const fixtureType = normalizeFixtureType(module?.fixtureType ?? module?.fixture_type);
    if (fixtureType) fixtureTypes.add(fixtureType);
  }
  return fixtureTypes;
}

function productDelivery(asset, capabilities, counters) {
  if (!asset || asset.attested !== true) return null;

  if (capabilities.textureAtlas === true && asset.atlas_path && Array.isArray(asset.atlas_uv)) {
    if (counters.atlasSkus < MAX_ATLAS_SKUS) {
      counters.atlasSkus += 1;
      return Object.freeze({
        mode: "atlas",
        path: asset.atlas_path,
        atlasUv: Object.freeze([...asset.atlas_uv]),
        fallbackPath: asset.front_image_path,
        authority: "attested_same_origin_atlas",
      });
    }
  }

  if (capabilities.ktx2 === true && asset.ktx2_path) {
    if (counters.ktx2Skus < MAX_KTX2_SKUS) {
      counters.ktx2Skus += 1;
      return Object.freeze({
        mode: "ktx2",
        path: asset.ktx2_path,
        fallbackPath: asset.front_image_path,
        authority: "attested_same_origin_ktx2",
      });
    }
  }

  return Object.freeze({
    mode: "packshot",
    path: asset.front_image_path,
    fallbackPath: asset.front_image_path,
    authority: "attested_same_origin_packshot",
  });
}

function fixtureDelivery(asset) {
  if (!asset || asset.attested !== true) return null;
  const levels = [
    Object.freeze({ distanceM: 0, path: asset.model_path, quality: "near" }),
  ];
  if (asset.lod_model_paths?.medium) {
    levels.push(Object.freeze({
      distanceM: DEFAULT_MEDIUM_LOD_DISTANCE_M,
      path: asset.lod_model_paths.medium,
      quality: "medium",
    }));
  }
  if (asset.lod_model_paths?.far) {
    levels.push(Object.freeze({
      distanceM: DEFAULT_FAR_LOD_DISTANCE_M,
      path: asset.lod_model_paths.far,
      quality: "far",
    }));
  }
  return Object.freeze({
    mode: levels.length > 1 ? "lod" : "single_glb",
    authority: "attested_same_origin_glb",
    levels: Object.freeze(levels),
  });
}

export function buildPlanogramVisualDeliveryPlan(model, assetManifest, capabilities = {}) {
  if (!model || !Array.isArray(model.modules)) return null;

  const productIndex = buildProductAssetIndex(assetManifest);
  const fixtureIndex = buildFixtureAssetIndex(assetManifest);
  const skus = collectModelSkus(model);
  const fixtureTypes = collectFixtureTypes(model);
  const counters = { ktx2Skus: 0, atlasSkus: 0 };
  const products = [];
  const fixtures = [];
  let missingProductAsset = 0;
  let missingFixtureAsset = 0;

  for (const sku of skus) {
    const delivery = productDelivery(productIndex.get(sku), capabilities, counters);
    if (!delivery) {
      missingProductAsset += 1;
      continue;
    }
    products.push(Object.freeze({ sku, ...delivery }));
  }

  for (const fixtureType of fixtureTypes) {
    const delivery = fixtureDelivery(fixtureIndex.get(fixtureType));
    if (!delivery) {
      missingFixtureAsset += 1;
      continue;
    }
    fixtures.push(Object.freeze({ fixtureType, ...delivery }));
  }

  return Object.freeze({
    contract: "eay.planogram.visual-delivery-plan.v2",
    geometryAuthority: "canonical_store_scene",
    productionReleaseAllowed: false,
    capabilities: Object.freeze({
      ktx2: capabilities.ktx2 === true,
      textureAtlas: capabilities.textureAtlas === true,
    }),
    products: Object.freeze(products),
    fixtures: Object.freeze(fixtures),
    budgets: Object.freeze({
      maxKtx2Skus: MAX_KTX2_SKUS,
      maxAtlasSkus: MAX_ATLAS_SKUS,
      usedKtx2Skus: counters.ktx2Skus,
      usedAtlasSkus: counters.atlasSkus,
    }),
    diagnostics: Object.freeze({
      missingProductAsset,
      missingFixtureAsset,
    }),
  });
}

export const PLANOGRAM_VISUAL_DELIVERY_LIMITS = Object.freeze({
  mediumLodDistanceM: DEFAULT_MEDIUM_LOD_DISTANCE_M,
  farLodDistanceM: DEFAULT_FAR_LOD_DISTANCE_M,
  maxKtx2Skus: MAX_KTX2_SKUS,
  maxAtlasSkus: MAX_ATLAS_SKUS,
});
