import { createStoreSceneNode, normalizeStoreScene } from "./planogramAuthoringModel.js";

export const PLANOGRAM_CAD_CONSTRAINT_CONTRACT = "eay.planogram.cad-constraints.v1";
export const PLANOGRAM_CAD_HOST_CONSTRAINT = "wall_centerline_v1";
export const PLANOGRAM_CAD_HOSTED_OPENING_TYPES = Object.freeze([
  "door",
  "window",
  "emergency_exit",
]);
export const PLANOGRAM_CAD_LAYER_IDS = Object.freeze([
  "architecture",
  "equipment",
  "operations",
  "annotations",
]);

const HOSTED_OPENING_TYPES = new Set(PLANOGRAM_CAD_HOSTED_OPENING_TYPES);
const LAYER_TYPES = Object.freeze({
  architecture: new Set(["wall", "door", "window", "column", "emergency_exit"]),
  equipment: new Set(["fixture"]),
  operations: new Set([
    "no_go",
    "technical",
    "inbound",
    "dispatch",
    "picker_entry",
    "picker_exit",
  ]),
  annotations: new Set(["measurement", "annotation"]),
});
const EPSILON = 1e-9;
const DEFAULT_HOST_DISTANCE_M = 0.75;
const HOST_TOLERANCE_M = 0.02;
const ROTATION_TOLERANCE_DEG = 0.1;

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

function normalizedRotation(value) {
  let rotation = finite(value) % 360;
  if (rotation > 180) rotation -= 360;
  if (rotation <= -180) rotation += 360;
  return rounded(rotation, 2);
}

function rotationDelta(left, right) {
  return Math.abs(normalizedRotation(finite(left) - finite(right)));
}

function wallAxes(wall) {
  const angle = finite(wall?.geometry?.rotationDeg) * Math.PI / 180;
  return {
    tangent: { x: Math.cos(angle), y: Math.sin(angle) },
    normal: { x: -Math.sin(angle), y: Math.cos(angle) },
  };
}

function localCoordinates(wall, centerXM, centerYM) {
  const { tangent, normal } = wallAxes(wall);
  const dx = finite(centerXM) - finite(wall?.geometry?.centerXM);
  const dy = finite(centerYM) - finite(wall?.geometry?.centerYM);
  return {
    alongM: dx * tangent.x + dy * tangent.y,
    normalM: dx * normal.x + dy * normal.y,
  };
}

function centerAtOffset(wall, offsetM) {
  const { tangent } = wallAxes(wall);
  return {
    centerXM: rounded(finite(wall.geometry.centerXM) + tangent.x * offsetM),
    centerYM: rounded(finite(wall.geometry.centerYM) + tangent.y * offsetM),
  };
}

function openingFitsWall(opening, wall) {
  return finite(opening?.geometry?.widthM) <= finite(wall?.geometry?.widthM) + EPSILON;
}

function maximumHostOffset(opening, wall) {
  if (!openingFitsWall(opening, wall)) {
    throw new Error(`Hosted opening exceeds wall span: ${opening?.nodeId || "unknown"}`);
  }
  return Math.max(
    0,
    (finite(wall.geometry.widthM) - finite(opening.geometry.widthM)) / 2,
  );
}

function clampHostOffset(opening, wall, requestedOffsetM) {
  const maxOffset = maximumHostOffset(opening, wall);
  return rounded(Math.max(-maxOffset, Math.min(maxOffset, finite(requestedOffsetM))));
}

function nodeById(scene, nodeId) {
  return scene.nodes.find((node) => node.nodeId === nodeId) || null;
}

function wallById(scene, wallId) {
  const wall = nodeById(scene, wallId);
  return wall?.nodeType === "wall" ? wall : null;
}

function proposedNode(current, patch = {}) {
  return createStoreSceneNode({
    ...current,
    ...patch,
    geometry: { ...current.geometry, ...(patch.geometry || {}) },
    provenance: patch.provenance || current.provenance,
    metadata: { ...current.metadata, ...(patch.metadata || {}) },
  });
}

function hostPatch(opening, wall, requestedCenter = null) {
  if (!HOSTED_OPENING_TYPES.has(opening.nodeType)) {
    throw new Error(`Node is not a hostable opening: ${opening.nodeId}`);
  }
  if (!wall || wall.nodeType !== "wall") {
    throw new Error(`Hosted opening requires a wall: ${opening.nodeId}`);
  }
  const centerXM = requestedCenter?.centerXM ?? opening.geometry.centerXM;
  const centerYM = requestedCenter?.centerYM ?? opening.geometry.centerYM;
  const local = localCoordinates(wall, centerXM, centerYM);
  const offsetM = clampHostOffset(opening, wall, local.alongM);
  const center = centerAtOffset(wall, offsetM);
  return Object.freeze({
    parentId: wall.nodeId,
    geometry: Object.freeze({
      centerXM: center.centerXM,
      centerYM: center.centerYM,
      depthM: rounded(wall.geometry.depthM),
      rotationDeg: rounded(wall.geometry.rotationDeg, 2),
    }),
    metadata: Object.freeze({
      ...(opening.metadata || {}),
      cadLayer: "architecture",
      hostConstraint: PLANOGRAM_CAD_HOST_CONSTRAINT,
      hostWallId: wall.nodeId,
      hostOffsetM: offsetM,
      productionReleaseAllowed: false,
    }),
  });
}

function wallDistanceScore(opening, wall) {
  if (!openingFitsWall(opening, wall)) return Number.POSITIVE_INFINITY;
  const local = localCoordinates(
    wall,
    opening.geometry.centerXM,
    opening.geometry.centerYM,
  );
  const halfWall = finite(wall.geometry.widthM) / 2;
  const spanExcessM = Math.max(0, Math.abs(local.alongM) - halfWall);
  return Math.hypot(local.normalM, spanExcessM);
}

function nearestWall(scene, opening, maxDistanceM = DEFAULT_HOST_DISTANCE_M) {
  const candidates = scene.nodes
    .filter((node) => node.nodeType === "wall")
    .map((wall) => ({ wall, distanceM: wallDistanceScore(opening, wall) }))
    .filter((row) => Number.isFinite(row.distanceM) && row.distanceM <= maxDistanceM + EPSILON)
    .sort((left, right) => left.distanceM - right.distanceM || left.wall.nodeId.localeCompare(right.wall.nodeId));
  return candidates[0]?.wall || null;
}

function descendantNodes(scene, parentId) {
  const ids = new Set([parentId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const node of scene.nodes) {
      if (node.parentId && ids.has(node.parentId) && !ids.has(node.nodeId)) {
        ids.add(node.nodeId);
        changed = true;
      }
    }
  }
  ids.delete(parentId);
  return scene.nodes.filter((node) => ids.has(node.nodeId));
}

function patchRequestsHost(patch = {}) {
  return Boolean(text(patch.parentId || patch.parent_id || patch.metadata?.hostWallId));
}

export function planogramCadLayerForNode(node) {
  const type = text(node?.nodeType || node?.node_type || node?.element_type).toLowerCase();
  for (const layerId of PLANOGRAM_CAD_LAYER_IDS) {
    if (LAYER_TYPES[layerId].has(type)) return layerId;
  }
  return "annotations";
}

export function buildPlanogramCadLayerModel(inputScene, overrides = {}) {
  const scene = normalizeStoreScene(inputScene);
  const layers = PLANOGRAM_CAD_LAYER_IDS.map((layerId) => {
    const nodes = scene.nodes.filter((node) => planogramCadLayerForNode(node) === layerId);
    const override = overrides?.[layerId] || {};
    return Object.freeze({
      layerId,
      visible: override.visible !== false,
      locked: override.locked === true,
      count: nodes.length,
      nodeIds: Object.freeze(nodes.map((node) => node.nodeId)),
      workspaceOnly: true,
      productionAuthority: false,
    });
  });
  return Object.freeze({
    contract: PLANOGRAM_CAD_CONSTRAINT_CONTRACT,
    layers: Object.freeze(layers),
    productionReleaseAllowed: false,
    storeDnaAuthority: false,
  });
}

export function hydratePlanogramCadRelationships(inputScene, document) {
  const scene = normalizeStoreScene(inputScene);
  const byId = new Map(
    (document?.architecture?.elements || []).map((row) => [String(row?.element_id || ""), row]),
  );
  const nodes = scene.nodes.map((node) => {
    const row = byId.get(node.nodeId);
    if (!row) return node;
    const parentId = text(row.parent_id || row.host_wall_id) || node.parentId || null;
    const metadata = {
      ...(node.metadata || {}),
      cadLayer: text(row.cad_layer) || planogramCadLayerForNode(node),
    };
    if (text(row.host_constraint)) metadata.hostConstraint = text(row.host_constraint);
    if (row.host_offset_m != null && Number.isFinite(Number(row.host_offset_m))) {
      metadata.hostOffsetM = rounded(row.host_offset_m);
    }
    if (parentId) metadata.hostWallId = parentId;
    return createStoreSceneNode({ ...node, parentId, metadata });
  });
  return normalizeStoreScene({ ...scene, nodes });
}

export function buildPlanogramCadHostOpeningPatch(
  inputScene,
  nodeId,
  wallId = null,
  options = {},
) {
  const scene = normalizeStoreScene(inputScene);
  const opening = nodeById(scene, nodeId);
  if (!opening || !HOSTED_OPENING_TYPES.has(opening.nodeType)) {
    throw new Error(`Hostable CAD opening not found: ${nodeId}`);
  }
  const wall = wallId
    ? wallById(scene, wallId)
    : nearestWall(
        scene,
        opening,
        Math.max(0.05, finite(options.maxDistanceM, DEFAULT_HOST_DISTANCE_M)),
      );
  if (!wall) throw new Error(`No eligible wall host found for opening: ${nodeId}`);
  return hostPatch(opening, wall);
}

function constrainedOpeningUpdate(scene, current, patch, wallOverride = null) {
  const proposed = proposedNode(current, patch);
  const hostId = text(proposed.parentId || proposed.metadata?.hostWallId || current.parentId);
  if (!hostId) return patch;
  const wall = wallOverride || wallById(scene, hostId);
  if (!wall) throw new Error(`Hosted opening wall is unavailable: ${current.nodeId}`);
  const constrained = hostPatch(proposed, wall, proposed.geometry);
  return {
    ...patch,
    parentId: constrained.parentId,
    geometry: { ...(patch.geometry || {}), ...constrained.geometry },
    metadata: { ...(patch.metadata || {}), ...constrained.metadata },
  };
}

function cascadeWallUpdate(scene, wallCurrent, wallPatch, explicitUpdates = new Map()) {
  const wallProposed = proposedNode(wallCurrent, wallPatch);
  const updates = new Map();
  updates.set(wallCurrent.nodeId, { nodeId: wallCurrent.nodeId, patch: wallPatch });
  for (const child of scene.nodes.filter(
    (node) => node.parentId === wallCurrent.nodeId && HOSTED_OPENING_TYPES.has(node.nodeType),
  )) {
    if (child.locked) throw new Error(`Hosted opening is locked: ${child.nodeId}`);
    const explicit = explicitUpdates.get(child.nodeId)?.patch || {};
    const proposedChild = proposedNode(child, explicit);
    const storedOffset = Number(proposedChild.metadata?.hostOffsetM);
    const requestedCenter = Number.isFinite(storedOffset)
      ? centerAtOffset(wallProposed, storedOffset)
      : proposedChild.geometry;
    const constrained = hostPatch(proposedChild, wallProposed, requestedCenter);
    updates.set(child.nodeId, {
      nodeId: child.nodeId,
      patch: {
        ...explicit,
        parentId: constrained.parentId,
        geometry: { ...(explicit.geometry || {}), ...constrained.geometry },
        metadata: { ...(explicit.metadata || {}), ...constrained.metadata },
      },
    });
  }
  return updates;
}

export function constrainPlanogramCadCommand(inputScene, rawCommand = {}) {
  const scene = normalizeStoreScene(inputScene);
  const command = { ...rawCommand, type: text(rawCommand.type).toUpperCase() };
  if (command.force === true) return command;

  if (command.type === "CREATE_NODE") {
    let node = createStoreSceneNode(command.node);
    if (HOSTED_OPENING_TYPES.has(node.nodeType)) {
      const requestedWallId = text(node.parentId || node.metadata?.hostWallId);
      const wall = requestedWallId
        ? wallById(scene, requestedWallId)
        : nearestWall(scene, node, DEFAULT_HOST_DISTANCE_M);
      if (!wall) throw new Error(`Opening placement requires a nearby wall: ${node.nodeId}`);
      node = proposedNode(node, hostPatch(node, wall));
    } else {
      node = proposedNode(node, {
        metadata: { ...(node.metadata || {}), cadLayer: planogramCadLayerForNode(node) },
      });
    }
    return { ...command, node };
  }

  if (command.type === "UPDATE_NODE") {
    const current = nodeById(scene, command.nodeId);
    if (!current) return command;
    if (current.nodeType === "wall") {
      const cascaded = cascadeWallUpdate(scene, current, command.patch || {});
      return { ...command, type: "UPDATE_NODES", updates: [...cascaded.values()] };
    }
    if (
      HOSTED_OPENING_TYPES.has(current.nodeType)
      && (current.parentId || patchRequestsHost(command.patch || {}))
    ) {
      return {
        ...command,
        patch: constrainedOpeningUpdate(scene, current, command.patch || {}),
      };
    }
    return command;
  }

  if (command.type === "UPDATE_NODES") {
    const rawUpdates = Array.isArray(command.updates) ? command.updates : [];
    const explicit = new Map(rawUpdates.map((row) => [text(row?.nodeId), row]));
    const output = new Map();
    const proposedWalls = new Map();

    for (const row of rawUpdates) {
      const current = nodeById(scene, row.nodeId);
      if (!current) continue;
      if (current.nodeType === "wall") {
        proposedWalls.set(current.nodeId, proposedNode(current, row.patch || {}));
        const cascaded = cascadeWallUpdate(scene, current, row.patch || {}, explicit);
        for (const [id, update] of cascaded) output.set(id, update);
      }
    }

    for (const row of rawUpdates) {
      const current = nodeById(scene, row.nodeId);
      if (!current || current.nodeType === "wall") continue;
      let patch = row.patch || {};
      const requestedHost = text(
        patch.parentId || patch.parent_id || patch.metadata?.hostWallId || current.parentId,
      );
      if (HOSTED_OPENING_TYPES.has(current.nodeType) && requestedHost) {
        patch = constrainedOpeningUpdate(
          scene,
          current,
          patch,
          proposedWalls.get(requestedHost) || null,
        );
      }
      output.set(current.nodeId, { nodeId: current.nodeId, patch });
    }
    return { ...command, updates: [...output.values()] };
  }

  if (command.type === "DELETE_NODE") {
    const current = nodeById(scene, command.nodeId);
    if (current?.nodeType === "wall") {
      const locked = descendantNodes(scene, current.nodeId).find((node) => node.locked);
      if (locked) throw new Error(`Cannot delete wall with locked hosted child: ${locked.nodeId}`);
    }
  }

  return command;
}

export function findPlanogramCadConstraintViolations(inputScene) {
  const scene = normalizeStoreScene(inputScene);
  const violations = [];
  for (const opening of scene.nodes.filter((node) => HOSTED_OPENING_TYPES.has(node.nodeType))) {
    if (!opening.parentId) {
      violations.push({ nodeId: opening.nodeId, reason: "unhosted_opening", hostWallId: null });
      continue;
    }
    const wall = wallById(scene, opening.parentId);
    if (!wall) {
      violations.push({
        nodeId: opening.nodeId,
        reason: "invalid_wall_host",
        hostWallId: opening.parentId,
      });
      continue;
    }
    if (!openingFitsWall(opening, wall)) {
      violations.push({
        nodeId: opening.nodeId,
        reason: "host_span_violation",
        hostWallId: wall.nodeId,
      });
      continue;
    }
    const local = localCoordinates(wall, opening.geometry.centerXM, opening.geometry.centerYM);
    const maxOffset = maximumHostOffset(opening, wall);
    if (Math.abs(local.normalM) > HOST_TOLERANCE_M) {
      violations.push({
        nodeId: opening.nodeId,
        reason: "off_wall_centerline",
        hostWallId: wall.nodeId,
      });
    }
    if (Math.abs(local.alongM) > maxOffset + HOST_TOLERANCE_M) {
      violations.push({
        nodeId: opening.nodeId,
        reason: "host_span_violation",
        hostWallId: wall.nodeId,
      });
    }
    if (
      rotationDelta(opening.geometry.rotationDeg, wall.geometry.rotationDeg)
      > ROTATION_TOLERANCE_DEG
    ) {
      violations.push({
        nodeId: opening.nodeId,
        reason: "host_rotation_mismatch",
        hostWallId: wall.nodeId,
      });
    }
    if (
      Math.abs(finite(opening.geometry.depthM) - finite(wall.geometry.depthM))
      > HOST_TOLERANCE_M
    ) {
      violations.push({
        nodeId: opening.nodeId,
        reason: "host_depth_mismatch",
        hostWallId: wall.nodeId,
      });
    }
  }
  return Object.freeze(violations.map((row) => Object.freeze(row)));
}
