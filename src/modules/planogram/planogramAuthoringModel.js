export const PLANOGRAM_AUTHORING_CONTRACT = "planogram-architectural-authoring-v1";
export const PLANOGRAM_STORE_SCENE_CONTRACT = "planogram-store-scene-v1";
export const PLANOGRAM_AUTHORING_GRID_M = 0.05;
export const PLANOGRAM_STORE_SCENE_UNITS = "m";
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
export const PLANOGRAM_STORE_SCENE_NODE_TYPES = Object.freeze([
  "store",
  "level",
  "wall",
  "door",
  "window",
  "column",
  "zone",
  "aisle",
  "fixture",
  "bay",
  "shelf",
  "product-placement",
  "measurement",
  "annotation",
  "no_go",
  "technical",
  "inbound",
  "dispatch",
  "picker_entry",
  "picker_exit",
  "emergency_exit",
]);

const MIN_DIMENSION_M = 0.05;
const EPSILON = 1e-9;
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

function normalizedId(value, fallback) {
  const text = String(value || fallback || "").trim();
  if (!text) throw new Error("StoreScene node id is required.");
  return text;
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (!value || typeof value !== "object") return value;
  return Object.keys(value).sort().reduce((result, key) => {
    result[key] = stableValue(value[key]);
    return result;
  }, {});
}

function sortSceneNodes(nodes) {
  return [...nodes].sort((left, right) => String(left.nodeId).localeCompare(String(right.nodeId)));
}

function cloneScene(scene) {
  return JSON.parse(JSON.stringify(scene));
}

export function snapPlanogramAuthoringValue(value, stepM = PLANOGRAM_AUTHORING_GRID_M) {
  const step = Math.max(0.001, finite(stepM, PLANOGRAM_AUTHORING_GRID_M));
  return rounded(Math.round(finite(value) / step) * step);
}

export function snapStoreSceneCoordinate(value, anchors = [], options = {}) {
  const numericValue = finite(value);
  const thresholdM = Math.max(0, finite(options.thresholdM, PLANOGRAM_AUTHORING_GRID_M));
  const gridM = Math.max(0.001, finite(options.gridM, PLANOGRAM_AUTHORING_GRID_M));
  const candidates = anchors
    .map((anchor) => finite(anchor, Number.NaN))
    .filter(Number.isFinite)
    .map((anchor) => ({ anchor, distance: Math.abs(anchor - numericValue) }))
    .filter((item) => item.distance <= thresholdM + EPSILON)
    .sort((left, right) => left.distance - right.distance || left.anchor - right.anchor);
  if (candidates.length) return rounded(candidates[0].anchor);
  return snapPlanogramAuthoringValue(numericValue, gridM);
}

function centerForElement(element) {
  const width = Math.max(MIN_DIMENSION_M, finite(element?.width_m, MIN_DIMENSION_M));
  const depth = Math.max(MIN_DIMENSION_M, finite(element?.depth_m, MIN_DIMENSION_M));
  const hasCenter = Number.isFinite(Number(element?.center_x_m)) && Number.isFinite(Number(element?.center_y_m));
  if (hasCenter) return [finite(element.center_x_m), finite(element.center_y_m)];
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

function normalizeStoreSceneGeometry(raw = {}) {
  return {
    centerXM: rounded(raw.centerXM ?? raw.center_x_m),
    centerYM: rounded(raw.centerYM ?? raw.center_y_m),
    widthM: Math.max(MIN_DIMENSION_M, rounded(raw.widthM ?? raw.width_m, 3)),
    depthM: Math.max(MIN_DIMENSION_M, rounded(raw.depthM ?? raw.depth_m, 3)),
    heightM: Math.max(0, rounded(raw.heightM ?? raw.height_m ?? 0, 3)),
    rotationDeg: normalizedRotation(raw.rotationDeg ?? raw.rotation_deg),
  };
}

export function createStoreSceneNode(raw = {}) {
  const nodeType = String(raw.nodeType || raw.node_type || raw.element_type || raw.type || "annotation")
    .trim()
    .toLowerCase();
  if (!PLANOGRAM_STORE_SCENE_NODE_TYPES.includes(nodeType)) {
    throw new Error(`Unsupported StoreScene node type: ${nodeType}`);
  }
  const nodeId = normalizedId(raw.nodeId || raw.node_id || raw.element_id || raw.id, `${nodeType}-1`);
  return {
    nodeId,
    nodeType,
    parentId: raw.parentId || raw.parent_id || null,
    geometry: normalizeStoreSceneGeometry(raw.geometry || raw),
    locked: Boolean(raw.locked),
    provenance: stableValue(raw.provenance || {
      source: raw.scan_source_element_id ? "reviewed-scan" : (raw.human_authored ? "human" : "authoring"),
      sourceRef: raw.scan_source_element_id || null,
    }),
    metadata: stableValue(raw.metadata || {}),
  };
}

function sceneNodesFromAuthoringDocument(document) {
  return (document?.architecture?.elements || []).map((element) => createStoreSceneNode({
    nodeId: element.element_id,
    nodeType: element.element_type,
    geometry: element,
    locked: element.locked,
    provenance: {
      source: element.scan_source_element_id ? "reviewed-scan" : (element.human_authored ? "human" : "architecture"),
      sourceRef: element.scan_source_element_id || document?.architecture?.source_ref || null,
      reviewFingerprint: document?.architecture?.source_review_fingerprint || null,
    },
    metadata: { clearanceM: Math.max(0, finite(element.clearance_m)) },
  }));
}

export function buildStoreScene(candidate, authoringDocument = buildPlanogramAuthoringDocument(candidate), options = {}) {
  if (!authoringDocument) return null;
  const sourceId = candidate?.store_code
    || candidate?.store_dna?.store_code
    || authoringDocument?.architecture?.source_ref
    || "planogram-store";
  const sceneId = normalizedId(options.sceneId, `STORE-SCENE-${String(sourceId).replace(/[^a-zA-Z0-9_-]+/g, "-")}`);
  return {
    contract: PLANOGRAM_STORE_SCENE_CONTRACT,
    schemaVersion: 1,
    sceneId,
    revision: Math.max(0, Math.trunc(finite(options.revision, 0))),
    units: PLANOGRAM_STORE_SCENE_UNITS,
    previewOnly: Boolean(authoringDocument.previewOnly),
    floor: {
      widthM: rounded(authoringDocument.floor.widthM),
      depthM: rounded(authoringDocument.floor.depthM),
    },
    nodes: sortSceneNodes(sceneNodesFromAuthoringDocument(authoringDocument)),
    provenance: stableValue({
      sourceContract: authoringDocument.sourceContract,
      sourceRef: authoringDocument?.architecture?.source_ref || null,
      reviewFingerprint: authoringDocument?.architecture?.source_review_fingerprint || null,
      physicalTruthAttested: false,
    }),
  };
}

export function normalizeStoreScene(scene) {
  if (!scene || scene.contract !== PLANOGRAM_STORE_SCENE_CONTRACT) {
    throw new Error("Canonical StoreScene contract is required.");
  }
  const seen = new Set();
  const nodes = sortSceneNodes((scene.nodes || []).map((node) => createStoreSceneNode(node)));
  for (const node of nodes) {
    if (seen.has(node.nodeId)) throw new Error(`Duplicate StoreScene node id: ${node.nodeId}`);
    seen.add(node.nodeId);
  }
  return {
    contract: PLANOGRAM_STORE_SCENE_CONTRACT,
    schemaVersion: 1,
    sceneId: normalizedId(scene.sceneId, "STORE-SCENE"),
    revision: Math.max(0, Math.trunc(finite(scene.revision, 0))),
    units: PLANOGRAM_STORE_SCENE_UNITS,
    previewOnly: Boolean(scene.previewOnly),
    floor: {
      widthM: Math.max(1, rounded(scene.floor?.widthM, 3)),
      depthM: Math.max(1, rounded(scene.floor?.depthM, 3)),
    },
    nodes,
    provenance: stableValue(scene.provenance || { physicalTruthAttested: false }),
  };
}

export function serializeStoreScene(scene) {
  return JSON.stringify(stableValue(normalizeStoreScene(scene)));
}

export function deserializeStoreScene(serialized) {
  return normalizeStoreScene(JSON.parse(String(serialized)));
}

function projectStoreScene(scene, view) {
  const normalized = normalizeStoreScene(scene);
  return {
    contract: PLANOGRAM_STORE_SCENE_CONTRACT,
    view,
    sceneId: normalized.sceneId,
    revision: normalized.revision,
    units: normalized.units,
    floor: { ...normalized.floor },
    nodes: normalized.nodes.map((node) => ({
      nodeId: node.nodeId,
      nodeType: node.nodeType,
      parentId: node.parentId,
      geometry: { ...node.geometry },
      locked: node.locked,
    })),
  };
}

export function projectStoreScene2D(scene) {
  return projectStoreScene(scene, "2d");
}

export function projectStoreScene3D(scene) {
  return projectStoreScene(scene, "3d");
}

function requireSceneRevision(scene, command) {
  if (command.expectedRevision == null) return;
  if (Math.trunc(finite(command.expectedRevision, -1)) !== scene.revision) {
    throw new Error(`StoreScene revision conflict: expected ${command.expectedRevision}, found ${scene.revision}`);
  }
}

function nextScene(scene, nodes) {
  return normalizeStoreScene({ ...scene, revision: scene.revision + 1, nodes });
}

export function applyStoreSceneCommand(inputScene, rawCommand = {}) {
  const scene = normalizeStoreScene(inputScene);
  const command = { ...rawCommand, type: String(rawCommand.type || "").toUpperCase() };
  requireSceneRevision(scene, command);
  if (!command.commandId) throw new Error("StoreScene commandId is required.");

  if (command.type === "CREATE_NODE") {
    const node = createStoreSceneNode(command.node);
    if (scene.nodes.some((row) => row.nodeId === node.nodeId)) throw new Error(`StoreScene node already exists: ${node.nodeId}`);
    const next = nextScene(scene, [...scene.nodes, node]);
    return {
      scene: next,
      command,
      inverseCommand: { commandId: `${command.commandId}:undo`, type: "DELETE_NODE", nodeId: node.nodeId, force: true },
    };
  }

  const index = scene.nodes.findIndex((row) => row.nodeId === command.nodeId);
  if (index < 0) throw new Error(`StoreScene node not found: ${command.nodeId}`);
  const current = scene.nodes[index];
  if (current.locked && command.force !== true && command.type !== "SET_LOCK") {
    throw new Error(`StoreScene node is locked: ${current.nodeId}`);
  }

  if (command.type === "UPDATE_NODE") {
    const patched = createStoreSceneNode({
      ...current,
      ...command.patch,
      geometry: { ...current.geometry, ...(command.patch?.geometry || {}) },
      provenance: command.patch?.provenance || current.provenance,
      metadata: { ...current.metadata, ...(command.patch?.metadata || {}) },
    });
    const nodes = scene.nodes.map((node, nodeIndex) => nodeIndex === index ? patched : node);
    return {
      scene: nextScene(scene, nodes),
      command,
      inverseCommand: { commandId: `${command.commandId}:undo`, type: "UPDATE_NODE", nodeId: current.nodeId, patch: current, force: true },
    };
  }

  if (command.type === "DELETE_NODE") {
    const childIds = new Set([current.nodeId]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const node of scene.nodes) {
        if (node.parentId && childIds.has(node.parentId) && !childIds.has(node.nodeId)) {
          childIds.add(node.nodeId);
          changed = true;
        }
      }
    }
    const removed = scene.nodes.filter((node) => childIds.has(node.nodeId));
    const retained = scene.nodes.filter((node) => !childIds.has(node.nodeId));
    return {
      scene: nextScene(scene, retained),
      command,
      inverseCommand: {
        commandId: `${command.commandId}:undo`,
        type: "RESTORE_NODES",
        nodes: removed,
        force: true,
      },
    };
  }

  if (command.type === "SET_LOCK") {
    const patched = { ...current, locked: Boolean(command.locked) };
    const nodes = scene.nodes.map((node, nodeIndex) => nodeIndex === index ? patched : node);
    return {
      scene: nextScene(scene, nodes),
      command,
      inverseCommand: { commandId: `${command.commandId}:undo`, type: "SET_LOCK", nodeId: current.nodeId, locked: current.locked, force: true },
    };
  }

  if (command.type === "RESTORE_NODES") {
    const restored = (command.nodes || []).map(createStoreSceneNode);
    const existing = new Set(scene.nodes.map((node) => node.nodeId));
    if (restored.some((node) => existing.has(node.nodeId))) throw new Error("StoreScene restore would create duplicate node ids.");
    return {
      scene: nextScene(scene, [...scene.nodes, ...restored]),
      command,
      inverseCommand: { commandId: `${command.commandId}:undo`, type: "DELETE_NODE", nodeId: restored[0]?.nodeId, force: true },
    };
  }

  throw new Error(`Unsupported StoreScene command: ${command.type}`);
}

export function createStoreSceneHistory(scene) {
  return { past: [], present: normalizeStoreScene(scene), future: [] };
}

export function executeStoreSceneCommand(history, command) {
  const applied = applyStoreSceneCommand(history.present, command);
  return {
    past: [...history.past, { command: applied.command, inverseCommand: applied.inverseCommand }],
    present: applied.scene,
    future: [],
  };
}

export function undoStoreSceneCommand(history) {
  if (!history.past.length) return history;
  const entry = history.past[history.past.length - 1];
  const undone = applyStoreSceneCommand(history.present, { ...entry.inverseCommand, force: true });
  return {
    past: history.past.slice(0, -1),
    present: undone.scene,
    future: [entry, ...history.future],
  };
}

export function redoStoreSceneCommand(history) {
  if (!history.future.length) return history;
  const [entry, ...future] = history.future;
  const redone = applyStoreSceneCommand(history.present, { ...entry.command, expectedRevision: undefined, force: true });
  return {
    past: [...history.past, { command: entry.command, inverseCommand: redone.inverseCommand }],
    present: redone.scene,
    future,
  };
}

function rectangleCorners(node) {
  const geometry = node.geometry;
  const angle = geometry.rotationDeg * Math.PI / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const halfWidth = geometry.widthM / 2;
  const halfDepth = geometry.depthM / 2;
  return [
    [-halfWidth, -halfDepth],
    [halfWidth, -halfDepth],
    [halfWidth, halfDepth],
    [-halfWidth, halfDepth],
  ].map(([x, y]) => ({
    x: geometry.centerXM + x * cos - y * sin,
    y: geometry.centerYM + x * sin + y * cos,
  }));
}

function polygonAxes(points) {
  return points.map((point, index) => {
    const next = points[(index + 1) % points.length];
    const dx = next.x - point.x;
    const dy = next.y - point.y;
    const length = Math.hypot(dx, dy) || 1;
    return { x: -dy / length, y: dx / length };
  });
}

function projectedRange(points, axis) {
  const values = points.map((point) => point.x * axis.x + point.y * axis.y);
  return [Math.min(...values), Math.max(...values)];
}

export function storeSceneNodesCollide(left, right) {
  const leftPoints = rectangleCorners(left);
  const rightPoints = rectangleCorners(right);
  for (const axis of [...polygonAxes(leftPoints), ...polygonAxes(rightPoints)]) {
    const [leftMin, leftMax] = projectedRange(leftPoints, axis);
    const [rightMin, rightMax] = projectedRange(rightPoints, axis);
    if (leftMax <= rightMin + EPSILON || rightMax <= leftMin + EPSILON) return false;
  }
  return true;
}

export function findStoreSceneCollisions(scene, nodeTypes = ["fixture"]) {
  const normalized = normalizeStoreScene(scene);
  const allowed = new Set(nodeTypes);
  const nodes = normalized.nodes.filter((node) => allowed.has(node.nodeType));
  const collisions = [];
  for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
      if (storeSceneNodesCollide(nodes[leftIndex], nodes[rightIndex])) {
        collisions.push({ leftNodeId: nodes[leftIndex].nodeId, rightNodeId: nodes[rightIndex].nodeId });
      }
    }
  }
  return collisions;
}

function rotatedBounds(node) {
  const points = rectangleCorners(node);
  return {
    minX: Math.min(...points.map((point) => point.x)),
    maxX: Math.max(...points.map((point) => point.x)),
    minY: Math.min(...points.map((point) => point.y)),
    maxY: Math.max(...points.map((point) => point.y)),
  };
}

function boundsClearance(left, right) {
  const leftBounds = rotatedBounds(left);
  const rightBounds = rotatedBounds(right);
  const gapX = Math.max(0, leftBounds.minX - rightBounds.maxX, rightBounds.minX - leftBounds.maxX);
  const gapY = Math.max(0, leftBounds.minY - rightBounds.maxY, rightBounds.minY - leftBounds.maxY);
  return rounded(Math.hypot(gapX, gapY), 4);
}

export function findStoreSceneAisleViolations(scene, minimumAisleM = 1, nodeTypes = ["fixture"]) {
  const normalized = normalizeStoreScene(scene);
  const allowed = new Set(nodeTypes);
  const nodes = normalized.nodes.filter((node) => allowed.has(node.nodeType));
  const violations = [];
  for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
      const left = nodes[leftIndex];
      const right = nodes[rightIndex];
      const clearanceM = storeSceneNodesCollide(left, right) ? 0 : boundsClearance(left, right);
      if (clearanceM + EPSILON < minimumAisleM) {
        violations.push({
          leftNodeId: left.nodeId,
          rightNodeId: right.nodeId,
          clearanceM,
          minimumAisleM: rounded(minimumAisleM, 4),
          deficitM: rounded(minimumAisleM - clearanceM, 4),
        });
      }
    }
  }
  return violations;
}

export function applyOptimizerStoreSceneSuggestions(scene, suggestions = [], options = {}) {
  let current = normalizeStoreScene(scene);
  const applied = [];
  const blocked = [];
  for (const [index, suggestion] of suggestions.entries()) {
    const node = current.nodes.find((row) => row.nodeId === suggestion.nodeId);
    if (!node) {
      blocked.push({ nodeId: suggestion.nodeId, reason: "node-not-found" });
      continue;
    }
    if (node.locked) {
      blocked.push({ nodeId: suggestion.nodeId, reason: "locked-human-override" });
      continue;
    }
    const commandId = suggestion.commandId || `OPTIMIZER-${options.optimizerRunId || "RUN"}-${index + 1}`;
    const result = applyStoreSceneCommand(current, {
      commandId,
      type: "UPDATE_NODE",
      nodeId: suggestion.nodeId,
      expectedRevision: current.revision,
      patch: {
        ...suggestion.patch,
        provenance: {
          ...node.provenance,
          source: "optimizer",
          optimizerRunId: options.optimizerRunId || null,
          humanOverride: false,
        },
      },
    });
    current = result.scene;
    applied.push({ nodeId: suggestion.nodeId, commandId });
  }
  return { scene: current, applied, blocked };
}