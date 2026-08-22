import assert from "node:assert/strict";
import fs from "node:fs";

import {
  buildPlanogramCadHostOpeningPatch,
  buildPlanogramCadLayerModel,
  findPlanogramCadConstraintViolations,
  PLANOGRAM_CAD_HOST_CONSTRAINT,
  planogramCadLayerForNode,
} from "../src/modules/planogram/planogramCadConstraints.js";
import {
  createPlanogramCadSession,
  executePlanogramCadSessionCommand,
  undoPlanogramCadSession,
} from "../src/modules/planogram/planogramCadSession.js";
import {
  createStoreSceneNode,
  projectStoreScene2D,
  projectStoreScene3D,
} from "../src/modules/planogram/planogramAuthoringModel.js";

function candidate(elements) {
  return {
    store_code: "CAD-CONSTRAINT-STORE",
    store_dna: {
      store_code: "CAD-CONSTRAINT-STORE",
      architecture: {
        schema_version: 2,
        coordinate_system: "cartesian_m_centered_rect",
        source: "manual_survey",
        source_ref: "cad-constraint-test:v1",
        floor_width_m: 12,
        floor_depth_m: 8,
        elements,
      },
    },
  };
}

function wallElement() {
  return {
    element_id: "WALL-1",
    element_type: "wall",
    center_x_m: 6,
    center_y_m: 4,
    width_m: 6,
    depth_m: 0.12,
    height_m: 2.8,
    rotation_deg: 30,
    clearance_m: 0,
  };
}

function command(session, body) {
  return executePlanogramCadSessionCommand(session, {
    commandId: body.commandId,
    expectedRevision: session.scene.revision,
    ...body,
  });
}

function byId(session, nodeId) {
  return session.scene.nodes.find((node) => node.nodeId === nodeId);
}

let session = createPlanogramCadSession({ candidate: candidate([wallElement()]) });
assert.ok(session, "CAD session should build from measured architecture.");
assert.equal(session.productionReleaseAllowed, false);
assert.equal(session.physicalTruthAttested, false);

const looseDoor = createStoreSceneNode({
  nodeId: "DOOR-1",
  nodeType: "door",
  geometry: {
    centerXM: 6.2,
    centerYM: 4.25,
    widthM: 0.9,
    depthM: 0.2,
    heightM: 2.1,
    rotationDeg: 0,
  },
  provenance: { source: "human", sourceRef: "cad-constraint-test" },
});
session = command(session, {
  commandId: "CREATE-DOOR",
  type: "CREATE_NODE",
  node: looseDoor,
});
let door = byId(session, "DOOR-1");
assert.equal(door.parentId, "WALL-1");
assert.equal(door.metadata.hostConstraint, PLANOGRAM_CAD_HOST_CONSTRAINT);
assert.equal(door.metadata.hostWallId, "WALL-1");
assert.equal(door.metadata.cadLayer, "architecture");
assert.equal(door.geometry.rotationDeg, 30);
assert.equal(door.geometry.depthM, 0.12);
assert.equal(findPlanogramCadConstraintViolations(session.scene).length, 0);

const roundTrip = createPlanogramCadSession({ candidate: session.candidate });
const roundTripDoor = byId(roundTrip, "DOOR-1");
assert.equal(roundTripDoor.parentId, "WALL-1", "Hosted parent must survive candidate round-trip.");
assert.equal(roundTripDoor.metadata.hostConstraint, PLANOGRAM_CAD_HOST_CONSTRAINT);
assert.equal(roundTripDoor.metadata.hostWallId, "WALL-1");
assert.ok(Number.isFinite(Number(roundTripDoor.metadata.hostOffsetM)));

session = command(session, {
  commandId: "MOVE-DOOR-OFF-WALL",
  type: "UPDATE_NODE",
  nodeId: "DOOR-1",
  patch: { geometry: { centerXM: 10.8, centerYM: 7.2, rotationDeg: -80, depthM: 1 } },
});
door = byId(session, "DOOR-1");
assert.equal(door.parentId, "WALL-1");
assert.equal(door.geometry.rotationDeg, 30, "Hosted opening rotation must follow its wall.");
assert.equal(door.geometry.depthM, 0.12, "Hosted opening depth must follow wall thickness.");
assert.equal(findPlanogramCadConstraintViolations(session.scene).length, 0);

const beforeWallMoveRevision = session.scene.revision;
session = command(session, {
  commandId: "MOVE-WALL",
  type: "UPDATE_NODE",
  nodeId: "WALL-1",
  patch: { geometry: { centerXM: 7, centerYM: 4.5, rotationDeg: 55 } },
});
assert.equal(session.scene.revision, beforeWallMoveRevision + 1, "Wall + hosted children must move in one revision.");
const movedWall = byId(session, "WALL-1");
door = byId(session, "DOOR-1");
assert.equal(movedWall.geometry.rotationDeg, 55);
assert.equal(door.geometry.rotationDeg, 55);
assert.equal(door.parentId, "WALL-1");
assert.equal(findPlanogramCadConstraintViolations(session.scene).length, 0);

session = command(session, {
  commandId: "LOCK-DOOR",
  type: "SET_LOCK",
  nodeId: "DOOR-1",
  locked: true,
});
assert.throws(
  () => command(session, {
    commandId: "MOVE-WALL-WITH-LOCKED-CHILD",
    type: "UPDATE_NODE",
    nodeId: "WALL-1",
    patch: { geometry: { centerXM: 7.5 } },
  }),
  /Hosted opening is locked/,
);
assert.throws(
  () => command(session, {
    commandId: "DELETE-WALL-WITH-LOCKED-CHILD",
    type: "DELETE_NODE",
    nodeId: "WALL-1",
  }),
  /locked hosted child/,
);

session = command(session, {
  commandId: "UNLOCK-DOOR",
  type: "SET_LOCK",
  nodeId: "DOOR-1",
  locked: false,
});
const beforeDelete = session;
session = command(session, {
  commandId: "DELETE-WALL",
  type: "DELETE_NODE",
  nodeId: "WALL-1",
});
assert.equal(byId(session, "WALL-1"), undefined);
assert.equal(byId(session, "DOOR-1"), undefined, "Deleting a wall must not leave an orphan hosted opening.");
session = undoPlanogramCadSession(session);
assert.ok(byId(session, "WALL-1"));
assert.ok(byId(session, "DOOR-1"));
assert.equal(byId(session, "DOOR-1").parentId, "WALL-1");
assert.equal(session.historyDepth, beforeDelete.historyDepth);

const unhostedCandidate = candidate([
  wallElement(),
  {
    element_id: "SCAN-DOOR-UNHOSTED",
    element_type: "door",
    center_x_m: 5.5,
    center_y_m: 4.1,
    width_m: 0.9,
    depth_m: 0.12,
    height_m: 2.1,
    rotation_deg: 30,
    scan_source_element_id: "SCAN-DOOR-UNHOSTED",
  },
]);
let unhostedSession = createPlanogramCadSession({ candidate: unhostedCandidate });
assert.ok(
  unhostedSession.diagnostics.constraintViolations.some(
    (row) => row.nodeId === "SCAN-DOOR-UNHOSTED" && row.reason === "unhosted_opening",
  ),
  "Existing scan openings must be diagnosed instead of silently rehosted.",
);
const attachPatch = buildPlanogramCadHostOpeningPatch(
  unhostedSession.scene,
  "SCAN-DOOR-UNHOSTED",
);
unhostedSession = command(unhostedSession, {
  commandId: "REHOST-SCAN-DOOR",
  type: "UPDATE_NODE",
  nodeId: "SCAN-DOOR-UNHOSTED",
  patch: attachPatch,
});
assert.equal(byId(unhostedSession, "SCAN-DOOR-UNHOSTED").parentId, "WALL-1");
assert.equal(unhostedSession.diagnostics.constraintViolationCount, 0);

const layerModel = buildPlanogramCadLayerModel(unhostedSession.scene, {
  equipment: { visible: false, locked: true },
});
const architectureLayer = layerModel.layers.find((row) => row.layerId === "architecture");
const equipmentLayer = layerModel.layers.find((row) => row.layerId === "equipment");
assert.ok(architectureLayer.count >= 2);
assert.equal(equipmentLayer.visible, false);
assert.equal(equipmentLayer.locked, true);
assert.equal(layerModel.productionReleaseAllowed, false);
assert.equal(layerModel.storeDnaAuthority, false);
assert.equal(planogramCadLayerForNode(byId(unhostedSession, "WALL-1")), "architecture");
assert.equal(byId(unhostedSession, "WALL-1").locked, false, "Workspace layer lock must not mutate StoreScene node authority.");

const projection2D = projectStoreScene2D(unhostedSession.scene);
const projection3D = projectStoreScene3D(unhostedSession.scene);
const twoDoor = projection2D.nodes.find((node) => node.nodeId === "SCAN-DOOR-UNHOSTED");
const threeDoor = projection3D.nodes.find((node) => node.nodeId === "SCAN-DOOR-UNHOSTED");
assert.equal(twoDoor.parentId, threeDoor.parentId);
assert.deepEqual(twoDoor.geometry, threeDoor.geometry, "2D and 3D must project identical hosted geometry.");

const ui = fs.readFileSync("src/modules/planogram/PlanogramArchitecturalAuthoring.jsx", "utf8");
for (const needle of [
  "PlanogramCadLayersPanel",
  "buildPlanogramCadLayerModel",
  "data-cad-layer",
  "constraintViolationCount",
  "attachNearestWall",
]) {
  if (!ui.includes(needle)) throw new Error(`CAD constraint UI wiring missing: ${needle}`);
}

console.log("Planogram Sprint 3 CAD layers + hosted-opening constraints: PASS");
