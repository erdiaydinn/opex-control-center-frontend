import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_AUTHORING_MESSAGES } from "../src/platform/i18n/planogramAuthoringMessages.js";
import { PLANOGRAM_WALKTHROUGH_MESSAGES } from "../src/platform/i18n/planogramWalkthroughMessages.js";
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

const reviewedResult = { reviewed_draft_ready: true, reviewed_draft_fingerprint: "reviewed-sprint3-002", reviewed_store_dna_v2_preview: { review: { human_reviewed: true, scan_fingerprint: "scan-sprint3-002" }, architecture: { schema_version: 2, coordinate_system: "cartesian_m_centered_rect", source: "human_reviewed_store_scan", source_ref: "scan://SPRINT3/review-002", floor_width_m: 10, floor_depth_m: 8, elements: [{ element_id: "ENTRY", element_type: "picker_entry", center_x_m: 1, center_y_m: 1, width_m: 0.4, depth_m: 0.4, rotation_deg: 0, scan_source_element_id: "scan-entry-2", scan_confidence: 0.99 }, { element_id: "SCAN-WALL", element_type: "wall", center_x_m: 3, center_y_m: 3, width_m: 2, depth_m: 0.12, rotation_deg: 17, scan_source_element_id: "scan-wall-2", scan_confidence: 0.93 }] } } };
let session = createPlanogramCadSession({ reviewedResult, minimumAisleM: 1 });
if (!session || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT) fail("Sprint 3 CAD session contract missing.");
if (session.scene.contract !== PLANOGRAM_STORE_SCENE_CONTRACT) fail("Reviewed scan did not become a canonical editable StoreScene.");
if (!session.previewOnly || session.productionReleaseAllowed !== false || session.physicalTruthAttested !== false) fail("Reviewed scan CAD session self-promoted beyond preview authority.");
if (session.reviewFingerprint !== "reviewed-sprint3-002") fail("Reviewed scan fingerprint was lost in canonical CAD session provenance.");
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-MOVE-SCAN-WALL", type: "UPDATE_NODE", nodeId: "SCAN-WALL", expectedRevision: session.scene.revision, patch: { geometry: { centerXM: 4.25, rotationDeg: 23 } } });
const projectedWall = session.candidate.store_dna.architecture.elements.find((row) => row.element_id === "SCAN-WALL");
if (!projectedWall || projectedWall.center_x_m !== 4.25 || projectedWall.rotation_deg !== 23) fail("Canonical StoreScene edit did not project back to candidate.");
if (projectedWall.scan_confidence !== 0.93 || projectedWall.scan_source_element_id !== "scan-wall-2") fail("Scan provenance metadata was lost while projecting StoreScene edits back to candidate.");
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-LOCK-SCAN-WALL", type: "SET_LOCK", nodeId: "SCAN-WALL", expectedRevision: session.scene.revision, locked: true });
let lockedRejected = false;
try { executePlanogramCadSessionCommand(session, { commandId: "CAD-ILLEGAL-LOCKED-MOVE", type: "UPDATE_NODE", nodeId: "SCAN-WALL", expectedRevision: session.scene.revision, patch: { geometry: { centerXM: 7 } } }); } catch { lockedRejected = true; }
if (!lockedRejected) fail("Locked CAD node accepted an unauthorized geometry edit.");
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-UNLOCK-SCAN-WALL", type: "SET_LOCK", nodeId: "SCAN-WALL", expectedRevision: session.scene.revision, locked: false });
for (const [commandId, node] of [["CAD-FIX-A", createStoreSceneNode({ nodeId: "CAD-FIX-A", nodeType: "fixture", geometry: { centerXM: 5, centerYM: 5, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: 17 }, provenance: { source: "human", sourceRef: "cad-session" } })], ["CAD-FIX-B", createStoreSceneNode({ nodeId: "CAD-FIX-B", nodeType: "fixture", geometry: { centerXM: 5.35, centerYM: 5, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: -12 }, provenance: { source: "human", sourceRef: "cad-session" } })]]) session = executePlanogramCadSessionCommand(session, { commandId, type: "CREATE_NODE", node, expectedRevision: session.scene.revision });
if (session.diagnostics.collisionCount < 1) fail("CAD session did not surface oriented fixture collision diagnostics.");
const collisionRevision = session.scene.revision;
session = undoPlanogramCadSession(session);
if (session.scene.revision <= collisionRevision || session.scene.nodes.some((row) => row.nodeId === "CAD-FIX-B") || session.redoDepth !== 1) fail("CAD session undo history drifted.");
session = redoPlanogramCadSession(session);
if (!session.scene.nodes.some((row) => row.nodeId === "CAD-FIX-B") || session.redoDepth !== 0) fail("CAD session redo history drifted.");
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-EDGE-FIXTURE", type: "CREATE_NODE", expectedRevision: session.scene.revision, node: createStoreSceneNode({ nodeId: "CAD-EDGE", nodeType: "fixture", geometry: { centerXM: 9.4, centerYM: 2, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: 0 }, provenance: { source: "human", sourceRef: "cad-session" } }) });
if (session.diagnostics.boundaryViolationCount !== 0) fail("In-bounds fixture was incorrectly marked outside the floor.");
session = executePlanogramCadSessionCommand(session, { commandId: "CAD-RESIZE-FLOOR", type: "RESIZE_FLOOR", expectedRevision: session.scene.revision, widthM: 9, depthM: 8 });
if (session.scene.floor.widthM !== 9 || session.diagnostics.boundaryViolationCount < 1) fail("Revisioned floor resize did not expose live boundary violations.");
session = undoPlanogramCadSession(session);
if (session.scene.floor.widthM !== 10 || session.diagnostics.boundaryViolationCount !== 0) fail("Undo did not restore floor geometry and boundary diagnostics.");

const sceneModel = { contract: "eay.planogram.unified-twin-scene.v1", sourceKind: "reviewed_store_scan_preview", geometryAuthority: "reviewed_scan_preview_not_store_dna_authority", productionReleaseAllowed: false, floor: { widthM: 10, depthM: 8 }, architecture: [{ id: "ENTRY", type: "picker_entry", centerXM: 1, centerYM: 1, widthM: 0.4, depthM: 0.4, rotationDeg: 0 }, { id: "WALL", type: "wall", centerXM: 3, centerYM: 1, widthM: 0.2, depthM: 2, rotationDeg: 0 }, { id: "NO-GO", type: "no_go", centerXM: 8, centerYM: 6, widthM: 1.5, depthM: 1, rotationDeg: 23 }], fixtures: [{ id: "FIX-1", moduleKey: "A:1", fixtureType: "REGULAR_SHELF", centerXM: 5, centerYM: 4, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: 30, products: [] }] };
const navigation = buildPlanogramWalkthroughNavigation(sceneModel);
if (!navigation || navigation.contract !== PLANOGRAM_WALKTHROUGH_NAVIGATION_CONTRACT || navigation.productionReleaseAllowed !== false) fail("Walk-through navigation authority drifted.");
if (isPlanogramWalkthroughPositionBlocked(navigation, navigation.start)) fail("Picker-entry start is inside a collision obstacle.");
const wallStop = resolvePlanogramWalkthroughStep(navigation, { x: 2.4, y: 1 }, { x: 0.7, y: 0 });
if (!wallStop.blocked || wallStop.position.x !== 2.4 || wallStop.reason !== "collision-stop") fail("Wall collision did not veto first-person motion.");
const boundaryStep = resolvePlanogramWalkthroughStep(navigation, { x: navigation.bounds.minX + 0.05, y: 2 }, { x: -2, y: 0 });
if (!boundaryStep.blocked || boundaryStep.reason !== "floor-boundary-clamp") fail("Walk-through floor boundary did not fail closed.");
for (const table of [PLANOGRAM_AUTHORING_MESSAGES, PLANOGRAM_WALKTHROUGH_MESSAGES]) { const englishKeys = Object.keys(table.en).sort(); for (const { code } of SUPPORTED_LOCALES) { const keys = Object.keys(table[code] || {}).sort(); if (JSON.stringify(keys) !== JSON.stringify(englishKeys)) fail(`Sprint 3 localization drifted: ${code}`); } }
const authoring = fs.readFileSync("src/modules/planogram/PlanogramArchitecturalAuthoring.jsx", "utf8");
const cad = fs.readFileSync("src/modules/planogram/planogramCadSession.js", "utf8");
const twin = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
const walk = fs.readFileSync("src/modules/planogram/PlanogramFirstPersonWalkthrough.jsx", "utf8");
for (const needle of ["createPlanogramCadSession", "executePlanogramCadSessionCommand", "undoPlanogramCadSession", "redoPlanogramCadSession", 'type: "SET_LOCK"', 'type: "RESIZE_FLOOR"', "session.diagnostics", "has-collision", "has-aisle-violation", "has-boundary-violation", "handleKeyboardShortcut"]) if (!authoring.includes(needle)) fail(`Canonical CAD editor integration missing: ${needle}`);
for (const forbidden of ["updatePlanogramAuthoringElement(", "removePlanogramAuthoringElement(", "resizePlanogramAuthoringFloor("]) if (authoring.includes(forbidden)) fail(`CAD editor regressed to legacy document mutation: ${forbidden}`);
for (const needle of ["candidateWithPlanogramAuthoringDocument", "boundaryViolationCount", 'command.type !== "RESIZE_FLOOR"', "historyDepth", "redoDepth"]) if (!cad.includes(needle)) fail(`CAD session authority capability missing: ${needle}`);
for (const needle of ["PlanogramFirstPersonWalkthrough", 'cameraPreset === "walk"', 'setCameraPreset("walk")', "translatePlanogramWalkthrough"]) if (!twin.includes(needle)) fail(`Canonical Digital Twin walk-through integration missing: ${needle}`);
for (const needle of ['import("three/examples/jsm/controls/PointerLockControls.js")', "buildPlanogramWalkthroughNavigation", "resolvePlanogramWalkthroughStep", "assetRuntime.loadFixtureLod", "assetRuntime.loadProductTexture", 'setAttribute("role", "application")', 'dataset.productionReleaseAllowed = "false"']) if (!walk.includes(needle)) fail(`First-person runtime capability missing: ${needle}`);
if (/https?:\/\//.test(walk)) fail("First-person renderer must not fetch remote visual assets directly.");
console.log("SPRINT3_SCAN_TO_CANONICAL_STORE_SCENE=PASS");
console.log("SPRINT3_CAD_UI_STORE_SCENE_COMMAND_AUTHORITY=PASS");
console.log("SPRINT3_CAD_UNDO_REDO_LOCK_PROVENANCE=PASS");
console.log("SPRINT3_CAD_LIVE_COLLISION_AISLE_BOUNDARY_INSPECTOR=PASS");
console.log("SPRINT3_COLLISION_AWARE_FIRST_PERSON_WALKTHROUGH=PASS");
console.log("SPRINT3_WALKTHROUGH_PRODUCTION_AUTHORITY=FALSE");
