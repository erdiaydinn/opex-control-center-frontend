export const PLANOGRAM_AUTHORING_CONTRACT = "planogram-architectural-authoring-v1";
export const PLANOGRAM_AUTHORING_GRID_M = 0.05;
export const PLANOGRAM_AUTHORING_ELEMENT_TYPES = Object.freeze([
  "wall",
  "door",
  "window",
  "column",
  "no_go",
  "technical",
  "inbound",
  "dispatch",
  "picker_entry",
  "picker_exit",
  "emergency_exit",
]);

const MIN_DIMENSION_M = 0.05;
const DEFAULT_DIMENSIONS = Object.freeze({
  wall: [1, 0.12],
  door: [0.9, 0.12],
  window: [1.2, 0.12],
  column: [0.35, 0.35],
  no_go: [1, 1],
  technical: [1, 1],
  inbound: [1.5, 1.5],
  dispatch: [1.5, 1.5],
  picker_entry: [0.4, 0.4],
  picker_exit: [0.4, 0.4],
  emergency_exit: [1, 0.25],
});

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function rounded(value, precision = 3) {
  const factor = 10 ** precision;
  return Math.round(finite(value) * factor) / factor;
}

function normalizedRotation(value) {
  let rotation = finite(value, 0) % 360;
  if (rotation > 180) rotation -= 360;
  if (rotation <= -180) rotation += 360;
  return rounded(rotation, 2);
}

export function snapPlanogramAuthoringValue(value, stepM = PLANOGRAM_AUTHORING_GRID_M) {
  const step = Math.max(0.001, finite(stepM, PLANOGRAM_AUTHORING_GRID_M));
  return rounded(Math.round(finite(value) / step) * step);
}

function centerForElement(element) {
  const width = Math.max(MIN_DIMENSION_M, finite(element?.width_m, MIN_DIMENSION_M));
  const depth = Math.max(MIN_DIMENSION_M, finite(element?.depth_m, MIN_DIMENSION_M));
  const hasCenter = Number.isFinite(Number(element?.center_x_m)) && Number.isFinite(Number(element?.center_y_m));
  if (hasCenter) {
    return [finite(element.center_x_m), finite(element.center_y_m)];
  }
  return [finite(element?.x_m) + width / 2, finite(element?.y_m) + depth / 2];
}

function clampCenter(value, dimension, floorDimension) {
  const half = dimension / 2;
  return Math.min(Math.max(value, half), Math.max(half, floorDimension - half));
}

export function normalizePlanogramAuthoringElement(raw, floor, index = 0) {
  if (!raw || typeof raw !== "object") return null;
  const type = String(raw.element_type || raw.type || "").trim().toLowerCase();
  if (!PLANOGRAM_AUTHORING_ELEMENT_TYPES.includes(type)) return null;
  const defaults = DEFAULT_DIMENSIONS[type] || [1, 1];
  const widthM = Math.max(MIN_DIMENSION_M, finite(raw.width_m, defaults[0]));
  const depthM = Math.max(MIN_DIMENSION_M, finite(raw.depth_m, defaults[1]));
  const [rawX, rawY] = centerForElement({ ...raw, width_m: widthM, depth_m: depthM });
  const centerXM = clampCenter(rawX, widthM, floor.widthM);
  const centerYM = clampCenter(rawY, depthM, floor.depthM);
  const id = String(raw.element_id || raw.id || `AUTHOR-${type.toUpperCase()}-${index + 1}`);
  return {
    ...raw,
    element_id: id,
    element_type: type,
    center_x_m: rounded(centerXM),
    center_y_m: rounded(centerYM),
    width_m: rounded(widthM),
    depth_m: rounded(depthM),
    rotation_deg: normalizedRotation(raw.rotation_deg),
    clearance_m: Math.max(0, rounded(raw.clearance_m || 0)),
  };
}

export function buildPlanogramAuthoringDocument(candidate, options = {}) {
  const architecture = candidate?.store_dna?.architecture;
  if (!architecture || typeof architecture !== "object") return null;
  const floor = {
    widthM: Math.max(1, finite(architecture.floor_width_m, 1)),
    depthM: Math.max(1, finite(architecture.floor_depth_m, 1)),
  };
  const elements = (Array.isArray(architecture.elements) ? architecture.elements : [])
    .map((row, index) => normalizePlanogramAuthoringElement(row, floor, index))
    .filter(Boolean);
  return {
    contract: PLANOGRAM_AUTHORING_CONTRACT,
    sourceContract: architecture.schema_version === 2
      ? "store-architecture-v2-oriented-polygons"
      : "store-architecture-v1",
    previewOnly: architecture.schema_version === 2 || Boolean(architecture.preview_only),
    gridM: Math.max(0.01, finite(options.gridM, PLANOGRAM_AUTHORING_GRID_M)),
    floor,
    architecture: {
      ...architecture,
      schema_version: architecture.schema_version === 2 ? 2 : 1,
      coordinate_system: architecture.schema_version === 2
        ? "cartesian_m_centered_rect"
        : (architecture.coordinate_system || "cartesian_m"),
      elements,
    },
  };
}

export function createPlanogramAuthoringElement({
  type,
  centerXM,
  centerYM,
  floor,
  sequence = 1,
  gridM = PLANOGRAM_AUTHORING_GRID_M,
}) {
  const normalizedType = PLANOGRAM_AUTHORING_ELEMENT_TYPES.includes(type) ? type : "wall";
  const [widthM, depthM] = DEFAULT_DIMENSIONS[normalizedType] || [1, 1];
  return normalizePlanogramAuthoringElement({
    element_id: `AUTHOR-${normalizedType.toUpperCase()}-${sequence}`,
    element_type: normalizedType,
    center_x_m: snapPlanogramAuthoringValue(centerXM, gridM),
    center_y_m: snapPlanogramAuthoringValue(centerYM, gridM),
    width_m: widthM,
    depth_m: depthM,
    rotation_deg: 0,
    human_authored: true,
    authoring_contract: PLANOGRAM_AUTHORING_CONTRACT,
  }, floor, sequence - 1);
}

export function updatePlanogramAuthoringElement(document, elementId, patch) {
  if (!document || !elementId || !patch) return document;
  const current = document.architecture.elements.find((row) => row.element_id === elementId);
  if (!current) return document;
  const nextRaw = { ...current, ...patch };
  if (patch.center_x_m != null) nextRaw.center_x_m = snapPlanogramAuthoringValue(patch.center_x_m, document.gridM);
  if (patch.center_y_m != null) nextRaw.center_y_m = snapPlanogramAuthoringValue(patch.center_y_m, document.gridM);
  if (patch.width_m != null) nextRaw.width_m = snapPlanogramAuthoringValue(Math.max(MIN_DIMENSION_M, patch.width_m), document.gridM);
  if (patch.depth_m != null) nextRaw.depth_m = snapPlanogramAuthoringValue(Math.max(MIN_DIMENSION_M, patch.depth_m), document.gridM);
  const updated = normalizePlanogramAuthoringElement(nextRaw, document.floor);
  return {
    ...document,
    architecture: {
      ...document.architecture,
      elements: document.architecture.elements.map((row) => row.element_id === elementId ? updated : row),
    },
  };
}

export function removePlanogramAuthoringElement(document, elementId) {
  if (!document || !elementId) return document;
  return {
    ...document,
    architecture: {
      ...document.architecture,
      elements: document.architecture.elements.filter((row) => row.element_id !== elementId),
    },
  };
}

export function resizePlanogramAuthoringFloor(document, widthM, depthM) {
  if (!document) return document;
  const floor = {
    widthM: Math.max(1, snapPlanogramAuthoringValue(widthM, document.gridM)),
    depthM: Math.max(1, snapPlanogramAuthoringValue(depthM, document.gridM)),
  };
  const elements = document.architecture.elements
    .map((row, index) => normalizePlanogramAuthoringElement(row, floor, index))
    .filter(Boolean);
  return {
    ...document,
    floor,
    architecture: {
      ...document.architecture,
      floor_width_m: floor.widthM,
      floor_depth_m: floor.depthM,
      elements,
    },
  };
}

export function candidateWithPlanogramAuthoringDocument(candidate, document) {
  if (!candidate || !document) return candidate;
  const architecture = {
    ...document.architecture,
    floor_width_m: document.floor.widthM,
    floor_depth_m: document.floor.depthM,
    elements: document.architecture.elements.map((row) => ({ ...row })),
    authoring_contract: PLANOGRAM_AUTHORING_CONTRACT,
    authoring_preview_only: document.previewOnly,
  };
  return {
    ...candidate,
    store_dna: {
      ...(candidate.store_dna || {}),
      architecture,
    },
  };
}

export function candidateFromReviewedStoreScan(candidate, reviewedResult) {
  const reviewedStoreDna = reviewedResult?.reviewed_store_dna_v2_preview;
  const architecture = reviewedStoreDna?.architecture;
  if (!architecture || reviewedResult?.reviewed_draft_ready !== true) return null;
  return {
    ...(candidate || {}),
    store_dna: {
      ...(candidate?.store_dna || {}),
      ...reviewedStoreDna,
      architecture: {
        ...architecture,
        preview_only: true,
        source: architecture.source || "human_reviewed_store_scan",
        authoring_contract: PLANOGRAM_AUTHORING_CONTRACT,
        authoring_preview_only: true,
        source_review_fingerprint: reviewedResult.reviewed_draft_fingerprint || null,
      },
    },
  };
}
