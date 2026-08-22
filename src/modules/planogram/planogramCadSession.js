import {
  applyStoreSceneCommand,
  buildPlanogramAuthoringDocument,
  buildStoreScene,
  candidateFromReviewedStoreScan,
  candidateWithPlanogramAuthoringDocument,
  createStoreSceneNode,
  findStoreSceneAisleViolations,
  findStoreSceneCollisions,
  normalizeStoreScene,
  PLANOGRAM_AUTHORING_ELEMENT_TYPES,
  serializeStoreScene,
} from "./planogramAuthoringModel.js";

export const PLANOGRAM_CAD_SESSION_CONTRACT = "eay.planogram.cad-session.v1";
export const PLANOGRAM_CAD_BATCH_LIMIT = 100;

const EPSILON = 1e-9;
const AUTHORING_TYPES = new Set(PLANOGRAM_AUTHORING_ELEMENT_TYPES);

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function rounded(value, precision = 3) {
  const factor = 10 ** precision;
  return Math.round(finite(value) * factor) / factor;
}

function rectangleCorners(node) {
  const geometry = node.geometry || {};
  const angle = finite(geometry.rotationDeg) * Math.PI / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const halfWidth = Math.max(0.025, finite(geometry.widthM, 0.05)) / 2;
  const halfDepth = Math.max(0.025, finite(geometry.depthM, 0.05)) / 2;
  return [
    [-halfWidth, -halfDepth],
    [halfWidth, -halfDepth],
    [halfWidth, halfDepth],
    [-halfWidth, halfDepth],
  ].map(([x, y]) => ({
    x: finite(geometry.centerXM) + x * cos - y * sin,
    y: finite(geometry.centerYM) + x * sin + y * cos,
  }));
}

function findBoundaryViolations(scene) {
  const normalized = normalizeStoreScene(scene);
  const violations = [];
  for (const node of normalized.nodes) {
    if (!AUTHORING_TYPES.has(node.nodeType) && node.nodeType !== "fixture") continue;
    const points = rectangleCorners(node);
    const minX = Math.min(...points.map((point) => point.x));
    const maxX = Math.max(...points.map((point) => point.x));
    const minY = Math.min(...points.map((point) => point.y));
    const maxY = Math.max(...points.map((point) => point.y));
    const overflow = {
      leftM: rounded(Math.max(0, -minX), 4),
      rightM: rounded(Math.max(0, maxX - normalized.floor.widthM), 4),
      bottomM: rounded(Math.max(0, -minY), 4),
      topM: rounded(Math.max(0, maxY - normalized.floor.depthM), 4),
    };
    const outsideM = rounded(Math.max(overflow.leftM, overflow.rightM, overflow.bottomM, overflow.topM), 4);
    if (outsideM > EPSILON) violations.push(Object.freeze({ nodeId: node.nodeId, outsideM, overflow: Object.freeze(overflow) }));
  }
  return Object.freeze(violations);
}

function diagnostics(scene, minimumAisleM) {
  const collisions = findStoreSceneCollisions(scene, ["fixture", "wall", "column", "no_go", "technical"]);
  const aisleViolations = findStoreSceneAisleViolations(scene, minimumAisleM, ["fixture"]);
  const boundaryViolations = findBoundaryViolations(scene);
  return Object.freeze({
    collisionCount: collisions.length,
    aisleViolationCount: aisleViolations.length,
    boundaryViolationCount: boundaryViolations.length,
    lockedNodeCount: scene.nodes.filter((node) => node.locked).length,
    collisions: Object.freeze(collisions),
    aisleViolations: Object.freeze(aisleViolations),
    boundaryViolations,
  });
}

function sourceRowForNode(baseDocument, nodeId) {
  return (baseDocument?.architecture?.elements || []).find((row) => row.element_id === nodeId) || null;
}

function authoringElementFromNode(baseDocument, node) {
  const source = sourceRowForNode(baseDocument, node.nodeId) || {};
  const provenance = node.provenance || {};
  const clearanceM = Math.max(0, finite(node.metadata?.clearanceM, source.clearance_m || 0));
  const scanSourceElementId = source.scan_source_element_id || (provenance.source === "reviewed-scan" ? provenance.sourceRef : null);
  return {
    ...source,
    element_id: node.nodeId,
    element_type: node.nodeType,
    center_x_m: rounded(node.geometry.centerXM),
    center_y_m: rounded(node.geometry.centerYM),
    width_m: rounded(node.geometry.widthM),
    depth_m: rounded(node.geometry.depthM),
    height_m: rounded(node.geometry.heightM),
    rotation_deg: rounded(node.geometry.rotationDeg, 2),
    clearance_m: rounded(clearanceM),
    locked: Boolean(node.locked),
    human_authored: Boolean(source.human_authored || provenance.source === "human"),
    scan_source_element_id: scanSourceElementId || undefined,
  };
}

function documentFromScene(baseDocument, scene) {
  const elements = scene.nodes.filter((node) => AUTHORING_TYPES.has(node.nodeType)).map((node) => authoringElementFromNode(baseDocument, node));
  return {
    ...baseDocument,
    floor: { widthM: scene.floor.widthM, depthM: scene.floor.depthM },
    architecture: {
      ...(baseDocument?.architecture || {}),
      floor_width_m: scene.floor.widthM,
      floor_depth_m: scene.floor.depthM,
      elements,
    },
  };
}

function normalizedFloorDimension(value, fallback) {
  return Math.max(1, rounded(finite(value, fallback), 3));
}

function requireCadCommand(scene, command) {
  if (!command.commandId) throw new Error("StoreScene commandId is required.");
  if (command.expectedRevision != null && Math.trunc(finite(command.expectedRevision, -1)) !== scene.revision) {
    throw new Error(`StoreScene revision conflict: expected ${command.expectedRevision}, found ${scene.revision}`);
  }
}

function patchedNode(current, patch = {}) {
  return createStoreSceneNode({
    ...current,
    ...patch,
    geometry: { ...current.geometry, ...(patch.geometry || {}) },
    provenance: patch.provenance || current.provenance,
    metadata: { ...current.metadata, ...(patch.metadata || {}) },
  });
}

function nodesEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function applyBatchUpdate(scene, command) {
  requireCadCommand(scene, command);
  const updates = Array.isArray(command.updates) ? command.updates : [];
  if (!updates.length) return { scene, command, inverseCommand: null, changed: false };
  if (updates.length > PLANOGRAM_CAD_BATCH_LIMIT) throw new Error(`CAD batch limit exceeded: ${updates.length}`);
  const ids = updates.map((row) => String(row?.nodeId || ""));
  if (ids.some((id) => !id) || new Set(ids).size !== ids.length) throw new Error("CAD batch node ids must be unique and non-empty.");
  const currentById = new Map(scene.nodes.map((node) => [node.nodeId, node]));
  const changed = [];
  for (const update of updates) {
    const current = currentById.get(update.nodeId);
    if (!current) throw new Error(`StoreScene node not found: ${update.nodeId}`);
    if (current.locked && command.force !== true) throw new Error(`StoreScene node is locked: ${current.nodeId}`);
    const next = patchedNode(current, update.patch || {});
    if (!nodesEqual(current, next)) changed.push({ current, next });
  }
  if (!changed.length) return { scene, command, inverseCommand: null, changed: false };
  const nextById = new Map(changed.map((row) => [row.next.nodeId, row.next]));
  const next = normalizeStoreScene({
    ...scene,
    revision: scene.revision + 1,
    nodes: scene.nodes.map((node) => nextById.get(node.nodeId) || node),
  });
  return {
    scene: next,
    command: { ...command, updates: changed.map((row) => ({ nodeId: row.next.nodeId, patch: updatePatchForNode(row.next) })) },
    inverseCommand: {
      commandId: `${command.commandId}:undo`,
      type: "UPDATE_NODES",
      updates: changed.map((row) => ({ nodeId: row.current.nodeId, patch: updatePatchForNode(row.current) })),
      force: true,
    },
    changed: true,
  };
}

function updatePatchForNode(node) {
  return {
    nodeType: node.nodeType,
    parentId: node.parentId,
    geometry: { ...node.geometry },
    locked: node.locked,
    provenance: node.provenance,
    metadata: node.metadata,
  };
}

function applyCadCommand(inputScene, rawCommand = {}) {
  const scene = normalizeStoreScene(inputScene);
  const command = { ...rawCommand, type: String(rawCommand.type || "").toUpperCase() };
  requireCadCommand(scene, command);

  if (command.type === "UPDATE_NODES") return applyBatchUpdate(scene, command);

  if (command.type === "RESIZE_FLOOR") {
    const widthM = normalizedFloorDimension(command.widthM, scene.floor.widthM);
    const depthM = normalizedFloorDimension(command.depthM, scene.floor.depthM);
    if (widthM === scene.floor.widthM && depthM === scene.floor.depthM) return { scene, command, inverseCommand: null, changed: false };
    const next = normalizeStoreScene({ ...scene, revision: scene.revision + 1, floor: { widthM, depthM } });
    return {
      scene: next,
      command: { ...command, widthM, depthM },
      inverseCommand: { commandId: `${command.commandId}:undo`, type: "RESIZE_FLOOR", widthM: scene.floor.widthM, depthM: scene.floor.depthM, force: true },
      changed: true,
    };
  }

  if (command.type === "UPDATE_NODE") {
    const current = scene.nodes.find((node) => node.nodeId === command.nodeId);
    if (!current) throw new Error(`StoreScene node not found: ${command.nodeId}`);
    if (current.locked && command.force !== true) throw new Error(`StoreScene node is locked: ${current.nodeId}`);
    if (nodesEqual(current, patchedNode(current, command.patch || {}))) return { scene, command, inverseCommand: null, changed: false };
  }

  if (command.type === "SET_LOCK") {
    const current = scene.nodes.find((node) => node.nodeId === command.nodeId);
    if (!current) throw new Error(`StoreScene node not found: ${command.nodeId}`);
    if (current.locked === Boolean(command.locked)) return { scene, command, inverseCommand: null, changed: false };
  }

  const applied = applyStoreSceneCommand(scene, command);
  return { ...applied, changed: true };
}

function sessionFromHistory(base, history) {
  const document = documentFromScene(base.document, history.present);
  const candidate = candidateWithPlanogramAuthoringDocument(base.candidate, document);
  return Object.freeze({
    ...base,
    candidate,
    document,
    history,
    scene: history.present,
    serializedScene: serializeStoreScene(history.present),
    diagnostics: diagnostics(history.present, base.minimumAisleM),
    historyDepth: history.past.length,
    redoDepth: history.future.length,
  });
}

export function createPlanogramCadSession({ candidate = null, reviewedResult = null, minimumAisleM = 1, sceneId = null } = {}) {
  const editableCandidate = reviewedResult ? candidateFromReviewedStoreScan(candidate, reviewedResult) : candidate;
  if (!editableCandidate) return null;
  const document = buildPlanogramAuthoringDocument(editableCandidate);
  if (!document) return null;
  const scene = buildStoreScene(editableCandidate, document, sceneId ? { sceneId } : {});
  if (!scene) return null;
  const sourceKind = reviewedResult ? "human_reviewed_store_scan" : "authored_store_scene";
  const base = Object.freeze({
    contract: PLANOGRAM_CAD_SESSION_CONTRACT,
    sourceKind,
    candidate: editableCandidate,
    document,
    minimumAisleM: Math.max(0.8, Number(minimumAisleM) || 1),
    previewOnly: Boolean(scene.previewOnly),
    geometryAuthority: scene.previewOnly ? "editable_preview_not_store_dna_authority" : "editable_store_scene",
    productionReleaseAllowed: false,
    physicalTruthAttested: false,
    reviewFingerprint: scene.provenance?.reviewFingerprint || null,
  });
  return sessionFromHistory(base, { past: [], present: scene, future: [] });
}

export function executePlanogramCadSessionCommand(session, command) {
  if (!session?.history || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT) return session;
  const applied = applyCadCommand(session.history.present, command);
  if (applied.changed === false) return session;
  return sessionFromHistory(session, {
    past: [...session.history.past, { command: applied.command, inverseCommand: applied.inverseCommand }],
    present: applied.scene,
    future: [],
  });
}

export function undoPlanogramCadSession(session) {
  if (!session?.history || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT || !session.history.past.length) return session;
  const entry = session.history.past[session.history.past.length - 1];
  const undone = applyCadCommand(session.history.present, { ...entry.inverseCommand, expectedRevision: undefined, force: true });
  if (undone.changed === false) return session;
  return sessionFromHistory(session, {
    past: session.history.past.slice(0, -1),
    present: undone.scene,
    future: [entry, ...session.history.future],
  });
}

export function redoPlanogramCadSession(session) {
  if (!session?.history || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT || !session.history.future.length) return session;
  const [entry, ...future] = session.history.future;
  const redone = applyCadCommand(session.history.present, { ...entry.command, expectedRevision: undefined, force: true });
  if (redone.changed === false) return session;
  return sessionFromHistory(session, {
    past: [...session.history.past, { command: redone.command, inverseCommand: redone.inverseCommand }],
    present: redone.scene,
    future,
  });
}
