import { normalizePlanogramAssetManifest } from "./planogramAssetManifest.js";

const PREVIEW_MODES = new Set(["HYBRID", "CATEGORY", "ABC", "BRAND"]);
const MAX_PRODUCTS = 5000;
const MAX_BASKETS = 5000;
const MAX_SKUS_PER_BASKET = 200;
const MAX_SKU_LENGTH = 160;

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeBasket(raw) {
  if (!isPlainObject(raw)) return null;
  const keys = Object.keys(raw);
  if (keys.length !== 1 || keys[0] !== "skus") return null;
  if (!Array.isArray(raw.skus) || raw.skus.length === 0) return null;
  if (raw.skus.length > MAX_SKUS_PER_BASKET) return null;

  const skus = [];
  for (const value of raw.skus) {
    const sku = String(value ?? "").trim().toUpperCase();
    if (!sku || sku.length > MAX_SKU_LENGTH) return null;
    skus.push(sku);
  }
  return { skus };
}

export function normalizeCandidateBundle(payload) {
  if (!isPlainObject(payload)) return null;
  if (
    !Array.isArray(payload.products) ||
    payload.products.length === 0 ||
    payload.products.length > MAX_PRODUCTS
  ) {
    return null;
  }
  if (!isPlainObject(payload.layout) || !isPlainObject(payload.store_dna)) return null;

  const mode = payload.mode == null ? "HYBRID" : String(payload.mode).trim().toUpperCase();
  if (!PREVIEW_MODES.has(mode)) return null;

  const rawBaskets = payload.order_baskets ?? [];
  if (!Array.isArray(rawBaskets) || rawBaskets.length > MAX_BASKETS) return null;
  const orderBaskets = [];
  for (const raw of rawBaskets) {
    const basket = normalizeBasket(raw);
    if (!basket) return null;
    orderBaskets.push(basket);
  }

  const assetManifest = payload.asset_manifest == null
    ? null
    : normalizePlanogramAssetManifest(payload.asset_manifest);
  if (payload.asset_manifest != null && !assetManifest) return null;

  return {
    products: payload.products,
    layout: payload.layout,
    store_dna: payload.store_dna,
    mode,
    order_baskets: orderBaskets,
    ...(assetManifest ? { asset_manifest: assetManifest } : {}),
  };
}

export const PLANOGRAM_CANDIDATE_LIMITS = Object.freeze({
  maxProducts: MAX_PRODUCTS,
  maxBaskets: MAX_BASKETS,
  maxSkusPerBasket: MAX_SKUS_PER_BASKET,
  maxSkuLength: MAX_SKU_LENGTH,
});
