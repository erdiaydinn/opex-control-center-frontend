const MAX_PRODUCT_ASSETS = 2500;
const MAX_FIXTURE_ASSETS = 250;
const MAX_PATH_LENGTH = 500;
const PRODUCT_EXTENSIONS = /\.(png|jpe?g|webp|avif)(\?.*)?$/i;
const PRODUCT_KTX2_EXTENSIONS = /\.ktx2(\?.*)?$/i;
const FIXTURE_EXTENSIONS = /\.(glb)(\?.*)?$/i;
const PRODUCT_ASSET_PREFIX = "/planogram-assets/products/";
const FIXTURE_ASSET_PREFIX = "/planogram-assets/fixtures/";
const ATLAS_ASSET_PREFIX = "/planogram-assets/atlases/";

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

function normalizeAtlasUv(raw) {
  if (!Array.isArray(raw) || raw.length !== 4) return null;
  const values = raw.map(Number);
  if (values.some((value) => !Number.isFinite(value) || value < 0 || value > 1)) return null;
  const [u0, v0, u1, v1] = values;
  if (u1 <= u0 || v1 <= v0) return null;
  return values;
}

function normalizeLodModelPaths(raw) {
  if (raw == null) return null;
  if (!isPlainObject(raw)) return null;
  const allowed = new Set(["medium", "far"]);
  if (!Object.keys(raw).every((key) => allowed.has(key))) return null;
  const result = {};
  for (const key of ["medium", "far"]) {
    if (raw[key] == null) continue;
    const path = safeSameOriginPath(raw[key], FIXTURE_EXTENSIONS, FIXTURE_ASSET_PREFIX);
    if (!path) return null;
    result[key] = path;
  }
  return Object.keys(result).length ? result : null;
}

function normalizeProductAsset(raw, version) {
  if (!isPlainObject(raw)) return null;
  const allowed = version === 2
    ? new Set(["sku", "front_image_path", "ktx2_path", "atlas_path", "atlas_uv", "source_ref", "attested"])
    : new Set(["sku", "front_image_path", "source_ref", "attested"]);
  if (!Object.keys(raw).every((key) => allowed.has(key))) return null;
  const sku = String(raw.sku ?? "").trim().toUpperCase();
  const frontImagePath = safeSameOriginPath(raw.front_image_path, PRODUCT_EXTENSIONS, PRODUCT_ASSET_PREFIX);
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (!sku || sku.length > 160 || !frontImagePath || sourceRef.length < 3 || sourceRef.length > 500) return null;
  if (raw.attested !== true && raw.attested !== false) return null;

  const result = { sku, front_image_path: frontImagePath, source_ref: sourceRef, attested: raw.attested };
  if (version === 2) {
    if (raw.ktx2_path != null) {
      const ktx2Path = safeSameOriginPath(raw.ktx2_path, PRODUCT_KTX2_EXTENSIONS, PRODUCT_ASSET_PREFIX);
      if (!ktx2Path) return null;
      result.ktx2_path = ktx2Path;
    }
    const hasAtlasPath = raw.atlas_path != null;
    const hasAtlasUv = raw.atlas_uv != null;
    if (hasAtlasPath !== hasAtlasUv) return null;
    if (hasAtlasPath) {
      const atlasPath = safeSameOriginPath(raw.atlas_path, PRODUCT_EXTENSIONS, ATLAS_ASSET_PREFIX);
      const atlasUv = normalizeAtlasUv(raw.atlas_uv);
      if (!atlasPath || !atlasUv) return null;
      result.atlas_path = atlasPath;
      result.atlas_uv = atlasUv;
    }
  }
  return result;
}

function normalizeFixtureAsset(raw, version) {
  if (!isPlainObject(raw)) return null;
  const allowed = version === 2
    ? new Set(["fixture_type", "model_path", "lod_model_paths", "source_ref", "attested"])
    : new Set(["fixture_type", "model_path", "source_ref", "attested"]);
  if (!Object.keys(raw).every((key) => allowed.has(key))) return null;
  const fixtureType = String(raw.fixture_type ?? "").trim().toUpperCase();
  const modelPath = safeSameOriginPath(raw.model_path, FIXTURE_EXTENSIONS, FIXTURE_ASSET_PREFIX);
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (!fixtureType || fixtureType.length > 120 || !modelPath || sourceRef.length < 3 || sourceRef.length > 500) return null;
  if (raw.attested !== true && raw.attested !== false) return null;

  const result = { fixture_type: fixtureType, model_path: modelPath, source_ref: sourceRef, attested: raw.attested };
  if (version === 2 && raw.lod_model_paths != null) {
    const lodModelPaths = normalizeLodModelPaths(raw.lod_model_paths);
    if (!lodModelPaths) return null;
    result.lod_model_paths = lodModelPaths;
  }
  return result;
}

export function normalizePlanogramAssetManifest(raw) {
  if (raw == null) return null;
  if (!isPlainObject(raw)) return null;
  const allowed = new Set(["version", "source_ref", "product_assets", "fixture_assets"]);
  if (!Object.keys(raw).every((key) => allowed.has(key))) return null;
  const version = Number(raw.version);
  if (version !== 1 && version !== 2) return null;
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (sourceRef.length < 3 || sourceRef.length > 500) return null;
  if (!Array.isArray(raw.product_assets) || raw.product_assets.length > MAX_PRODUCT_ASSETS) return null;
  if (!Array.isArray(raw.fixture_assets) || raw.fixture_assets.length > MAX_FIXTURE_ASSETS) return null;

  const productAssets = raw.product_assets.map((row) => normalizeProductAsset(row, version));
  const fixtureAssets = raw.fixture_assets.map((row) => normalizeFixtureAsset(row, version));
  if (productAssets.some((row) => !row) || fixtureAssets.some((row) => !row)) return null;

  const productKeys = productAssets.map((row) => row.sku);
  const fixtureKeys = fixtureAssets.map((row) => row.fixture_type);
  if (new Set(productKeys).size !== productKeys.length) return null;
  if (new Set(fixtureKeys).size !== fixtureKeys.length) return null;

  return {
    version,
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
  atlasAssetPrefix: ATLAS_ASSET_PREFIX,
});
