import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_AUTHORING_MESSAGES } from "../src/platform/i18n/planogramAuthoringMessages.js";
import {
  buildPlanogramAuthoringDocument,
  candidateFromReviewedStoreScan,
  candidateWithPlanogramAuthoringDocument,
  createPlanogramAuthoringElement,
  PLANOGRAM_AUTHORING_CONTRACT,
  removePlanogramAuthoringElement,
  resizePlanogramAuthoringFloor,
  updatePlanogramAuthoringElement,
} from "../src/modules/planogram/planogramAuthoringModel.js";

function fail(message) { console.error(message); process.exit(1); }

const candidate = {
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

console.log("Planogram architectural authoring + scan-to-editable + immersive twin contracts: PASS");
