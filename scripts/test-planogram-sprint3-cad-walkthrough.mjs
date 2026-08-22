import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_AUTHORING_MESSAGES } from "../src/platform/i18n/planogramAuthoringMessages.js";
import { PLANOGRAM_WALKTHROUGH_MESSAGES } from "../src/platform/i18n/planogramWalkthroughMessages.js";
import {
  buildPlanogramCadDistributeUpdates,
  buildPlanogramCadSelectionMetrics,
  createPlanogramCadFixtureNode,
  createPlanogramCadMeasurementNode,
  hydratePlanogramCadOverlay,
  PLANOGRAM_CAD_OVERLAY_CONTRACT,
  PLANOGRAM_CAD_OVERLAY_LIMIT,
  snapPlanogramCadSelectionDelta,
} from "../src/modules/planogram/planogramCadAdvanced.js";
import {
  createPlanogramCadSession,
  executePlanogramCadSessionCommand,
  PLANOGRAM_CAD_SESSION_CONTRACT,
  redoPlanogramCadSession,
  undoPlanogramCadSession,
} from "../src/modules/planogram/planogramCadSession.js";
import { createStoreSceneNode, PLANOGRAM_STORE_SCENE_CONTRACT } from "../src/modules/planogram/planogramAuthoringModel.js";
import {
  buildPlanogramWalkthroughNavigation,
  isPlanogramWalkthroughPositionBlocked,
  PLANOGRAM_WALKTHROUGH_NAVIGATION_CONTRACT,
  resolvePlanogramWalkthroughStep,
} from "../src/modules/planogram/planogramWalkthroughNavigation.js";

function fail(message) { console.error(message); process.exit(1); }

const reviewedResult = {
  reviewed_draft_ready: true,
  reviewed_draft_fingerprint: "reviewed-sprint3-004",
  reviewed_store_dna_v2_preview: {
    review: { human_reviewed: true, scan_fingerprint: "scan-sprint3-004" },
    architecture: {
      schema_version: 2,
      coordinate_system: "cartesian_m_centered_rect",
      source: "human_reviewed_store_scan",
      source_ref: "scan://SPRINT3/review-004",
      floor_width_m: 10,
      floor_depth_m: 8,
      elements: [
        { element_id: "ENTRY", element_type: "picker_entry", center_x_m: 1, center_y_m: 1, width_m: 0.4, depth_m: 0.4, rotation_deg: 0, scan_source_element_id: "scan-entry-4" },
        { element_id: "SCAN-WALL", element_type: "wall", center_x_m: 3, center_y_m: 3, width_m: 2, depth_m: 0.12, rotation_deg: 17, scan_source_element_id: "scan-wall-4", scan_confidence: 0.93 },
      ],
    },
  },
};

let session = createPlanogramCadSession({ reviewedResult, minimumAisleM: 1 });
if (!session || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT || session.scene.contract !== PLANOGRAM_STORE_SCENE_CONTRACT) fail("Sprint 3 canonical CAD session missing.");
const initialRevision = session.scene.revision;
const initialDepth = session.historyDepth;
const noOp = executePlanogramCadSessionCommand(session, { commandId: "CAD-NOOP", type: "UPDATE_NODE", nodeId: "SCAN-WALL", expectedRevision: session.scene.revision, patch: { geometry: { centerXM: 3 } } });
if (noOp !== session || noOp.scene.revision !== initialRevision || noOp.historyDepth !== initialDepth) fail("No-op CAD edit polluted StoreScene revision history.");

session = executePlanogramCadSessionCommand(session, { commandId: "CAD-MOVE-SCAN-WALL", type: "UPDATE_NODE", nodeId: "SCAN-WALL", expectedRevision: session.scene.revision, patch: { geometry: { centerXM: 4.25, rotationDeg: 23 } } });
const projectedWall = session.candidate.store_dna.architecture.elements.find((row) => row.element_id === "SCAN-WALL");
if (!projectedWall || projectedWall.center_x_m !== 4.25 || projectedWall.rotation_deg !== 23 || projectedWall.scan_confidence !== 0.93 || projectedWall.scan_source_element_id !== "scan-wall-4") fail("StoreScene edit/provenance projection drifted.");

for (const fixture of [
  createPlanogramCadFixtureNode({ nodeId: "CAD-FIX-A", fixtureType: "REGULAR_SHELF", fixtureCode: "GONDOLA-1000", centerXM: 5, centerYM: 5, rotationDeg: 17 }),
  createPlanogramCadFixtureNode({ nodeId: "CAD-FIX-B", fixtureType: "REGULAR_SHELF", fixtureCode: "GONDOLA-1000", centerXM: 6.4, centerYM: 5.3, rotationDeg: -12 }),
]) {
  session = executePlanogramCadSessionCommand(session, { commandId: `CREATE-${fixture.nodeId}`, type: "CREATE_NODE", node: fixture, expectedRevision: session.scene.revision });
}
const overlay = session.candidate.store_dna.cad_overlay;
if (!overlay || overlay.contract !== PLANOGRAM_CAD_OVERLAY_CONTRACT || overlay.preview_only !== true || overlay.production_release_allowed !== false) fail("CAD overlay authority boundary missing.");
if (!overlay.nodes.some((row) => row.nodeId === "CAD-FIX-A" && row.nodeType === "fixture" && row.metadata?.fixtureCode === "GONDOLA-1000")) fail("Authored fixture did not persist in CAD overlay.");
const rehydrated = createPlanogramCadSession({ candidate: session.candidate, minimumAisleM: 1 });
if (!rehydrated?.scene.nodes.some((row) => row.nodeId === "CAD-FIX-A" && row.nodeType === "fixture")) fail("CAD fixture overlay did not rehydrate into StoreScene.");
if (rehydrated.productionReleaseAllowed !== false || rehydrated.physicalTruthAttested !== false) fail("CAD overlay rehydration self-promoted production authority.");
session = rehydrated;

const beforeBatchRevision = session.scene.revision;
const beforeBatchA = session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-A");
const beforeBatchB = session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-B");
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-BATCH-ALIGN-X", type: "UPDATE_NODES", expectedRevision: session.scene.revision, updates: [{ nodeId: "CAD-FIX-A", patch: { geometry: { centerXM: 5.7 } } }, { nodeId: "CAD-FIX-B", patch: { geometry: { centerXM: 5.7 } } }] });
if (session.scene.revision !== beforeBatchRevision + 1 || session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-A").geometry.centerXM !== 5.7 || session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-B").geometry.centerXM !== 5.7) fail("Atomic multi-node StoreScene update did not use one revision.");
session = undoPlanogramCadSession(session);
if (session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-A").geometry.centerXM !== beforeBatchA.geometry.centerXM || session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-B").geometry.centerXM !== beforeBatchB.geometry.centerXM) fail("Atomic multi-node undo did not restore the group.");
session = redoPlanogramCadSession(session);
if (session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-A").geometry.centerXM !== 5.7 || session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-B").geometry.centerXM !== 5.7) fail("Atomic multi-node redo drifted.");

session = executePlanogramCadSessionCommand(session, { commandId: "CAD-LOCK-A", type: "SET_LOCK", nodeId: "CAD-FIX-A", expectedRevision: session.scene.revision, locked: true });
const lockedRevision = session.scene.revision;
const lockedB = session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-B").geometry.centerYM;
let batchRejected = false;
try {
  executePlanogramCadSessionCommand(session, { commandId: "CAD-BATCH-LOCKED", type: "UPDATE_NODES", expectedRevision: session.scene.revision, updates: [{ nodeId: "CAD-FIX-A", patch: { geometry: { centerYM: 6 } } }, { nodeId: "CAD-FIX-B", patch: { geometry: { centerYM: 6 } } }] });
} catch { batchRejected = true; }
if (!batchRejected || session.scene.revision !== lockedRevision || session.scene.nodes.find((row) => row.nodeId === "CAD-FIX-B").geometry.centerYM !== lockedB) fail("Locked batch transform was partially applied instead of atomically rejected.");
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-UNLOCK-A", type: "SET_LOCK", nodeId: "CAD-FIX-A", expectedRevision: session.scene.revision, locked: false });

for (const fixture of [
  createPlanogramCadFixtureNode({ nodeId: "DIST-A", centerXM: 2, centerYM: 6 }),
  createPlanogramCadFixtureNode({ nodeId: "DIST-B", centerXM: 4, centerYM: 6 }),
  createPlanogramCadFixtureNode({ nodeId: "DIST-C", centerXM: 9, centerYM: 6 }),
]) session = executePlanogramCadSessionCommand(session, { commandId: `CREATE-${fixture.nodeId}`, type: "CREATE_NODE", node: fixture, expectedRevision: session.scene.revision });
const distributeUpdates = buildPlanogramCadDistributeUpdates(session.scene, ["DIST-A", "DIST-B", "DIST-C"], "x");
if (distributeUpdates.length !== 1 || distributeUpdates[0].nodeId !== "DIST-B" || distributeUpdates[0].patch.geometry.centerXM !== 5.5) fail(`CAD distribute kernel drifted: ${JSON.stringify(distributeUpdates)}`);
const beforeDistributeRevision = session.scene.revision;
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-DISTRIBUTE-X", type: "UPDATE_NODES", expectedRevision: session.scene.revision, updates: distributeUpdates });
if (session.scene.revision !== beforeDistributeRevision + 1 || session.scene.nodes.find((row) => row.nodeId === "DIST-B").geometry.centerXM !== 5.5) fail("CAD distribute did not apply atomically.");
session = undoPlanogramCadSession(session);
if (session.scene.nodes.find((row) => row.nodeId === "DIST-B").geometry.centerXM !== 4) fail("CAD distribute undo drifted.");
session = redoPlanogramCadSession(session);

const measurement = createPlanogramCadMeasurementNode({ scene: session.scene, nodeId: "MEASURE-DIST-A-C", sourceNodeIds: ["DIST-A", "DIST-C"] });
if (measurement.metadata.measuredDistanceM !== 7 || measurement.metadata.deltaXM !== 7 || measurement.metadata.deltaYM !== 0) fail(`CAD measurement kernel drifted: ${JSON.stringify(measurement.metadata)}`);
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-MEASURE", type: "CREATE_NODE", node: measurement, expectedRevision: session.scene.revision });
if (!session.candidate.store_dna.cad_overlay.nodes.some((row) => row.nodeId === "MEASURE-DIST-A-C" && row.nodeType === "measurement")) fail("CAD measurement did not persist in overlay.");
const measurementReload = createPlanogramCadSession({ candidate: session.candidate });
if (!measurementReload.scene.nodes.some((row) => row.nodeId === "MEASURE-DIST-A-C" && row.metadata?.measuredDistanceM === 7)) fail("CAD measurement did not survive overlay round-trip.");
session = measurementReload;

session = executePlanogramCadSessionCommand(session, { commandId: "GUIDE-WALL", type: "CREATE_NODE", expectedRevision: session.scene.revision, node: createStoreSceneNode({ nodeId: "GUIDE-WALL", nodeType: "wall", geometry: { centerXM: 7.8, centerYM: 2, widthM: 2, depthM: 0.12, heightM: 2.5, rotationDeg: 0 }, provenance: { source: "human", sourceRef: "cad-session" } }) });
session = executePlanogramCadSessionCommand(session, { commandId: "SNAP-FIX", type: "CREATE_NODE", expectedRevision: session.scene.revision, node: createPlanogramCadFixtureNode({ nodeId: "SNAP-FIX", centerXM: 5, centerYM: 2, widthM: 1, depthM: 0.5 }) });
const snapped = snapPlanogramCadSelectionDelta(session.scene, ["SNAP-FIX"], 2.77, 0, { gridM: 0.01, thresholdM: 0.05 });
if (!snapped.snappedX || snapped.deltaX !== 2.8 || !snapped.guides.some((guide) => guide.axis === "x" && guide.value === 7.8 && guide.sourceNodeId === "GUIDE-WALL")) fail(`CAD smart snap guide drifted: ${JSON.stringify(snapped)}`);
const metrics = buildPlanogramCadSelectionMetrics(session.scene, ["DIST-A", "DIST-C"]);
if (metrics.count !== 2 || metrics.widthM <= 7 || metrics.center.x !== 5.5) fail(`CAD selection metric kernel drifted: ${JSON.stringify(metrics)}`);

session = executePlanogramCadSessionCommand(session, { commandId: "CAD-EDGE", type: "CREATE_NODE", expectedRevision: session.scene.revision, node: createPlanogramCadFixtureNode({ nodeId: "CAD-EDGE", centerXM: 9.4, centerYM: 2, widthM: 1, depthM: 0.6, heightM: 2 }) });
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-RESIZE", type: "RESIZE_FLOOR", expectedRevision: session.scene.revision, widthM: 9, depthM: 8 });
if (session.diagnostics.boundaryViolationCount < 1) fail("Floor resize did not expose boundary diagnostics.");
session = undoPlanogramCadSession(session);
if (session.scene.floor.widthM !== 10) fail("Floor resize undo drifted.");

const maliciousCandidates = [
  { reason: "duplicate-id", overlay: { contract: PLANOGRAM_CAD_OVERLAY_CONTRACT, preview_only: true, production_release_allowed: false, nodes: [{ nodeId: "ENTRY", nodeType: "fixture", geometry: { centerXM: 2, centerYM: 2, widthM: 1, depthM: 1 } }] } },
  { reason: "invalid-type", overlay: { contract: PLANOGRAM_CAD_OVERLAY_CONTRACT, preview_only: true, production_release_allowed: false, nodes: [{ nodeId: "BAD-WALL", nodeType: "wall", geometry: { centerXM: 2, centerYM: 2, widthM: 1, depthM: 1 } }] } },
  { reason: "remote-url", overlay: { contract: PLANOGRAM_CAD_OVERLAY_CONTRACT, preview_only: true, production_release_allowed: false, nodes: [{ nodeId: "REMOTE", nodeType: "fixture", geometry: { centerXM: 2, centerYM: 2, widthM: 1, depthM: 1 }, provenance: { source: "human", sourceRef: "https://evil.example/fixture.glb" } }] } },
  { reason: "overlay-limit", overlay: { contract: PLANOGRAM_CAD_OVERLAY_CONTRACT, preview_only: true, production_release_allowed: false, nodes: Array.from({ length: PLANOGRAM_CAD_OVERLAY_LIMIT + 1 }, (_, index) => ({ nodeId: `LIMIT-${index}`, nodeType: "fixture", geometry: { centerXM: 1, centerYM: 1, widthM: 1, depthM: 1 } })) } },
];
for (const { reason, overlay: badOverlay } of maliciousCandidates) {
  let rejected = false;
  try { hydratePlanogramCadOverlay(createPlanogramCadSession({ reviewedResult }).scene, { store_dna: { cad_overlay: badOverlay } }); } catch { rejected = true; }
  if (!rejected) fail(`CAD overlay adversarial case was not rejected: ${reason}`);
}

const sceneModel = { contract: "eay.planogram.unified-twin-scene.v1", sourceKind: "reviewed_store_scan_preview", geometryAuthority: "reviewed_scan_preview_not_store_dna_authority", productionReleaseAllowed: false, floor: { widthM: 10, depthM: 8 }, architecture: [{ id: "ENTRY", type: "picker_entry", centerXM: 1, centerYM: 1, widthM: 0.4, depthM: 0.4, rotationDeg: 0 }, { id: "WALL", type: "wall", centerXM: 3, centerYM: 1, widthM: 0.2, depthM: 2, rotationDeg: 0 }], fixtures: [{ id: "FIX-1", moduleKey: "A:1", fixtureType: "REGULAR_SHELF", centerXM: 5, centerYM: 4, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: 30, products: [] }] };
const navigation = buildPlanogramWalkthroughNavigation(sceneModel);
if (!navigation || navigation.contract !== PLANOGRAM_WALKTHROUGH_NAVIGATION_CONTRACT || navigation.productionReleaseAllowed !== false || isPlanogramWalkthroughPositionBlocked(navigation, navigation.start)) fail("Walk-through navigation authority drifted.");
if (!resolvePlanogramWalkthroughStep(navigation, { x: 2.4, y: 1 }, { x: 0.7, y: 0 }).blocked) fail("Walk-through wall collision drifted.");

for (const table of [PLANOGRAM_AUTHORING_MESSAGES, PLANOGRAM_WALKTHROUGH_MESSAGES]) {
  const englishKeys = Object.keys(table.en).sort();
  for (const { code } of SUPPORTED_LOCALES) if (JSON.stringify(Object.keys(table[code] || {}).sort()) !== JSON.stringify(englishKeys)) fail(`Sprint 3 localization drifted: ${code}`);
}
const authoring = fs.readFileSync("src/modules/planogram/PlanogramArchitecturalAuthoring.jsx", "utf8");
const cad = fs.readFileSync("src/modules/planogram/planogramCadSession.js", "utf8");
const advanced = fs.readFileSync("src/modules/planogram/planogramCadAdvanced.js", "utf8");
const walk = fs.readFileSync("src/modules/planogram/PlanogramFirstPersonWalkthrough.jsx", "utf8");
for (const needle of ['type: "UPDATE_NODES"', "selectedIds", "alignSelection", "nudgeSelection", "shiftKey", "ctrlKey", "metaKey", "drag.deltaX", "drag.deltaY", "session.diagnostics", "createPlanogramCadFixtureNode", "createPlanogramCadMeasurementNode", "buildPlanogramCadDistributeUpdates", "snapPlanogramCadSelectionDelta", 'tool === "fixture"', "snapGuides", "measurementRows", "distributeSelection", "createMeasurement", "cad_overlay"]) if (!authoring.includes(needle)) fail(`Sprint 3 advanced CAD UI capability missing: ${needle}`);
for (const needle of ['command.type === "UPDATE_NODES"', "PLANOGRAM_CAD_BATCH_LIMIT", "changed: false", "updates.length > PLANOGRAM_CAD_BATCH_LIMIT", "hydratePlanogramCadOverlay", "candidateWithPlanogramCadOverlay"]) if (!cad.includes(needle)) fail(`Sprint 3 CAD session capability missing: ${needle}`);
for (const needle of ["PLANOGRAM_CAD_OVERLAY_CONTRACT", "createPlanogramCadFixtureNode", "createPlanogramCadMeasurementNode", "buildPlanogramCadDistributeUpdates", "snapPlanogramCadSelectionDelta", "production_release_allowed: false"]) if (!advanced.includes(needle)) fail(`Sprint 3 advanced CAD kernel capability missing: ${needle}`);
for (const forbidden of ["updatePlanogramAuthoringElement(", "removePlanogramAuthoringElement(", "resizePlanogramAuthoringFloor("]) if (authoring.includes(forbidden)) fail(`CAD editor regressed to legacy document mutation: ${forbidden}`);
for (const needle of ['import("three/examples/jsm/controls/PointerLockControls.js")', "resolvePlanogramWalkthroughStep", 'dataset.productionReleaseAllowed = "false"']) if (!walk.includes(needle)) fail(`First-person runtime capability missing: ${needle}`);

console.log("SPRINT3_CAD_NOOP_HISTORY_SUPPRESSION=PASS");
console.log("SPRINT3_CAD_ATOMIC_MULTI_NODE_TRANSFORM=PASS");
console.log("SPRINT3_CAD_LOCKED_BATCH_FAIL_CLOSED=PASS");
console.log("SPRINT3_CAD_MULTISELECT_ALIGN_NUDGE_UI=PASS");
console.log("SPRINT3_CAD_OVERLAY_ROUNDTRIP=PASS");
console.log("SPRINT3_CAD_FIXTURE_AUTHORING_KERNEL=PASS");
console.log("SPRINT3_CAD_DIMENSION_MEASUREMENT=PASS");
console.log("SPRINT3_CAD_SMART_SNAP_GUIDES=PASS");
console.log("SPRINT3_CAD_DISTRIBUTE_KERNEL=PASS");
console.log("SPRINT3_CAD_ADVANCED_EDITOR_UI=PASS");
console.log("SPRINT3_CAD_OVERLAY_PRODUCTION_AUTHORITY=FALSE");
console.log("SPRINT3_COLLISION_AWARE_FIRST_PERSON_WALKTHROUGH=PASS");
