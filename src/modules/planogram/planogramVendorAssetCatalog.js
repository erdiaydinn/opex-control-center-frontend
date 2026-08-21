import { normalizePlanogramAssetManifest } from "./planogramAssetManifest.js";

const SHA256 = /^[0-9a-f]{64}$/i;
const MAX_VENDOR_ENTRIES = 500;

function text(value) {
  return String(value ?? "").trim();
}

function key(value) {
  return text(value).toUpperCase();
}

function approvedCatalogRecord(version) {
  if (!version || version.status !== "approved") return null;
  const record = version.record;
  if (!record || typeof record !== "object" || Array.isArray(record)) return null;
  const fixtureCode = key(record.fixture_code);
  const fixtureType = key(record.fixture_type);
  const recordSha256 = text(version.record_sha256).toLowerCase();
  if (!fixtureCode || !fixtureType || !SHA256.test(recordSha256)) return null;
  return Object.freeze({
    fixtureCode,
    fixtureType,
    fixtureName: text(record.fixture_name),
    catalogVersionId: text(version.id),
    versionNumber: Number(version.version_number || 0),
    recordSha256,
    physicalSourceRef: text(record.source_ref),
  });
}

function normalizeVisualMapping(mapping, approved) {
  if (!mapping || mapping.attested !== true) return null;
  const fixtureCode = key(mapping.fixture_code);
  if (!fixtureCode || fixtureCode !== approved.fixtureCode) return null;
  const vendorId = key(mapping.vendor_id);
  const variantKey = key(mapping.variant_key || "DEFAULT");
  if (!vendorId || !variantKey) return null;

  const manifest = normalizePlanogramAssetManifest({
    version: 2,
    source_ref: text(mapping.source_ref),
    product_assets: [],
    fixture_assets: [{
      fixture_type: approved.fixtureType,
      model_path: mapping.model_path,
      ...(mapping.lod_model_paths ? { lod_model_paths: mapping.lod_model_paths } : {}),
      source_ref: text(mapping.source_ref),
      attested: true,
    }],
  });
  const fixtureAsset = manifest?.fixture_assets?.[0];
  if (!fixtureAsset) return null;

  return Object.freeze({
    fixtureCode: approved.fixtureCode,
    fixtureType: approved.fixtureType,
    fixtureName: approved.fixtureName,
    vendorId,
    variantKey,
    catalogVersionId: approved.catalogVersionId,
    catalogVersionNumber: approved.versionNumber,
    catalogRecordSha256: approved.recordSha256,
    physicalSourceRef: approved.physicalSourceRef,
    visualSourceRef: fixtureAsset.source_ref,
    modelPath: fixtureAsset.model_path,
    lodModelPaths: fixtureAsset.lod_model_paths || null,
    physicalAuthority: "server_approved_fixture_catalog",
    visualAuthority: "attested_same_origin_vendor_glb",
  });
}

export function buildPlanogramVendorAssetCatalog(approvedVersions, visualMappings) {
  const approvedRows = Array.isArray(approvedVersions) ? approvedVersions : [];
  const mappings = Array.isArray(visualMappings) ? visualMappings : [];
  const approvedByCode = new Map();
  let rejectedCatalogVersions = 0;
  let supersededCatalogVersions = 0;

  for (const version of approvedRows) {
    const approved = approvedCatalogRecord(version);
    if (!approved) {
      rejectedCatalogVersions += 1;
      continue;
    }
    const current = approvedByCode.get(approved.fixtureCode);
    if (!current || approved.versionNumber > current.versionNumber) {
      if (current) supersededCatalogVersions += 1;
      approvedByCode.set(approved.fixtureCode, approved);
    } else {
      supersededCatalogVersions += 1;
    }
  }

  const entries = [];
  const identity = new Set();
  let rejectedVisualMappings = 0;
  let duplicateVisualMappings = 0;
  let skippedBudget = 0;

  for (const mapping of mappings) {
    const fixtureCode = key(mapping?.fixture_code);
    const approved = approvedByCode.get(fixtureCode);
    if (!approved) {
      rejectedVisualMappings += 1;
      continue;
    }
    const normalized = normalizeVisualMapping(mapping, approved);
    if (!normalized) {
      rejectedVisualMappings += 1;
      continue;
    }
    const identityKey = `${normalized.fixtureCode}:${normalized.vendorId}:${normalized.variantKey}`;
    if (identity.has(identityKey)) {
      duplicateVisualMappings += 1;
      continue;
    }
    if (entries.length >= MAX_VENDOR_ENTRIES) {
      skippedBudget += 1;
      continue;
    }
    identity.add(identityKey);
    entries.push(normalized);
  }

  return Object.freeze({
    contract: "eay.planogram.vendor-asset-catalog.v1",
    productionReleaseAllowed: false,
    physicalAuthority: "server_approved_fixture_catalog_only",
    visualAuthority: "attested_same_origin_vendor_glb_only",
    entries: Object.freeze(entries),
    diagnostics: Object.freeze({
      approvedFixtureCodes: approvedByCode.size,
      rejectedCatalogVersions,
      supersededCatalogVersions,
      rejectedVisualMappings,
      duplicateVisualMappings,
      skippedBudget,
    }),
  });
}

export function selectVendorFixtureAsset(catalog, module, preferredVendorId = null) {
  if (!catalog || catalog.contract !== "eay.planogram.vendor-asset-catalog.v1") return null;
  const fixtureCode = key(module?.fixtureCode ?? module?.fixture_code ?? module?.catalogFixtureCode);
  if (!fixtureCode) return null;
  const vendorId = preferredVendorId ? key(preferredVendorId) : null;
  const candidates = (catalog.entries || []).filter((row) => row.fixtureCode === fixtureCode);
  if (!candidates.length) return null;
  if (vendorId) return candidates.find((row) => row.vendorId === vendorId) || null;
  return candidates.find((row) => row.variantKey === "DEFAULT") || candidates[0] || null;
}

export const PLANOGRAM_VENDOR_ASSET_LIMITS = Object.freeze({
  maxVendorEntries: MAX_VENDOR_ENTRIES,
});
