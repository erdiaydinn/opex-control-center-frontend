import assert from "node:assert/strict";
import fs from "node:fs";

import { buildPlanogramUnifiedTwinScene } from "../src/modules/planogram/planogramUnifiedTwinScene.js";
import {
  buildPlanogramWalkthroughNavigation,
  isPlanogramWalkthroughPositionBlocked,
  resolvePlanogramWalkthroughStep,
} from "../src/modules/planogram/planogramWalkthroughNavigation.js";
import {
  buildPlanogramWallPassageModel,
  PLANOGRAM_WALL_PASSAGE_CONTRACT,
} from "../src/modules/planogram/planogramWallPassages.js";

const wall = {
  id: "WALL-DOOR",
  type: "wall",
  centerXM: 5,
  centerYM: 4,
  widthM: 6,
  depthM: 0.12,
  heightM: 2.7,
  rotationDeg: 0,
  coordinateAuthority: "measured",
};
const door = {
  id: "DOOR-1",
  type: "door",
  centerXM: 5,
  centerYM: 4,
  widthM: 1.4,
  depthM: 0.12,
  heightM: 2.1,
  rotationDeg: 0,
  parentId: "WALL-DOOR",
  hostConstraint: "wall_centerline_v1",
  coordinateAuthority: "measured",
};
const windowWall = {
  id: "WALL-WINDOW",
  type: "wall",
  centerXM: 5,
  centerYM: 2,
  widthM: 6,
  depthM: 0.12,
  heightM: 2.7,
  rotationDeg: 0,
  coordinateAuthority: "measured",
};
const window = {
  id: "WINDOW-1",
  type: "window",
  centerXM: 5,
  centerYM: 2,
  widthM: 1.4,
  depthM: 0.12,
  heightM: 1.2,
  rotationDeg: 0,
  parentId: "WALL-WINDOW",
  hostConstraint: "wall_centerline_v1",
  coordinateAuthority: "measured",
};

const passage = buildPlanogramWallPassageModel([wall, door, windowWall, window]);
assert.equal(passage.contract, PLANOGRAM_WALL_PASSAGE_CONTRACT);
assert.equal(passage.productionReleaseAllowed, false);
assert.equal(passage.storeDnaAuthority, false);
assert.equal(passage.passageCount, 1, "Only door/emergency-exit may open walk-through passage.");
assert.equal(passage.segmentedWallCount, 1);
assert.equal(passage.invalidPassageCount, 0);
assert.ok(!passage.renderArchitecture.some((row) => row.id === "WALL-DOOR"), "Hosted door must replace the full wall with derived side segments.");
assert.ok(passage.renderArchitecture.some((row) => row.sourceWallId === "WALL-DOOR" && row.derivedPassageSegment));
assert.ok(passage.renderArchitecture.some((row) => row.type === "door_passage" && row.passable));
assert.ok(passage.renderArchitecture.some((row) => row.id === "WALL-WINDOW"), "Window must not create a passable wall gap without vertical/elevation authority.");

const scene = {
  floor: { widthM: 10, depthM: 8 },
  geometryAuthority: "measured-preview-v2",
  sourceKind: "authored_planogram",
  architecture: passage.renderArchitecture,
  navigationArchitecture: passage.navigationArchitecture,
  fixtures: [],
};
const navigation = buildPlanogramWalkthroughNavigation(scene, { radiusM: 0.3 });
assert.ok(navigation);
assert.equal(isPlanogramWalkthroughPositionBlocked(navigation, { x: 5, y: 4 }), false, "Door center must be traversable.");
assert.equal(isPlanogramWalkthroughPositionBlocked(navigation, { x: 3.3, y: 4 }), true, "Remaining wall segment must still block traversal.");
assert.equal(isPlanogramWalkthroughPositionBlocked(navigation, { x: 5, y: 2 }), true, "Window host wall must remain blocking.");
const crossing = resolvePlanogramWalkthroughStep(
  navigation,
  { x: 5, y: 3.5 },
  { x: 0, y: 1 },
);
assert.equal(crossing.position.x, 5);
assert.ok(crossing.position.y > 4, "Walk-through step should cross the hosted door opening.");
assert.equal(crossing.reason, "clear");

const invalidDoor = { ...door, id: "DOOR-BAD", rotationDeg: 25 };
const failClosed = buildPlanogramWallPassageModel([wall, invalidDoor]);
assert.equal(failClosed.passageCount, 0);
assert.equal(failClosed.invalidPassageCount, 1);
assert.ok(failClosed.renderArchitecture.some((row) => row.id === "WALL-DOOR"), "Invalid host relation must retain the full blocking wall.");
assert.equal(failClosed.diagnostics[0].failClosed, true);

const authoredModel = {
  contract: "planogram-digital-twin-v1",
  geometryAuthority: "measured-preview-v2",
  engineGeometryAuthority: "measured-preview-v2",
  architectureSourceRef: "cad-passage-test:v1",
  floor: { widthM: 10, depthM: 8 },
  modules: [],
  cadFixtures: [],
  elements: [wall, door, windowWall, window],
  route: null,
  cadOverlay: { contract: "eay.planogram.cad-overlay.v1", rejected: false },
};
const authoringCandidate = {
  store_dna: {
    architecture: {
      elements: [
        { element_id: "WALL-DOOR" },
        {
          element_id: "DOOR-1",
          parent_id: "WALL-DOOR",
          host_constraint: "wall_centerline_v1",
          host_offset_m: 0,
          cad_layer: "architecture",
        },
        { element_id: "WALL-WINDOW" },
        {
          element_id: "WINDOW-1",
          parent_id: "WALL-WINDOW",
          host_constraint: "wall_centerline_v1",
          host_offset_m: 0,
          cad_layer: "architecture",
        },
      ],
    },
  },
};
const unified = buildPlanogramUnifiedTwinScene({ authoredModel, authoringCandidate });
assert.ok(unified);
assert.equal(unified.productionReleaseAllowed, false);
assert.equal(unified.wallPassages.contract, PLANOGRAM_WALL_PASSAGE_CONTRACT);
assert.equal(unified.wallPassages.passageCount, 1);
assert.ok(unified.sourceArchitecture.some((row) => row.id === "DOOR-1" && row.parentId === "WALL-DOOR"));
assert.ok(unified.architecture.some((row) => row.type === "door_passage"));
assert.ok(!unified.architecture.some((row) => row.id === "WALL-DOOR"));

const digitalTwin = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
for (const needle of [
  "authoringCandidate: candidate",
  "data-wall-passage-contract",
  "data-passable-opening-count",
]) {
  if (!digitalTwin.includes(needle)) throw new Error(`Digital Twin passage wiring missing: ${needle}`);
}
const unifiedSource = fs.readFileSync("src/modules/planogram/planogramUnifiedTwinScene.js", "utf8");
for (const needle of [
  "sourceArchitecture",
  "buildPlanogramWallPassageModel",
  "wallPassages.renderArchitecture",
  "wallPassages.navigationArchitecture",
]) {
  if (!unifiedSource.includes(needle)) throw new Error(`Unified Twin passage contract missing: ${needle}`);
}
const renderer = fs.readFileSync("src/modules/planogram/PlanogramTwinSceneRenderer.jsx", "utf8");
const walkthrough = fs.readFileSync("src/modules/planogram/PlanogramFirstPersonWalkthrough.jsx", "utf8");
for (const source of [renderer, walkthrough]) {
  if (!source.includes("sceneModel.architecture")) {
    throw new Error("Shared 3D runtime no longer consumes the unified architecture surface.");
  }
}

console.log("Planogram Sprint 3 hosted wall passages + walk-through passability: PASS");
