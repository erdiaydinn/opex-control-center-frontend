const PROVIDERS = new Set(["apple_roomplan", "arcore_depth", "cad_import", "manual_survey"]);
const ELEMENT_TYPES = new Set([
  "wall",
  "column",
  "door",
  "opening",
  "chiller",
  "freezer",
  "fixture",
  "unknown",
]);
const TOP_LEVEL_FIELDS = new Set([
  "store_code",
  "provider",
  "source_ref",
  "floor_width_m",
  "floor_depth_m",
  "elements",
]);
const ELEMENT_FIELDS = new Set([
  "element_id",
  "element_type",
  "x_m",
  "y_m",
  "width_m",
  "depth_m",
  "rotation_deg",
  "confidence",
  "label",
]);
const MAX_ELEMENTS = 5000;

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function onlyKnownKeys(raw, allowed) {
  return Object.keys(raw).every((key) => allowed.has(key));
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeElement(raw) {
  if (!isPlainObject(raw) || !onlyKnownKeys(raw, ELEMENT_FIELDS)) return null;
  const elementId = String(raw.element_id ?? "").trim();
  const elementType = String(raw.element_type ?? "").trim().toLowerCase();
  const xM = finiteNumber(raw.x_m);
  const yM = finiteNumber(raw.y_m);
  const widthM = finiteNumber(raw.width_m);
  const depthM = finiteNumber(raw.depth_m);
  const rotationDeg = finiteNumber(raw.rotation_deg ?? 0);
  const confidence = finiteNumber(raw.confidence);
  const label = raw.label == null ? null : String(raw.label).trim();

  if (!elementId || elementId.length > 120 || !ELEMENT_TYPES.has(elementType)) return null;
  if (xM == null || yM == null || xM < 0 || yM < 0 || xM > 500 || yM > 500) return null;
  if (widthM == null || depthM == null || widthM <= 0 || depthM <= 0 || widthM > 500 || depthM > 500) return null;
  if (rotationDeg == null || rotationDeg < -360 || rotationDeg > 360) return null;
  if (confidence == null || confidence < 0 || confidence > 1) return null;
  if (label != null && label.length > 160) return null;

  return {
    element_id: elementId,
    element_type: elementType,
    x_m: xM,
    y_m: yM,
    width_m: widthM,
    depth_m: depthM,
    rotation_deg: rotationDeg,
    confidence,
    ...(label ? { label } : {}),
  };
}

export function normalizePlanogramStoreScanBundle(payload) {
  if (!isPlainObject(payload) || !onlyKnownKeys(payload, TOP_LEVEL_FIELDS)) return null;
  const storeCode = String(payload.store_code ?? "").trim();
  const provider = String(payload.provider ?? "").trim().toLowerCase();
  const sourceRef = String(payload.source_ref ?? "").trim();
  const floorWidthM = finiteNumber(payload.floor_width_m);
  const floorDepthM = finiteNumber(payload.floor_depth_m);
  if (!/^[A-Za-z0-9._-]{1,80}$/.test(storeCode)) return null;
  if (!PROVIDERS.has(provider)) return null;
  if (sourceRef.length < 3 || sourceRef.length > 500) return null;
  if (floorWidthM == null || floorDepthM == null || floorWidthM <= 0 || floorDepthM <= 0) return null;
  if (floorWidthM > 500 || floorDepthM > 500) return null;
  if (!Array.isArray(payload.elements) || payload.elements.length < 1 || payload.elements.length > MAX_ELEMENTS) return null;

  const elements = payload.elements.map(normalizeElement);
  if (elements.some((element) => !element)) return null;
  const ids = elements.map((element) => element.element_id);
  if (new Set(ids).size !== ids.length) return null;

  return {
    store_code: storeCode,
    provider,
    source_ref: sourceRef,
    floor_width_m: floorWidthM,
    floor_depth_m: floorDepthM,
    elements,
  };
}

export function safePlanogramStoreScanPreview(response) {
  const scan = response?.store_scan;
  if (!isPlainObject(response) || !isPlainObject(scan)) return null;
  const fingerprint = String(scan.scan_fingerprint ?? "").trim().toLowerCase();
  const requiredFalse = [
    response.production_release_allowed,
    scan.raw_media_persisted,
    scan.production_evidence,
    scan.promotable_to_store_dna,
  ];
  if (
    response.preview_only !== true ||
    response.input_authority !== "request_supplied_measured_scan_unattested" ||
    requiredFalse.some((value) => value !== false) ||
    !/^[0-9a-f]{64}$/.test(fingerprint)
  ) {
    return null;
  }
  return response;
}

export const PLANOGRAM_STORE_SCAN_LIMITS = Object.freeze({ maxElements: MAX_ELEMENTS });
