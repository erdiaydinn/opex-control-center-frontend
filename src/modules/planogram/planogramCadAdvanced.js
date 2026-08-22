import { createStoreSceneNode, normalizeStoreScene, snapPlanogramAuthoringValue } from "./planogramAuthoringModel.js";

export const PLANOGRAM_CAD_OVERLAY_CONTRACT = "eay.planogram.cad-overlay.v1";
export const PLANOGRAM_CAD_OVERLAY_LIMIT = 500;
export const PLANOGRAM_CAD_SNAP_GUIDE_LIMIT = 2000;

const EPSILON = 1e-9;
const OVERLAY_NODE_TYPES = new Set(["fixture", "measurement", "annotation"]);
const FIXTURE_DEFAULTS = Object.freeze({
  REGULAR_SHELF: Object.freeze({ widthM: 1, depthM: 0.5, heightM: 2, shelfCount: 5 }),
  CHILLER: Object.freeze({ widthM: 0.9, depthM: 0.8, heightM: 2, shelfCount: 5 }),
  FREEZER: Object.freeze({ widthM: 1, depthM: 0.8, heightM: 1.9, shelfCount: 4 }),
  PALLET: Object.freeze({ widthM: 1.2, depthM: 1, heightM: 0.18, shelfCount: 1 }),
  ENDCAP: Object.freeze({ widthM: 0.9, depthM: 0.6, heightM: 1.8, shelfCount: 4 }),
});

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function rounded(value, precision = 4) {
  const factor = 10 ** precision;
  return Math.round(finite(value) * factor) / factor;
}

function text(value) {
  return String(value ?? "").trim();
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (!value || typeof value !== "object") return value;
  return Object.keys(value).sort().reduce((result, key) => {
    result[key] = stableValue(value[key]);
    return result;
  }, {});
}

function rejectRemoteStrings(value, path = "cad_overlay") {
  if (typeof value === "string") {
    if (/^(?:https?:)?\/\//iu.test(value.trim())) throw new Error(`Remote CAD overlay value is not allowed: ${path}`);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => rejectRemoteStrings(item, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) rejectRemoteStrings(child, `${path}.${key}`);
}

function overlayNode(raw) {
  const node = createStoreSceneNode(raw);
  if (!OVERLAY_NODE_TYPES.has(node.nodeType)) throw new Error(`Unsupported CAD overlay node type: ${node.nodeType}`);
  rejectRemoteStrings(node);
  return createStoreSceneNode({
    ...node,
    metadata: {
      ...(node.metadata || {}),
      cadOverlay: true,
      productionReleaseAllowed: false,
    },
  });
}

function overlayNodesFromScene(scene) {
  return normalizeStoreScene(scene).nodes.filter((node) => OVERLAY_NODE_TYPES.has(node.nodeType));
}

export function hydratePlanogramCadOverlay(inputScene, candidate) {
  const scene = normalizeStoreScene(inputScene);
  const overlay = candidate?.store_dna?.cad_overlay;
  if (overlay == null) return scene;
  if (!overlay || overlay.contract !== PLANOGRAM_CAD_OVERLAY_CONTRACT) throw new Error("Canonical CAD overlay contract is required.");
  if (overlay.preview_only !== true || overlay.production_release_allowed !== false) throw new Error("CAD overlay must remain preview-only and non-production.");
  if (!Array.isArray(overlay.nodes)) throw new Error("CAD overlay nodes must be an array.");
  if (overlay.nodes.length > PLANOGRAM_CAD_OVERLAY_LIMIT) throw new Error(`CAD overlay node limit exceeded: ${overlay.nodes.length}`);
  rejectRemoteStrings(overlay);

  const seen = new Set(scene.nodes.map((node) => node.nodeId));
  const hydrated = overlay.nodes.map((raw) => {
    const node = overlayNode(raw);
    if (seen.has(node.nodeId)) throw new Error(`CAD overlay node id collides with StoreScene: ${node.nodeId}`);
    seen.add(node.nodeId);
    return node;
  });
  return normalizeStoreScene({ ...scene, nodes: [...scene.nodes, ...hydrated] });
}

export function candidateWithPlanogramCadOverlay(candidate, scene) {
  if (!candidate || !scene) return candidate;
  const nodes = overlayNodesFromScene(scene).map((node) => stableValue({
    nodeId: node.nodeId,
    nodeType: node.nodeType,
    parentId: node.parentId,
    geometry: { ...node.geometry },
    locked: Boolean(node.locked),
    provenance: node.provenance || {},
    metadata: {
      ...(node.metadata || {}),
      cadOverlay: true,
      productionReleaseAllowed: false,
    },
  }));
  const storeDna = { ...(candidate.store_dna || {}) };
  if (!nodes.length && !storeDna.cad_overlay) return candidate;
  storeDna.cad_overlay = Object.freeze({
    contract: PLANOGRAM_CAD_OVERLAY_CONTRACT,
    preview_only: true,
    production_release_allowed: false,
    physical_truth_attested: false,
    authority: "human_cad_preview_not_store_dna_authority",
    nodes: Object.freeze(nodes),
  });
  return { ...candidate, store_dna: storeDna };
}

export function createPlanogramCadFixtureNode({
  nodeId,
  fixtureType = "REGULAR_SHELF",
  fixtureCode = null,
  centerXM,
  centerYM,
  widthM = null,
  depthM = null,
  heightM = null,
  rotationDeg = 0,
  shelfCount = null,
  sourceRef = "cad-session-ui",
} = {}) {
  const normalizedType = text(fixtureType).toUpperCase() || "REGULAR_SHELF";
  const defaults = FIXTURE_DEFAULTS[normalizedType] || FIXTURE_DEFAULTS.REGULAR_SHELF;
  const normalizedCode = text(fixtureCode).toUpperCase();
  if (normalizedCode && /[\\/]|https?:/iu.test(normalizedCode)) throw new Error("Fixture code must be an internal identifier, not a path or URL.");
  return overlayNode({
    nodeId: text(nodeId),
    nodeType: "fixture",
    geometry: {
      centerXM: finite(centerXM),
      centerYM: finite(centerYM),
      widthM: Math.max(0.05, finite(widthM, defaults.widthM)),
      depthM: Math.max(0.05, finite(depthM, defaults.depthM)),
      heightM: Math.max(0, finite(heightM, defaults.heightM)),
      rotationDeg: finite(rotationDeg),
    },
    provenance: { source: "human", sourceRef: text(sourceRef) || "cad-session-ui" },
    metadata: {
      fixtureType: normalizedType,
      fixtureCode: normalizedCode || null,
      shelfCount: Math.max(1, Math.round(finite(shelfCount, defaults.shelfCount))),
      dimensionAuthority: "human_cad_preview",
    },
  });
}

function nodeById(scene, nodeId) {
  return normalizeStoreScene(scene).nodes.find((node) => node.nodeId === nodeId) || null;
}

export function createPlanogramCadMeasurementNode({ scene, nodeId, sourceNodeIds, sourceRef = "cad-session-ui" } = {}) {
  const ids = Array.isArray(sourceNodeIds) ? sourceNodeIds.map(text).filter(Boolean) : [];
  if (ids.length !== 2 || ids[0] === ids[1]) throw new Error("CAD measurement requires two distinct source nodes.");
  const left = nodeById(scene, ids[0]);
  const right = nodeById(scene, ids[1]);
  if (!left || !right) throw new Error("CAD measurement source node was not found.");
  const deltaXM = rounded(right.geometry.centerXM - left.geometry.centerXM);
  const deltaYM = rounded(right.geometry.centerYM - left.geometry.centerYM);
  const distanceM = rounded(Math.hypot(deltaXM, deltaYM));
  return overlayNode({
    nodeId: text(nodeId),
    nodeType: "measurement",
    geometry: {
      centerXM: rounded((left.geometry.centerXM + right.geometry.centerXM) / 2),
      centerYM: rounded((left.geometry.centerYM + right.geometry.centerYM) / 2),
      widthM: 0.05,
      depthM: 0.05,
      heightM: 0,
      rotationDeg: 0,
    },
    provenance: { source: "human", sourceRef: text(sourceRef) || "cad-session-ui" },
    metadata: {
      measurementKind: "center_distance",
      sourceNodeIds: ids,
      deltaXM,
      deltaYM,
      measuredDistanceM: distanceM,
      dimensionAuthority: "canonical_store_scene_metric_preview",
    },
  });
}

function rectangleBounds(node) {
  const geometry = node.geometry || {};
  const angle = finite(geometry.rotationDeg) * Math.PI / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const halfWidth = Math.max(0.025, finite(geometry.widthM, 0.05)) / 2;
  const halfDepth = Math.max(0.025, finite(geometry.depthM, 0.05)) / 2;
  const points = [[-halfWidth, -halfDepth], [halfWidth, -halfDepth], [halfWidth, halfDepth], [-halfWidth, halfDepth]].map(([x, y]) => ({
    x: finite(geometry.centerXM) + x * cos - y * sin,
    y: finite(geometry.centerYM) + x * sin + y * cos,
  }));
  return {
    minX: Math.min(...points.map((point) => point.x)),
    maxX: Math.max(...points.map((point) => point.x)),
    minY: Math.min(...points.map((point) => point.y)),
    maxY: Math.max(...points.map((point) => point.y)),
  };
}

export function buildPlanogramCadSelectionMetrics(inputScene, nodeIds = []) {
  const scene = normalizeStoreScene(inputScene);
  const ids = new Set(nodeIds.map(text).filter(Boolean));
  const nodes = scene.nodes.filter((node) => ids.has(node.nodeId) && node.nodeType !== "measurement" && node.nodeType !== "annotation");
  if (!nodes.length) return Object.freeze({ count: 0, nodeIds: Object.freeze([]), bounds: null, center: null, widthM: 0, depthM: 0 });
  const bounds = nodes.map(rectangleBounds);
  const minX = Math.min(...bounds.map((row) => row.minX));
  const maxX = Math.max(...bounds.map((row) => row.maxX));
  const minY = Math.min(...bounds.map((row) => row.minY));
  const maxY = Math.max(...bounds.map((row) => row.maxY));
  return Object.freeze({
    count: nodes.length,
    nodeIds: Object.freeze(nodes.map((node) => node.nodeId)),
    bounds: Object.freeze({ minX: rounded(minX), maxX: rounded(maxX), minY: rounded(minY), maxY: rounded(maxY) }),
    center: Object.freeze({ x: rounded((minX + maxX) / 2), y: rounded((minY + maxY) / 2) }),
    widthM: rounded(maxX - minX),
    depthM: rounded(maxY - minY),
  });
}

export function buildPlanogramCadDistributeUpdates(inputScene, nodeIds = [], axis = "x") {
  const scene = normalizeStoreScene(inputScene);
  const normalizedAxis = axis === "y" ? "y" : "x";
  const field = normalizedAxis === "x" ? "centerXM" : "centerYM";
  const ids = [...new Set(nodeIds.map(text).filter(Boolean))];
  if (ids.length < 3) return Object.freeze([]);
  const byId = new Map(scene.nodes.map((node) => [node.nodeId, node]));
  const nodes = ids.map((id) => byId.get(id));
  if (nodes.some((node) => !node)) throw new Error("CAD distribute selection contains an unknown node.");
  if (nodes.some((node) => node.locked)) throw new Error("CAD distribute cannot move locked nodes.");
  const sorted = [...nodes].sort((left, right) => left.geometry[field] - right.geometry[field] || left.nodeId.localeCompare(right.nodeId));
  const start = finite(sorted[0].geometry[field]);
  const end = finite(sorted[sorted.length - 1].geometry[field]);
  const step = (end - start) / (sorted.length - 1);
  const updates = [];
  sorted.forEach((node, index) => {
    const target = rounded(start + step * index);
    if (Math.abs(target - finite(node.geometry[field])) <= EPSILON) return;
    updates.push(Object.freeze({ nodeId: node.nodeId, patch: Object.freeze({ geometry: Object.freeze({ [field]: target }) }) }));
  });
  return Object.freeze(updates);
}

export function buildPlanogramCadSnapGuides(inputScene, movingNodeIds = []) {
  const scene = normalizeStoreScene(inputScene);
  const moving = new Set(movingNodeIds.map(text).filter(Boolean));
  const guides = [
    { axis: "x", value: 0, kind: "floor-edge", sourceNodeId: null },
    { axis: "x", value: scene.floor.widthM, kind: "floor-edge", sourceNodeId: null },
    { axis: "y", value: 0, kind: "floor-edge", sourceNodeId: null },
    { axis: "y", value: scene.floor.depthM, kind: "floor-edge", sourceNodeId: null },
  ];
  for (const node of scene.nodes) {
    if (moving.has(node.nodeId) || node.nodeType === "measurement" || node.nodeType === "annotation") continue;
    const bounds = rectangleBounds(node);
    guides.push(
      { axis: "x", value: bounds.minX, kind: "edge", sourceNodeId: node.nodeId },
      { axis: "x", value: finite(node.geometry.centerXM), kind: "center", sourceNodeId: node.nodeId },
      { axis: "x", value: bounds.maxX, kind: "edge", sourceNodeId: node.nodeId },
      { axis: "y", value: bounds.minY, kind: "edge", sourceNodeId: node.nodeId },
      { axis: "y", value: finite(node.geometry.centerYM), kind: "center", sourceNodeId: node.nodeId },
      { axis: "y", value: bounds.maxY, kind: "edge", sourceNodeId: node.nodeId },
    );
    if (guides.length > PLANOGRAM_CAD_SNAP_GUIDE_LIMIT) throw new Error("CAD snap guide limit exceeded.");
  }
  return Object.freeze(guides.map((guide) => Object.freeze({ ...guide, value: rounded(guide.value) })));
}

function nearestGuideCorrection(selectionAnchors, guides, proposedDelta, thresholdM) {
  const candidates = [];
  for (const anchor of selectionAnchors) {
    const proposed = anchor.value + proposedDelta;
    for (const guide of guides) {
      const correction = guide.value - proposed;
      const distance = Math.abs(correction);
      if (distance <= thresholdM + EPSILON) candidates.push({ anchor, guide, correction, distance });
    }
  }
  candidates.sort((left, right) => left.distance - right.distance || left.guide.value - right.guide.value || String(left.guide.sourceNodeId || "").localeCompare(String(right.guide.sourceNodeId || "")) || left.anchor.value - right.anchor.value);
  return candidates[0] || null;
}

export function snapPlanogramCadSelectionDelta(inputScene, movingNodeIds = [], deltaX = 0, deltaY = 0, options = {}) {
  const scene = normalizeStoreScene(inputScene);
  const metrics = buildPlanogramCadSelectionMetrics(scene, movingNodeIds);
  if (!metrics.count) return Object.freeze({ deltaX: 0, deltaY: 0, guides: Object.freeze([]), snappedX: false, snappedY: false });
  const gridM = Math.max(0.001, finite(options.gridM, 0.05));
  const thresholdM = Math.max(0, finite(options.thresholdM, 0.08));
  const baseDeltaX = snapPlanogramAuthoringValue(deltaX, gridM);
  const baseDeltaY = snapPlanogramAuthoringValue(deltaY, gridM);
  const allGuides = buildPlanogramCadSnapGuides(scene, movingNodeIds);
  const xGuides = allGuides.filter((guide) => guide.axis === "x");
  const yGuides = allGuides.filter((guide) => guide.axis === "y");
  const xAnchors = [metrics.bounds.minX, metrics.center.x, metrics.bounds.maxX].map((value) => ({ value }));
  const yAnchors = [metrics.bounds.minY, metrics.center.y, metrics.bounds.maxY].map((value) => ({ value }));
  const snapX = nearestGuideCorrection(xAnchors, xGuides, baseDeltaX, thresholdM);
  const snapY = nearestGuideCorrection(yAnchors, yGuides, baseDeltaY, thresholdM);
  const guides = [];
  if (snapX) guides.push(Object.freeze({ axis: "x", value: snapX.guide.value, kind: snapX.guide.kind, sourceNodeId: snapX.guide.sourceNodeId }));
  if (snapY) guides.push(Object.freeze({ axis: "y", value: snapY.guide.value, kind: snapY.guide.kind, sourceNodeId: snapY.guide.sourceNodeId }));
  return Object.freeze({
    deltaX: rounded(baseDeltaX + (snapX?.correction || 0)),
    deltaY: rounded(baseDeltaY + (snapY?.correction || 0)),
    guides: Object.freeze(guides),
    snappedX: Boolean(snapX),
    snappedY: Boolean(snapY),
  });
}
