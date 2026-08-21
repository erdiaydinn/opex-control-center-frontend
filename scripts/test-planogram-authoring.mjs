import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_AUTHORING_MESSAGES } from "../src/platform/i18n/planogramAuthoringMessages.js";
import {
  applyOptimizerStoreSceneSuggestions,
  applyStoreSceneCommand,
  buildPlanogramAuthoringDocument,
  buildStoreScene,
  candidateFromReviewedStoreScan,
  candidateWithPlanogramAuthoringDocument,
  createPlanogramAuthoringElement,
  createStoreSceneHistory,
  createStoreSceneNode,
  deserializeStoreScene,
  executeStoreSceneCommand,
  findStoreSceneAisleViolations,
  findStoreSceneCollisions,
  PLANOGRAM_AUTHORING_CONTRACT,
  PLANOGRAM_STORE_SCENE_CONTRACT,
  projectStoreScene2D,
  projectStoreScene3D,
  redoStoreSceneCommand,
  removePlanogramAuthoringElement,
  resizePlanogramAuthoringFloor,
  serializeStoreScene,
  snapStoreSceneCoordinate,
  undoStoreSceneCommand,
  updatePlanogramAuthoringElement,
} from "../src/modules/planogram/planogramAuthoringModel.js";

function fail(message) { console.error(message); process.exit(1); }
function pass(id, message) { console.log(`${id}=PASS ${message}`); }

const candidate = {
  store_code: "STORE-1",
  products: [],
  layout: { aisles: [] },
  mode: "HYBRID",
  store_dna: {
    architecture: {
      schema_version: 2,
      coordinate_system: "cartesian_m_centered_rect",
      source: "e57_semantic_scan",
      source_ref: "scan://STORE-1/e57",
      source_review_fingerprint: "abc123",
      floor_width_m: 12,
      floor_depth_m: 8,
      elements: [
        {
          element_id: "SCAN-WALL-1",
          element_type: "wall",
          center_x_m: 3,
          center_y_m: 2,
          width_m: 2.4,
          depth_m: 0.12,
          rotation_deg: 17,
          scan_confidence: 0.98,
          scan_source_element_id: "E57-101",
        },
      ],
    },
  },
};

let document = buildPlanogramAuthoringDocument(candidate);
if (!document || document.contract !== PLANOGRAM_AUTHORING_CONTRACT) fail("Authoring document contract missing.");
if (!document.previewOnly || document.sourceContract !== "store-architecture-v2-oriented-polygons") fail("V2 scan draft authority was promoted incorrectly.");
if (document.architecture.elements[0].rotation_deg !== 17) fail("Arbitrary-angle scan geometry was snapped.");

const created = createPlanogramAuthoringElement({ type: "wall", centerXM: 4.123, centerYM: 5.177, floor: document.floor, sequence: 7, gridM: document.gridM });
if (created.center_x_m !== 4.1 || created.center_y_m !== 5.2) fail("Metric authoring grid snap drifted.");
document = { ...document, architecture: { ...document.architecture, elements: [...document.architecture.elements, created] } };

document = updatePlanogramAuthoringElement(document, "SCAN-WALL-1", { center_x_m: 6.13, rotation_deg: 33, width_m: 3.17 });
const editedScanWall = document.architecture.elements.find((row) => row.element_id === "SCAN-WALL-1");
if (editedScanWall.center_x_m !== 6.15 || editedScanWall.rotation_deg !== 33 || editedScanWall.width_m !== 3.15) fail("Exact authoring edits or snap drifted.");
if (editedScanWall.scan_confidence !== 0.98 || editedScanWall.scan_source_element_id !== "E57-101") fail("Scan provenance was lost during editing.");

document = resizePlanogramAuthoringFloor(document, 10.02, 7.98);
if (document.floor.widthM !== 10 || document.floor.depthM !== 8) fail("Floor metric resize drifted.");
document = removePlanogramAuthoringElement(document, created.element_id);
if (document.architecture.elements.some((row) => row.element_id === created.element_id)) fail("Authoring delete failed.");

const authoredCandidate = candidateWithPlanogramAuthoringDocument(candidate, document);
if (authoredCandidate.store_dna.architecture.authoring_contract !== PLANOGRAM_AUTHORING_CONTRACT) fail("Authored candidate contract missing.");
if (authoredCandidate.store_dna.architecture.source_ref !== "scan://STORE-1/e57") fail("Source reference was lost while applying authoring document.");

const scene = buildStoreScene(authoredCandidate, document, { sceneId: "STORE-SCENE-STORE-1" });
if (!scene || scene.contract !== PLANOGRAM_STORE_SCENE_CONTRACT || scene.units !== "m") fail("Canonical StoreScene contract or real-world unit basis missing.");
const serialized = serializeStoreScene(scene);
const roundTripped = deserializeStoreScene(serialized);
if (serializeStoreScene(roundTripped) !== serialized) fail("StoreScene round-trip is not deterministic.");
pass("SCENE-001", "deterministic serialize/deserialize round trip");

const projection2D = projectStoreScene2D(scene);
const projection3D = projectStoreScene3D(scene);
const commonGeometry2D = projection2D.nodes.map(({ nodeId, nodeType, parentId, geometry, locked }) => ({ nodeId, nodeType, parentId, geometry, locked }));
const commonGeometry3D = projection3D.nodes.map(({ nodeId, nodeType, parentId, geometry, locked }) => ({ nodeId, nodeType, parentId, geometry, locked }));
if (JSON.stringify(commonGeometry2D) !== JSON.stringify(commonGeometry3D)) fail("2D and 3D projections diverged from canonical StoreScene geometry.");
if (projection2D.sceneId !== projection3D.sceneId || projection2D.revision !== projection3D.revision) fail("2D/3D scene identity or revision diverged.");
pass("SCENE-002", "2D and 3D project identical geometry from one StoreScene");

let history = createStoreSceneHistory(scene);
const stableNodeId = scene.nodes[0].nodeId;
const originalCenter = scene.nodes[0].geometry.centerXM;
history = executeStoreSceneCommand(history, {
  commandId: "CMD-MOVE-1",
  type: "UPDATE_NODE",
  nodeId: stableNodeId,
  expectedRevision: history.present.revision,
  patch: { geometry: { centerXM: originalCenter + 0.5 } },
});
const editedRevision = history.present.revision;
if (history.present.nodes[0].nodeId !== stableNodeId || editedRevision !== scene.revision + 1) fail("Stable node id or revision contract drifted during command execution.");
const editedSerialized = serializeStoreScene(history.present);
if (deserializeStoreScene(editedSerialized).nodes[0].nodeId !== stableNodeId) fail("Stable node id did not survive persisted edit round trip.");
pass("SCENE-003", "stable ids and revisions survive editing and persistence round trip");

history = undoStoreSceneCommand(history);
if (history.present.nodes[0].geometry.centerXM !== originalCenter) fail("Undo did not apply deterministic inverse command.");
history = redoStoreSceneCommand(history);
if (history.present.nodes[0].geometry.centerXM !== originalCenter + 0.5) fail("Redo did not deterministically reapply command.");
pass("UNDO-001", "reversible command history preserves deterministic geometry");

const snappedBoundary = snapStoreSceneCoordinate(1.05, [1.1, 2], { thresholdM: 0.05, gridM: 0.25 });
if (snappedBoundary !== 1.1) fail(`Snap threshold boundary drifted: ${snappedBoundary}`);
const snappedGrid = snapStoreSceneCoordinate(1.17, [2], { thresholdM: 0.05, gridM: 0.25 });
if (snappedGrid !== 1.25) fail(`Grid fallback snap drifted: ${snappedGrid}`);
pass("SNAP-001", "anchor threshold and grid fallback are deterministic");

let fixtureScene = scene;
for (const [commandId, node] of [
  ["CMD-FIXTURE-A", createStoreSceneNode({ nodeId: "FIXTURE-A", nodeType: "fixture", geometry: { centerXM: 2, centerYM: 5, widthM: 1, depthM: 1, rotationDeg: 0 } })],
  ["CMD-FIXTURE-B", createStoreSceneNode({ nodeId: "FIXTURE-B", nodeType: "fixture", geometry: { centerXM: 3.8, centerYM: 5, widthM: 1, depthM: 1, rotationDeg: 0 } })],
  ["CMD-FIXTURE-C", createStoreSceneNode({ nodeId: "FIXTURE-C", nodeType: "fixture", geometry: { centerXM: 2.4, centerYM: 5, widthM: 1, depthM: 1, rotationDeg: 12 } })],
]) {
  fixtureScene = applyStoreSceneCommand(fixtureScene, {
    commandId,
    type: "CREATE_NODE",
    node,
    expectedRevision: fixtureScene.revision,
  }).scene;
}
const collisions = findStoreSceneCollisions(fixtureScene);
if (!collisions.some((row) => [row.leftNodeId, row.rightNodeId].includes("FIXTURE-A") && [row.leftNodeId, row.rightNodeId].includes("FIXTURE-C"))) fail("Oriented fixture overlap was not detected.");
pass("COLL-001", "oriented overlapping fixtures are detected deterministically");

const aisleViolations = findStoreSceneAisleViolations(fixtureScene, 1);
const fixturePair = aisleViolations.find((row) => [row.leftNodeId, row.rightNodeId].includes("FIXTURE-A") && [row.leftNodeId, row.rightNodeId].includes("FIXTURE-B"));
if (!fixturePair || fixturePair.clearanceM !== 0.8 || fixturePair.deficitM !== 0.2) fail(`Aisle clearance measurement drifted: ${JSON.stringify(fixturePair)}`);
pass("AISLE-001", "minimum aisle violation is deterministic and measurable");

let lockHistory = createStoreSceneHistory(fixtureScene);
lockHistory = executeStoreSceneCommand(lockHistory, {
  commandId: "CMD-LOCK-A",
  type: "SET_LOCK",
  nodeId: "FIXTURE-A",
  locked: true,
  expectedRevision: lockHistory.present.revision,
});
const optimizerResult = applyOptimizerStoreSceneSuggestions(lockHistory.present, [
  { nodeId: "FIXTURE-A", patch: { geometry: { centerXM: 8 } } },
  { nodeId: "FIXTURE-B", patch: { geometry: { centerXM: 4.2 } } },
], { optimizerRunId: "OPT-RUN-42" });
if (!optimizerResult.blocked.some((row) => row.nodeId === "FIXTURE-A" && row.reason === "locked-human-override")) fail("Optimizer overwrote a locked human node.");
const optimizedB = optimizerResult.scene.nodes.find((row) => row.nodeId === "FIXTURE-B");
if (optimizedB.geometry.centerXM !== 4.2 || optimizedB.provenance.optimizerRunId !== "OPT-RUN-42") fail("Optimizer scene command or provenance was not applied to unlocked node.");
pass("LOCK-001", "optimizer respects human locks and records provenance");

if (scene.provenance.physicalTruthAttested !== false || scene.previewOnly !== true) fail("StoreScene existence was promoted into physical truth authority.");
pass("AUTH-001", "canonical scene remains fail-closed for physical truth authority");

const reviewedResult = {
  reviewed_draft_ready: true,
  reviewed_draft_fingerprint: "reviewed456",
  reviewed_store_dna_v2_preview: {
    review: { human_reviewed: true, scan_fingerprint: "scan123" },
    architecture: {
      schema_version: 2,
      coordinate_system: "cartesian_m_centered_rect",
      source: "e57_semantic_scan",
      floor_width_m: 9,
      floor_depth_m: 6,
      elements: [],
    },
  },
};
const scanCandidate = candidateFromReviewedStoreScan(null, reviewedResult);
if (!scanCandidate?.store_dna?.architecture?.preview_only) fail("Reviewed scan draft was promoted out of preview authority.");
if (scanCandidate.store_dna.architecture.source_review_fingerprint !== "reviewed456") fail("Reviewed scan fingerprint did not bind into editable model.");

const englishKeys = Object.keys(PLANOGRAM_AUTHORING_MESSAGES.en).sort();
for (const { code } of SUPPORTED_LOCALES) {
  const keys = Object.keys(PLANOGRAM_AUTHORING_MESSAGES[code] || {}).sort();
  if (JSON.stringify(keys) !== JSON.stringify(englishKeys)) fail(`Authoring locale coverage drifted: ${code}`);
}

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
const authoring = fs.readFileSync("src/modules/planogram/PlanogramArchitecturalAuthoring.jsx", "utf8");
const scanWorkspace = fs.readFileSync("src/modules/planogram/PlanogramScanAnnotationWorkspace.jsx", "utf8");
const pickerEye = fs.readFileSync("src/modules/planogram/PlanogramPickerEyePreview.jsx", "utf8");
for (const needle of ["PlanogramArchitecturalAuthoring", "onOpenEditableModel", "candidateFromReviewedStoreScan"]) {
  if (!studio.includes(needle)) fail(`Studio scan-to-authoring integration missing: ${needle}`);
}
for (const needle of ["onPointerMove", "updatePlanogramAuthoringElement", "resizePlanogramAuthoringFloor", "data-rotation-deg"]) {
  if (!authoring.includes(needle)) fail(`Architectural editor capability missing: ${needle}`);
}
if (!scanWorkspace.includes("onOpenEditableModel(reviewedResult)")) fail("Reviewed scan cannot be opened in editable model.");
for (const needle of ["PointerLockControls", "RoomEnvironment", "MeshPhysicalMaterial", "blockedAt", "GLTFLoader", "front_image_path", "model_path"]) {
  if (!pickerEye.includes(needle)) fail(`Immersive digital twin capability missing: ${needle}`);
}
if (/https?:\/\//.test(pickerEye)) fail("Immersive renderer must not introduce remote asset URLs.");

console.log("Planogram architectural authoring + canonical StoreScene + scan-to-editable + immersive twin contracts: PASS");