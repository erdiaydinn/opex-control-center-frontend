import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_WALKTHROUGH_MESSAGES } from "../src/platform/i18n/planogramWalkthroughMessages.js";
import {
  createPlanogramCadSession,
  executePlanogramCadSessionCommand,
  PLANOGRAM_CAD_SESSION_CONTRACT,
  undoPlanogramCadSession,
} from "../src/modules/planogram/planogramCadSession.js";
import { createStoreSceneNode, PLANOGRAM_STORE_SCENE_CONTRACT } from "../src/modules/planogram/planogramAuthoringModel.js";
import {
  buildPlanogramWalkthroughNavigation,
  isPlanogramWalkthroughPositionBlocked,
  PLANOGRAM_WALKTHROUGH_NAVIGATION_CONTRACT,
  resolvePlanogramWalkthroughStep,
} from "../src/modules/planogram/planogramWalkthroughNavigation.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const reviewedResult = {
  reviewed_draft_ready: true,
  reviewed_draft_fingerprint: "reviewed-sprint3-001",
  reviewed_store_dna_v2_preview: {
    review: { human_reviewed: true, scan_fingerprint: "scan-sprint3-001" },
    architecture: {
      schema_version: 2,
      coordinate_system: "cartesian_m_centered_rect",
      source: "human_reviewed_store_scan",
      source_ref: "scan://SPRINT3/review-001",
      floor_width_m: 10,
      floor_depth_m: 8,
      elements: [
        {
          element_id: "ENTRY",
          element_type: "picker_entry",
          center_x_m: 1,
          center_y_m: 1,
          width_m: 0.4,
          depth_m: 0.4,
          rotation_deg: 0,
          scan_source_element_id: "scan-entry-1",
        },
      ],
    },
  },
};

let session = createPlanogramCadSession({ reviewedResult, minimumAisleM: 1 });
if (!session || session.contract !== PLANOGRAM_CAD_SESSION_CONTRACT) fail("Sprint 3 CAD session contract missing.");
if (session.scene.contract !== PLANOGRAM_STORE_SCENE_CONTRACT) fail("Reviewed scan did not become a canonical editable StoreScene.");
if (!session.previewOnly || session.productionReleaseAllowed !== false || session.physicalTruthAttested !== false) {
  fail("Reviewed scan CAD session self-promoted beyond preview authority.");
}
if (session.reviewFingerprint !== "reviewed-sprint3-001") fail("Reviewed scan fingerprint was lost in canonical CAD session provenance.");
if (session.scene.nodes.find((row) => row.nodeId === "ENTRY")?.provenance?.source !== "reviewed-scan") {
  fail("Reviewed scan node provenance was lost during StoreScene conversion.");
}

for (const [commandId, node] of [
  ["CAD-FIX-A", createStoreSceneNode({ nodeId: "CAD-FIX-A", nodeType: "fixture", geometry: { centerXM: 5, centerYM: 5, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: 17 }, provenance: { source: "human", sourceRef: "cad-session" } })],
  ["CAD-FIX-B", createStoreSceneNode({ nodeId: "CAD-FIX-B", nodeType: "fixture", geometry: { centerXM: 5.35, centerYM: 5, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: -12 }, provenance: { source: "human", sourceRef: "cad-session" } })],
]) {
  session = executePlanogramCadSessionCommand(session, {
    commandId,
    type: "CREATE_NODE",
    node,
    expectedRevision: session.scene.revision,
  });
}
if (session.diagnostics.collisionCount < 1) fail("CAD session did not surface oriented fixture collision diagnostics.");
const collisionRevision = session.scene.revision;
session = undoPlanogramCadSession(session);
if (session.scene.revision <= collisionRevision) fail("Undo must remain a revisioned StoreScene operation.");
if (session.scene.nodes.some((row) => row.nodeId === "CAD-FIX-B")) fail("CAD session undo did not restore editable geometry deterministically.");

const sceneModel = {
  contract: "eay.planogram.unified-twin-scene.v1",
  sourceKind: "reviewed_store_scan_preview",
  geometryAuthority: "reviewed_scan_preview_not_store_dna_authority",
  productionReleaseAllowed: false,
  floor: { widthM: 10, depthM: 8 },
  architecture: [
    { id: "ENTRY", type: "picker_entry", centerXM: 1, centerYM: 1, widthM: 0.4, depthM: 0.4, rotationDeg: 0 },
    { id: "WALL", type: "wall", centerXM: 3, centerYM: 1, widthM: 0.2, depthM: 2, rotationDeg: 0 },
    { id: "NO-GO", type: "no_go", centerXM: 8, centerYM: 6, widthM: 1.5, depthM: 1, rotationDeg: 23 },
  ],
  fixtures: [
    { id: "FIX-1", moduleKey: "A:1", fixtureType: "REGULAR_SHELF", centerXM: 5, centerYM: 4, widthM: 1, depthM: 0.6, heightM: 2, rotationDeg: 30, products: [] },
  ],
};
const navigation = buildPlanogramWalkthroughNavigation(sceneModel);
if (!navigation || navigation.contract !== PLANOGRAM_WALKTHROUGH_NAVIGATION_CONTRACT) fail("Walk-through navigation contract missing.");
if (navigation.productionReleaseAllowed !== false || navigation.geometryAuthority !== sceneModel.geometryAuthority) {
  fail("Walk-through navigation changed geometry or production authority.");
}
if (navigation.start.x !== 1 || navigation.start.y !== 1) fail(`Picker-entry start drifted: ${JSON.stringify(navigation.start)}`);
if (isPlanogramWalkthroughPositionBlocked(navigation, navigation.start)) fail("Picker-entry start is inside a collision obstacle.");

const wallStop = resolvePlanogramWalkthroughStep(navigation, { x: 2.4, y: 1 }, { x: 0.7, y: 0 });
if (!wallStop.blocked || wallStop.position.x !== 2.4 || wallStop.reason !== "collision-stop") {
  fail(`Wall collision did not veto first-person motion: ${JSON.stringify(wallStop)}`);
}
const clearStep = resolvePlanogramWalkthroughStep(navigation, { x: 1, y: 1 }, { x: 0, y: 0.5 });
if (clearStep.blocked || clearStep.position.y !== 1.5) fail("Clear first-person motion was blocked unexpectedly.");
const boundaryStep = resolvePlanogramWalkthroughStep(navigation, { x: navigation.bounds.minX + 0.05, y: 2 }, { x: -2, y: 0 });
if (!boundaryStep.blocked || boundaryStep.position.x !== navigation.bounds.minX || boundaryStep.reason !== "floor-boundary-clamp") {
  fail("Walk-through floor boundary did not fail closed.");
}

const expectedLocales = SUPPORTED_LOCALES.map((item) => item.code);
const englishKeys = Object.keys(PLANOGRAM_WALKTHROUGH_MESSAGES.en).sort();
for (const locale of expectedLocales) {
  const keys = Object.keys(PLANOGRAM_WALKTHROUGH_MESSAGES[locale] || {}).sort();
  if (JSON.stringify(keys) !== JSON.stringify(englishKeys)) fail(`Walk-through localization drifted: ${locale}`);
}

const twin = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
const walk = fs.readFileSync("src/modules/planogram/PlanogramFirstPersonWalkthrough.jsx", "utf8");
for (const needle of ["PlanogramFirstPersonWalkthrough", 'cameraPreset === "walk"', 'setCameraPreset("walk")', "translatePlanogramWalkthrough"]) {
  if (!twin.includes(needle)) fail(`Canonical Digital Twin walk-through integration missing: ${needle}`);
}
for (const needle of [
  'import("three/examples/jsm/controls/PointerLockControls.js")',
  "buildPlanogramWalkthroughNavigation",
  "resolvePlanogramWalkthroughStep",
  "assetRuntime.loadFixtureLod",
  "assetRuntime.loadProductTexture",
  'setAttribute("role", "application")',
  'dataset.productionReleaseAllowed = "false"',
]) {
  if (!walk.includes(needle)) fail(`First-person runtime capability missing: ${needle}`);
}
if (/https?:\/\//.test(walk)) fail("First-person renderer must not fetch remote visual assets directly.");

console.log("SPRINT3_SCAN_TO_CANONICAL_STORE_SCENE=PASS");
console.log("SPRINT3_CAD_REVISION_UNDO_COLLISION_DIAGNOSTICS=PASS");
console.log("SPRINT3_COLLISION_AWARE_FIRST_PERSON_WALKTHROUGH=PASS");
console.log("SPRINT3_WALKTHROUGH_PRODUCTION_AUTHORITY=FALSE");
