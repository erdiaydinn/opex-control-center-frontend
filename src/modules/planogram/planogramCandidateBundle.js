import { normalizePlanogramAssetManifest } from "./planogramAssetManifest.js";

const PREVIEW_MODES = new Set(["HYBRID", "CATEGORY", "ABC", "BRAND"]);
const MAX_PRODUCTS = 5000;
const MAX_BASKETS = 5000;
const MAX_SKUS_PER_BASKET = 200;
const MAX_SKU_LENGTH = 160;
const MAX_RETAIL_PAIRS = 5000;
const MAX_REALOGRAM_EVENTS = 100000;
const MAX_SUBSTITUTION_EDGES = 50000;
const MAX_SHELF_SCAN_SHELVES = 2000;
const MAX_SHELF_SCAN_OBSERVATIONS = 20000;
const MAX_BLIND_AISLES = 2000;
const RETAIL_KEYS = new Set([
  "store_code",
  "category_capacity_cm",
  "total_shelf_width_cm",
  "substitution_edges",
  "objective_weights",
  "historical_pairs",
  "metric_directions",
  "minimum_backtest_pairs",
  "blind_candidate_a",
  "blind_candidate_b",
  "shelf_scan_shelves",
  "shelf_scan_observations",
  "min_detection_confidence",
  "min_image_quality",
  "max_occlusion_pct",
  "realogram_events",
  "as_of",
  "stale_after_minutes",
  "require_images",
]);
const FORBIDDEN_IDENTITY_KEYS = new Set([
  "customer",
  "customer_id",
  "customer_name",
  "email",
  "email_address",
  "phone",
  "phone_number",
  "mobile",
  "address",
  "full_name",
  "first_name",
  "last_name",
  "order_id",
  "order_code",
  "payment_token",
  "card_number",
  "user_email",
  "user_id",
]);

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizedKey(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function containsForbiddenIdentity(value, depth = 0, state = { nodes: 0 }) {
  state.nodes += 1;
  if (depth > 12 || state.nodes > 250000) return true;
  if (Array.isArray(value)) {
    return value.some((item) => containsForbiddenIdentity(item, depth + 1, state));
  }
  if (!isPlainObject(value)) return false;
  for (const [key, nested] of Object.entries(value)) {
    if (FORBIDDEN_IDENTITY_KEYS.has(normalizedKey(key))) return true;
    if (containsForbiddenIdentity(nested, depth + 1, state)) return true;
  }
  return false;
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

function validBlindCandidate(raw) {
  if (!isPlainObject(raw)) return false;
  const keys = Object.keys(raw);
  if (keys.length !== 1 || keys[0] !== "planogram") return false;
  if (!isPlainObject(raw.planogram)) return false;
  const aisles = raw.planogram.aisles;
  return Array.isArray(aisles) && aisles.length > 0 && aisles.length <= MAX_BLIND_AISLES;
}

function validOptionalNumber(raw, key, min, max) {
  if (raw[key] == null) return true;
  const value = Number(raw[key]);
  return Number.isFinite(value) && value >= min && value <= max;
}

function normalizeRetailIntelligence(raw) {
  if (raw == null) return null;
  if (!isPlainObject(raw) || containsForbiddenIdentity(raw)) return null;
  if (Object.keys(raw).some((key) => !RETAIL_KEYS.has(key))) return null;

  const storeCode = String(raw.store_code ?? "").trim();
  if (!storeCode || storeCode.length > 80 || !/^[A-Za-z0-9._-]+$/.test(storeCode)) {
    return null;
  }

  const substitutionEdges = raw.substitution_edges ?? [];
  const historicalPairs = raw.historical_pairs ?? [];
  const realogramEvents = raw.realogram_events ?? [];
  const shelfScanShelves = raw.shelf_scan_shelves ?? [];
  const shelfScanObservations = raw.shelf_scan_observations ?? [];
  if (
    !Array.isArray(substitutionEdges)
    || substitutionEdges.length > MAX_SUBSTITUTION_EDGES
    || !Array.isArray(historicalPairs)
    || historicalPairs.length > MAX_RETAIL_PAIRS
    || !Array.isArray(realogramEvents)
    || realogramEvents.length > MAX_REALOGRAM_EVENTS
    || !Array.isArray(shelfScanShelves)
    || shelfScanShelves.length > MAX_SHELF_SCAN_SHELVES
    || !Array.isArray(shelfScanObservations)
    || shelfScanObservations.length > MAX_SHELF_SCAN_OBSERVATIONS
  ) {
    return null;
  }
  if (shelfScanObservations.length && !shelfScanShelves.length) return null;

  const blindA = raw.blind_candidate_a ?? null;
  const blindB = raw.blind_candidate_b ?? null;
  if (Boolean(blindA) !== Boolean(blindB)) return null;
  if ((blindA && !validBlindCandidate(blindA)) || (blindB && !validBlindCandidate(blindB))) {
    return null;
  }

  if (
    !validOptionalNumber(raw, "min_detection_confidence", 0.5, 1)
    || !validOptionalNumber(raw, "min_image_quality", 0, 1)
    || !validOptionalNumber(raw, "max_occlusion_pct", 0, 100)
  ) {
    return null;
  }

  const hasCategoryCapacity = isPlainObject(raw.category_capacity_cm)
    && Object.keys(raw.category_capacity_cm).length > 0;
  const totalShelfWidth = Number(raw.total_shelf_width_cm);
  if (!hasCategoryCapacity && !(Number.isFinite(totalShelfWidth) && totalShelfWidth > 0)) {
    return null;
  }
  return structuredClone(raw);
}

function embeddedStoreMatches(container, expected) {
  const embedded = String(container?.store_code ?? "").trim().toUpperCase();
  if (!embedded || embedded === "AUTO") return true;
  return embedded === expected;
}

export function normalizeCandidateBundle(payload) {
  if (!isPlainObject(payload)) return null;
  if (
    !Array.isArray(payload.products)
    || payload.products.length === 0
    || payload.products.length > MAX_PRODUCTS
  ) {
    return null;
  }
  if (!isPlainObject(payload.layout) || !isPlainObject(payload.store_dna)) return null;
  if (containsForbiddenIdentity(payload.products)) return null;

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

  const retailIntelligence = normalizeRetailIntelligence(payload.retail_intelligence);
  if (payload.retail_intelligence != null && !retailIntelligence) return null;
  if (retailIntelligence) {
    const expectedStore = String(retailIntelligence.store_code).trim().toUpperCase();
    if (
      !embeddedStoreMatches(payload.layout, expectedStore)
      || !embeddedStoreMatches(payload.store_dna, expectedStore)
    ) {
      return null;
    }
    for (const pair of retailIntelligence.historical_pairs ?? []) {
      if (String(pair?.store_code ?? "").trim().toUpperCase() !== expectedStore) return null;
    }
    for (const candidate of [
      retailIntelligence.blind_candidate_a,
      retailIntelligence.blind_candidate_b,
    ]) {
      if (candidate && !embeddedStoreMatches(candidate.planogram, expectedStore)) return null;
    }
    if (
      (retailIntelligence.blind_candidate_a || retailIntelligence.blind_candidate_b)
      && orderBaskets.length === 0
    ) {
      return null;
    }
  }

  const normalized = {
    products: payload.products,
    layout: payload.layout,
    store_dna: payload.store_dna,
    mode,
    order_baskets: orderBaskets,
    ...(assetManifest ? { asset_manifest: assetManifest } : {}),
  };
  if (retailIntelligence) {
    Object.defineProperty(normalized, "retail_intelligence", {
      value: retailIntelligence,
      enumerable: false,
      configurable: false,
      writable: false,
    });
  }
  return normalized;
}

export const PLANOGRAM_CANDIDATE_LIMITS = Object.freeze({
  maxProducts: MAX_PRODUCTS,
  maxBaskets: MAX_BASKETS,
  maxSkusPerBasket: MAX_SKUS_PER_BASKET,
  maxSkuLength: MAX_SKU_LENGTH,
  maxRetailPairs: MAX_RETAIL_PAIRS,
  maxRealogramEvents: MAX_REALOGRAM_EVENTS,
  maxSubstitutionEdges: MAX_SUBSTITUTION_EDGES,
  maxShelfScanShelves: MAX_SHELF_SCAN_SHELVES,
  maxShelfScanObservations: MAX_SHELF_SCAN_OBSERVATIONS,
  maxBlindAisles: MAX_BLIND_AISLES,
});
