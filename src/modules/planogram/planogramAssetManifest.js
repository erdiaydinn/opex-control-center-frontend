const MAX_PRODUCT_ASSETS = 2500;
const MAX_FIXTURE_ASSETS = 250;
const MAX_PATH_LENGTH = 500;
const PRODUCT_EXTENSIONS = /\.(png|jpe?g|webp|avif)(\?.*)?$/i;
const FIXTURE_EXTENSIONS = /\.(glb)(\?.*)?$/i;
const PRODUCT_ASSET_PREFIX = "/planogram-assets/products/";
const FIXTURE_ASSET_PREFIX = "/planogram-assets/fixtures/";

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function safeSameOriginPath(value, extensionPattern, allowedPrefix) {
  const path = String(value ?? "").trim();
  if (!path || path.length > MAX_PATH_LENGTH) return null;
  if (!path.startsWith("/") || path.startsWith("//")) return null;
  if (path.includes("\\") || /[\u0000-\u001f]/.test(path)) return null;
  if (path.includes("#") || /%(?:2e|2f|5c|00)/i.test(path)) return null;
  const pathname = path.split("?", 1)[0];
  if (!pathname.startsWith(allowedPrefix)) return null;
  if (pathname.split("/").some((segment) => segment === "." || segment === "..")) return null;
  return extensionPattern.test(path) ? path : null;
}

function normalizeProductAsset(raw) {
  if (!isPlainObject(raw)) return null;
  const allowed = new Set(["sku", "front_image_path", "source_ref", "attested"]);
  if (!Object.keys(raw).every((key) => allowed.has(key))) return null;
  const sku = String(raw.sku ?? "").trim().toUpperCase();
  const frontImagePath = safeSameOriginPath(raw.front_image_path, PRODUCT_EXTENSIONS, PRODUCT_ASSET_PREFIX);
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (!sku || sku.length > 160 || !frontImagePath || sourceRef.length < 3 || sourceRef.length > 500) return null;
  if (raw.attested !== true && raw.attested !== false) return null;
  return { sku, front_image_path: frontImagePath, source_ref: sourceRef, attested: raw.attested };
}

function normalizeFixtureAsset(raw) {
  if (!isPlainObject(raw)) return null;
  const allowed = new Set(["fixture_type", "model_path", "source_ref", "attested"]);
  if (!Object.keys(raw).every((key) => allowed.has(key))) return null;
  const fixtureType = String(raw.fixture_type ?? "").trim().toUpperCase();
  const modelPath = safeSameOriginPath(raw.model_path, FIXTURE_EXTENSIONS, FIXTURE_ASSET_PREFIX);
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (!fixtureType || fixtureType.length > 120 || !modelPath || sourceRef.length < 3 || sourceRef.length > 500) return null;
  if (raw.attested !== true && raw.attested !== false) return null;
  return { fixture_type: fixtureType, model_path: modelPath, source_ref: sourceRef, attested: raw.attested };
}

export function normalizePlanogramAssetManifest(raw) {
  if (raw == null) return null;
  if (!isPlainObject(raw)) return null;
  const allowed = new Set(["version", "source_ref", "product_assets", "fixture_assets"]);
  if (!Object.keys(raw).every((key) => allowed.has(key))) return null;
  if (Number(raw.version) !== 1) return null;
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (sourceRef.length < 3 || sourceRef.length > 500) return null;
  if (!Array.isArray(raw.product_assets) || raw.product_assets.length > MAX_PRODUCT_ASSETS) return null;
  if (!Array.isArray(raw.fixture_assets) || raw.fixture_assets.length > MAX_FIXTURE_ASSETS) return null;

  const productAssets = raw.product_assets.map(normalizeProductAsset);
  const fixtureAssets = raw.fixture_assets.map(normalizeFixtureAsset);
  if (productAssets.some((row) => !row) || fixtureAssets.some((row) => !row)) return null;

  const productKeys = productAssets.map((row) => row.sku);
  const fixtureKeys = fixtureAssets.map((row) => row.fixture_type);
  if (new Set(productKeys).size !== productKeys.length) return null;
  if (new Set(fixtureKeys).size !== fixtureKeys.length) return null;

  return {
    version: 1,
    source_ref: sourceRef,
    product_assets: productAssets,
    fixture_assets: fixtureAssets,
    authority: "request_supplied_preview_assets",
  };
}

export function buildProductAssetIndex(manifest) {
  return new Map((manifest?.product_assets || []).map((row) => [row.sku, row]));
}

export function buildFixtureAssetIndex(manifest) {
  return new Map((manifest?.fixture_assets || []).map((row) => [row.fixture_type, row]));
}

export const PLANOGRAM_ASSET_LIMITS = Object.freeze({
  maxProductAssets: MAX_PRODUCT_ASSETS,
  maxFixtureAssets: MAX_FIXTURE_ASSETS,
  productAssetPrefix: PRODUCT_ASSET_PREFIX,
  fixtureAssetPrefix: FIXTURE_ASSET_PREFIX,
});
