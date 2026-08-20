const STORAGE_TYPES = new Set(["AMBIENT", "CHILLED", "FROZEN", "PALLET"]);
const SIDES = new Set(["L", "R"]);
const ZONES = new Set(["bottom", "lower", "eye", "upper", "top"]);
const BINDING_FIELDS = new Set([
  "scan_fixture_element_id",
  "fixture_id",
  "aisle_id",
  "side",
  "position",
  "fixture_type",
  "storage_type",
  "shelf_count",
  "fixture_width_cm",
  "fixture_height_cm",
  "fixture_depth_cm",
  "shelf_width_cm",
  "shelf_height_cm",
  "shelf_depth_cm",
  "shelf_max_weight_kg",
  "shelf_zone_types",
  "source_ref",
  "attested",
]);
const CATALOG_FIELDS = new Set([
  "fixture_id",
  "fixture_type",
  "storage_type",
  "shelf_count",
  "fixture_width_cm",
  "fixture_height_cm",
  "fixture_depth_cm",
  "shelf_width_cm",
  "shelf_height_cm",
  "shelf_depth_cm",
  "shelf_max_weight_kg",
  "shelf_zone_types",
  "source_ref",
  "attested",
]);
const MAX_BINDINGS = 1000;
const MAX_CATALOG_FIXTURES = 2000;
const MAX_DIMENSION_DELTA_RATIO = 0.15;
const MIN_DIMENSION_DELTA_CM = 12;
const AUTO_SUGGESTION_MARGIN = 0.12;

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function exactKeys(raw, allowed) {
  return Object.keys(raw).length === allowed.size && Object.keys(raw).every((key) => allowed.has(key));
}

function normalizeFixtureTruth(raw, allowedKeys) {
  if (!isPlainObject(raw) || !exactKeys(raw, allowedKeys)) return null;
  const fixtureId = String(raw.fixture_id ?? "").trim();
  const fixtureType = String(raw.fixture_type ?? "").trim();
  const storageType = String(raw.storage_type ?? "").trim().toUpperCase();
  const shelfCount = finiteNumber(raw.shelf_count);
  const fixtureWidth = finiteNumber(raw.fixture_width_cm);
  const fixtureHeight = finiteNumber(raw.fixture_height_cm);
  const fixtureDepth = finiteNumber(raw.fixture_depth_cm);
  const shelfWidth = finiteNumber(raw.shelf_width_cm);
  const shelfHeight = finiteNumber(raw.shelf_height_cm);
  const shelfDepth = finiteNumber(raw.shelf_depth_cm);
  const maxWeight = finiteNumber(raw.shelf_max_weight_kg);
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{2,120}$/.test(fixtureId)) return null;
  if (!fixtureType || fixtureType.length > 120 || !STORAGE_TYPES.has(storageType)) return null;
  if (!Number.isInteger(shelfCount) || shelfCount < 1 || shelfCount > 30) return null;
  if ([fixtureWidth, fixtureHeight, fixtureDepth, shelfWidth, shelfHeight, shelfDepth, maxWeight].some((value) => value == null || value <= 0)) return null;
  if (fixtureWidth > 2000 || fixtureHeight > 2000 || fixtureDepth > 2000) return null;
  if (shelfWidth > fixtureWidth * 1.05 || shelfDepth > fixtureDepth * 1.05) return null;
  if (shelfHeight * shelfCount > fixtureHeight * 1.25) return null;
  if (!Array.isArray(raw.shelf_zone_types) || raw.shelf_zone_types.length !== shelfCount) return null;
  if (!raw.shelf_zone_types.every((zone) => ZONES.has(String(zone)))) return null;
  if (sourceRef.length < 3 || sourceRef.length > 500 || raw.attested !== true) return null;
  return {
    fixture_id: fixtureId,
    fixture_type: fixtureType,
    storage_type: storageType,
    shelf_count: shelfCount,
    fixture_width_cm: fixtureWidth,
    fixture_height_cm: fixtureHeight,
    fixture_depth_cm: fixtureDepth,
    shelf_width_cm: shelfWidth,
    shelf_height_cm: shelfHeight,
    shelf_depth_cm: shelfDepth,
    shelf_max_weight_kg: maxWeight,
    shelf_zone_types: raw.shelf_zone_types.map(String),
    source_ref: sourceRef,
    attested: true,
  };
}

function normalizeBinding(raw) {
  const truth = normalizeFixtureTruth(raw, BINDING_FIELDS);
  if (!truth) return null;
  const scanFixtureElementId = String(raw.scan_fixture_element_id ?? "").trim();
  const aisleId = String(raw.aisle_id ?? "").trim();
  const side = String(raw.side ?? "").trim().toUpperCase();
  const position = finiteNumber(raw.position);
  if (!scanFixtureElementId || scanFixtureElementId.length > 120) return null;
  if (!/^[A-Za-z0-9._:-]{1,40}$/.test(aisleId)) return null;
  if (!SIDES.has(side)) return null;
  if (!Number.isInteger(position) || position < 1 || position > 500) return null;
  return {
    scan_fixture_element_id: scanFixtureElementId,
    ...truth,
    aisle_id: aisleId,
    side,
    position,
  };
}

export function normalizePlanogramFixtureBindings(payload, recognizedIds = []) {
  if (!isPlainObject(payload) || Object.keys(payload).length !== 1 || !Array.isArray(payload.bindings)) return null;
  if (payload.bindings.length > MAX_BINDINGS) return null;
  const rows = payload.bindings.map(normalizeBinding);
  if (rows.some((row) => !row)) return null;
  const targetIds = rows.map((row) => row.scan_fixture_element_id);
  const fixtureIds = rows.map((row) => row.fixture_id);
  const slots = rows.map((row) => `${row.aisle_id}::${row.side}::${row.position}`);
  if (new Set(targetIds).size !== targetIds.length) return null;
  if (new Set(fixtureIds).size !== fixtureIds.length) return null;
  if (new Set(slots).size !== slots.length) return null;
  const allowedTargets = new Set(recognizedIds.map(String));
  if (rows.some((row) => !allowedTargets.has(row.scan_fixture_element_id))) return null;
  return rows;
}

export function normalizePlanogramFixtureCatalog(payload) {
  if (!isPlainObject(payload) || Object.keys(payload).length !== 1 || !Array.isArray(payload.fixtures)) return null;
  if (!payload.fixtures.length || payload.fixtures.length > MAX_CATALOG_FIXTURES) return null;
  const rows = payload.fixtures.map((row) => normalizeFixtureTruth(row, CATALOG_FIELDS));
  if (rows.some((row) => !row)) return null;
  const ids = rows.map((row) => row.fixture_id);
  if (new Set(ids).size !== ids.length) return null;
  return rows;
}

function dimensionMatches(scanM, catalogCm) {
  const scanCm = finiteNumber(scanM) == null ? null : Number(scanM) * 100;
  if (scanCm == null || scanCm <= 0 || catalogCm <= 0) return false;
  const tolerance = Math.max(MIN_DIMENSION_DELTA_CM, catalogCm * MAX_DIMENSION_DELTA_RATIO);
  return Math.abs(scanCm - catalogCm) <= tolerance;
}

function labelAffinity(scan, catalog) {
  const label = String(scan?.label || "").toLowerCase();
  if (!label) return 0;
  const tokens = String(catalog.fixture_type || "").toLowerCase().split(/[^a-z0-9+_-]+/).filter((token) => token.length >= 3);
  return tokens.some((token) => label.includes(token)) ? 0.08 : 0;
}

function hintedStorage(scan) {
  const value = String(scan?.hinted_storage_type || "").trim().toUpperCase();
  return STORAGE_TYPES.has(value) ? value : null;
}

function matchScore(scan, catalog) {
  const widthCm = Number(scan?.width_m || 0) * 100;
  const depthCm = Number(scan?.depth_m || 0) * 100;
  const widthDelta = Math.abs(widthCm - catalog.fixture_width_cm) / Math.max(catalog.fixture_width_cm, 1);
  const depthDelta = Math.abs(depthCm - catalog.fixture_depth_cm) / Math.max(catalog.fixture_depth_cm, 1);
  const storageHint = hintedStorage(scan);
  const storageCompatible = !storageHint || catalog.storage_type === storageHint;
  const eligible = storageCompatible
    && dimensionMatches(scan?.width_m, catalog.fixture_width_cm)
    && dimensionMatches(scan?.depth_m, catalog.fixture_depth_cm);
  return {
    eligible,
    score: Number(Math.max(0, widthDelta + depthDelta - labelAffinity(scan, catalog)).toFixed(6)),
    width_delta_cm: Number(Math.abs(widthCm - catalog.fixture_width_cm).toFixed(2)),
    depth_delta_cm: Number(Math.abs(depthCm - catalog.fixture_depth_cm).toFixed(2)),
    storage_hint: storageHint,
    storage_compatible: storageCompatible,
  };
}

export function suggestPlanogramFixtureCatalogMatches(recognizedFixtures, catalog) {
  if (!Array.isArray(recognizedFixtures) || !Array.isArray(catalog)) return [];
  return recognizedFixtures.map((scan) => {
    const candidates = catalog
      .map((fixture) => ({ fixture, ...matchScore(scan, fixture) }))
      .filter((row) => row.eligible)
      .sort((left, right) => left.score - right.score || left.fixture.fixture_id.localeCompare(right.fixture.fixture_id))
      .slice(0, 5);
    const first = candidates[0] || null;
    const second = candidates[1] || null;
    const margin = first && second ? second.score - first.score : Number.POSITIVE_INFINITY;
    return {
      scan_fixture_element_id: String(scan?.element_id || ""),
      hinted_storage_type: hintedStorage(scan),
      candidates,
      recommended_fixture_id: first?.fixture.fixture_id || null,
      recommendation_safe: Boolean(first && margin >= AUTO_SUGGESTION_MARGIN),
      ambiguous: Boolean(first && second && margin < AUTO_SUGGESTION_MARGIN),
    };
  });
}

export function buildPlanogramFixtureBindingsFromSelections(recognizedFixtures, catalog, selections) {
  if (!Array.isArray(recognizedFixtures) || !Array.isArray(catalog) || !isPlainObject(selections)) return null;
  const catalogById = new Map(catalog.map((row) => [row.fixture_id, row]));
  const rows = [];
  for (const scan of recognizedFixtures) {
    const scanId = String(scan?.element_id || "");
    const selection = selections[scanId];
    if (!isPlainObject(selection)) return null;
    const fixture = catalogById.get(String(selection.fixture_id || ""));
    if (!fixture) return null;
    const storageHint = hintedStorage(scan);
    if (storageHint && fixture.storage_type !== storageHint) return null;
    rows.push({
      scan_fixture_element_id: scanId,
      ...fixture,
      aisle_id: String(selection.aisle_id || "").trim(),
      side: String(selection.side || "").trim().toUpperCase(),
      position: Number(selection.position),
    });
  }
  return normalizePlanogramFixtureBindings(
    { bindings: rows },
    recognizedFixtures.map((row) => String(row?.element_id || ""))
  );
}

export function safePlanogramFixtureLayoutPreview(response, expectedScanFingerprint) {
  const result = response?.result;
  if (!isPlainObject(response) || !isPlainObject(result)) return null;
  const expected = String(expectedScanFingerprint ?? "").trim().toLowerCase();
  const actual = String(result.scan_fingerprint ?? "").trim().toLowerCase();
  const requiredFalse = [
    response.store_dna_approval_allowed,
    response.physical_layout_release_allowed,
    response.production_release_allowed,
    response.installation_approval_allowed,
    response.capex_approval_allowed,
    result.physical_layout_authority,
    result.store_dna_authority,
    result.v4_v5_production_eligible,
    result.relocation_execution_allowed,
    result.installation_approval_allowed,
    result.capex_approval_allowed,
  ];
  if (
    response.preview_only !== true ||
    response.input_authority !== "fingerprint_bound_human_fixture_binding_unattested" ||
    !expected || actual !== expected ||
    requiredFalse.some((value) => value !== false)
  ) return null;
  return response;
}

export const PLANOGRAM_FIXTURE_BINDING_LIMITS = Object.freeze({
  maxBindings: MAX_BINDINGS,
  maxCatalogFixtures: MAX_CATALOG_FIXTURES,
  maxDimensionDeltaRatio: MAX_DIMENSION_DELTA_RATIO,
  minDimensionDeltaCm: MIN_DIMENSION_DELTA_CM,
  autoSuggestionMargin: AUTO_SUGGESTION_MARGIN,
});