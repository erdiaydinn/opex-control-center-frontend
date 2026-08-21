import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_DIGITAL_TWIN_MESSAGES } from "../src/platform/i18n/planogramDigitalTwinMessages.js";
import {
  buildPlanogramDigitalTwinModel,
  PLANOGRAM_DIGITAL_TWIN_LIMITS,
} from "../src/modules/planogram/planogramDigitalTwinModel.js";
import { metricGridStep } from "../src/modules/planogram/planogramEngineering2D.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

function closeTo(actual, expected, tolerance = 1e-6) {
  return Math.abs(actual - expected) <= tolerance;
}

const engineResult = {
  planogram: {
    aisles: [
      {
        aisle_id: "A",
        modules: [{
          module_id: 1,
          side: "L",
          shelves: [{
            shelf_no: 1,
            shelf_width_cm: 100,
            shelf_depth_cm: 50,
            products: [{ sku: "A-1", facing_count: 2, sales_qty_7d: 10, width_cm: 8, height_cm: 18, depth_cm: 7 }],
          }],
        }],
      },
      {
        aisle_id: "PALLET",
        modules: [{
          module_id: 1,
          fixture_type: "pallet",
          shelves: [{
            shelf_no: 1,
            shelf_width_cm: 120,
            shelf_depth_cm: 100,
            products: [{ sku: "WATER", facing_count: 1, sales_qty_7d: 20 }],
          }],
        }],
      },
    ],
  },
  architecture_route_objective: {
    available: true,
    metric: "sales_weighted_single_origin_walk_m",
    value: 84.5,
    basis: "measured_architecture_grid",
    unreachable_module_ids: [],
  },
};

const candidate = {
  layout: {
    aisles: [
      { aisle_id: "A", modules: [{ module_id: 1, x_m: 2, y_m: 1, width_m: 1, depth_m: 0.5 }] },
      { aisle_id: "PALLET", modules: [{ module_id: 1, x_m: 8, y_m: 1, width_m: 1.2, depth_m: 1, rotation_deg: 90 }] },
    ],
  },
  store_dna: {
    architecture: {
      schema_version: 1,
      coordinate_system: "cartesian_m",
      source: "manual_survey",
      source_ref: "survey://TEST/v1",
      floor_width_m: 12,
      floor_depth_m: 8,
      elements: [
        { element_id: "ENTRY", element_type: "picker_entry", x_m: 0.2, y_m: 0.2, width_m: 0.5, depth_m: 0.5 },
        { element_id: "WALL-90", element_type: "wall", x_m: 5, y_m: 3, width_m: 2, depth_m: 0.2, rotation_deg: 90 },
        { element_id: "EXIT", element_type: "emergency_exit", x_m: 10.5, y_m: 7, width_m: 0.8, depth_m: 0.25, clearance_m: 1.1 },
      ],
    },
  },
};

const measured = buildPlanogramDigitalTwinModel(engineResult, candidate);
if (!measured) fail("Digital twin model must be created for a real planogram.");
if (measured.contract !== "planogram-digital-twin-v1") fail("Digital twin contract drifted.");
if (measured.geometryAuthority !== "measured") fail("Measured coordinates must remain measured authority.");
if (measured.spatialContract !== "store-architecture-v1") fail("V1 spatial contract drifted.");
if (measured.spatialPreviewOnly !== false) fail("Canonical V1 Store DNA must not be mislabeled preview-only.");
if (measured.stats.moduleCount !== 2) fail("Duplicate legacy module ids across aisles must remain distinct.");
if (measured.modules[0].key === measured.modules[1].key) fail("Spatial module identity collapsed across aisles.");
if (measured.stats.placedProductCount !== 2) fail("Placed product count is incorrect.");
if (measured.stats.facingCount !== 3) fail("Facing count is incorrect.");
if (measured.stats.measuredCoordinatePct !== 100) fail("Measured coordinate coverage must be 100%.");
if (measured.floor.widthM !== 12 || measured.floor.depthM !== 8) fail("Measured floorplate must remain authoritative.");
if (!measured.route?.available || measured.route.value !== 84.5) fail("Canonical route evidence must flow into the twin.");

const rotatedPallet = measured.modules.find((item) => item.aisleId === "PALLET");
if (rotatedPallet.rotationDeg !== 90) fail("Module rotation truth was not preserved.");
if (rotatedPallet.footprintWidthM !== 1 || rotatedPallet.footprintDepthM !== 1.2) {
  fail("90-degree module footprint must swap physical width/depth exactly like the backend gate.");
}
if (rotatedPallet.centerXM !== 8.5 || rotatedPallet.centerYM !== 1.6) {
  fail("Rotated module center must use the backend-equivalent V1 footprint.");
}
const rotatedWall = measured.elements.find((item) => item.id === "WALL-90");
if (rotatedWall.footprintWidthM !== 0.2 || rotatedWall.footprintDepthM !== 2) {
  fail("Rotated V1 architecture footprint must match collision geometry.");
}
const emergencyExit = measured.elements.find((item) => item.id === "EXIT");
if (emergencyExit.clearanceM !== 1.1) fail("Emergency-exit clearance must remain visible in the twin model.");

const v2Candidate = structuredClone(candidate);
v2Candidate.store_dna.architecture.schema_version = 2;
v2Candidate.store_dna.architecture.coordinate_system = "cartesian_m_centered_rect";
v2Candidate.store_dna.architecture.source_ref = "roomplan://TEST/v2";
v2Candidate.store_dna.architecture.elements = [
  { element_id: "ENTRY", element_type: "picker_entry", center_x_m: 0.5, center_y_m: 0.5, width_m: 0.5, depth_m: 0.5 },
  { element_id: "WALL-17", element_type: "wall", x_m: 5, y_m: 3, width_m: 2, depth_m: 0.2, rotation_deg: 17 },
  { element_id: "EXIT", element_type: "emergency_exit", center_x_m: 10.9, center_y_m: 7.1, width_m: 0.8, depth_m: 0.25, rotation_deg: 33, clearance_m: 1.1 },
];
v2Candidate.layout.aisles[0].modules[0].rotation_deg = 17;
const v2 = buildPlanogramDigitalTwinModel(engineResult, v2Candidate);
if (!v2) fail("Architecture V2 must project into a preview digital twin.");
if (v2.geometryAuthority !== "measured-preview-v2") fail("Architecture V2 must never silently become production measured authority.");
if (v2.spatialContract !== "store-architecture-v2-oriented-polygons") fail("Architecture V2 spatial contract missing from twin.");
if (!v2.spatialPreviewOnly || !v2.arbitraryAngleGeometry) fail("Architecture V2 preview/arbitrary-angle flags must remain explicit.");
const v2Wall = v2.elements.find((item) => item.id === "WALL-17");
if (!v2Wall || v2Wall.rotationDeg !== 17) fail("17-degree measured wall was snapped or dropped in the digital twin.");
if (!closeTo(v2Wall.centerXM, 6) || !closeTo(v2Wall.centerYM, 3.1)) {
  fail("Architecture V2 lower-left source geometry must rotate around its true physical center.");
}
const wallRadians = (17 * Math.PI) / 180;
const expectedWallWidth = 2 * Math.abs(Math.cos(wallRadians)) + 0.2 * Math.abs(Math.sin(wallRadians));
const expectedWallDepth = 2 * Math.abs(Math.sin(wallRadians)) + 0.2 * Math.abs(Math.cos(wallRadians));
if (!closeTo(v2Wall.footprintWidthM, expectedWallWidth) || !closeTo(v2Wall.footprintDepthM, expectedWallDepth)) {
  fail("Architecture V2 arbitrary-angle bounding footprint is not geometry-faithful.");
}
const v2Module = v2.modules.find((item) => item.aisleId === "A");
if (v2Module.rotationDeg !== 17) fail("17-degree fixture rotation was snapped in the digital twin model.");
if (!closeTo(v2Module.centerXM, 2.5) || !closeTo(v2Module.centerYM, 1.25)) {
  fail("Architecture V2 fixture center drifted from backend polygon semantics.");
}

const v2RouteEngine = structuredClone(engineResult);
v2RouteEngine.architecture_route_objective_v2 = {
  contract: "architecture-polygon-astar-v2",
  preview_only: true,
  available: true,
  distance_m: 7.25,
  path_m: [[0.5, 0.5], [1, 1], [2, 1.5]],
};
const v2WithRoute = buildPlanogramDigitalTwinModel(v2RouteEngine, v2Candidate);
if (!v2WithRoute.route?.available || v2WithRoute.route.value !== 7.25) fail("Architecture V2 A* preview route did not reach the twin.");
if (!v2WithRoute.route.previewOnly || v2WithRoute.route.basis !== "architecture-polygon-astar-v2") {
  fail("Architecture V2 route must remain visibly preview-only.");
}

const topologyCandidate = structuredClone(candidate);
topologyCandidate.layout.aisles[0].modules[0].x_m = null;
topologyCandidate.layout.aisles[0].modules[0].y_m = "";
delete topologyCandidate.store_dna.architecture;
const topology = buildPlanogramDigitalTwinModel(engineResult, topologyCandidate);
if (topology.geometryAuthority !== "topology-preview") fail("Null/empty coordinates must never become measured truth.");
if (topology.modules[0].coordinateAuthority !== "topology") fail("Fallback module must be marked topology-only.");

if (PLANOGRAM_DIGITAL_TWIN_LIMITS.maxProductInstances3d > 2000) {
  fail("3D product instance guard is too high for the canonical web surface.");
}

const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const locales = SUPPORTED_LOCALES.map((item) => item.code);
if (JSON.stringify(locales) !== JSON.stringify(expectedLocales)) fail("Digital twin locale set drifted.");
const enKeys = Object.keys(PLANOGRAM_DIGITAL_TWIN_MESSAGES.en).sort();
for (const locale of locales) {
  const keys = Object.keys(PLANOGRAM_DIGITAL_TWIN_MESSAGES[locale] || {}).sort();
  if (JSON.stringify(keys) !== JSON.stringify(enKeys)) fail(`Digital twin translation key drift for ${locale}.`);
}

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
const canonical = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
const renderer = fs.readFileSync("src/modules/planogram/PlanogramTwinSceneRenderer.jsx", "utf8");
const runtime = fs.readFileSync("src/modules/planogram/planogramThreeAssetRuntime.js", "utf8");
const css = fs.readFileSync("src/modules/planogram/planogram-digital-twin.css", "utf8");

for (const [needle, label] of [
  ["PlanogramDigitalTwin", "canonical Studio integration"],
  ["engineResult?.planogram ?", "fail-closed renderer activation"],
]) {
  if (!studio.includes(needle)) fail(`Planogram Studio missing ${label}: ${needle}`);
}

for (const [needle, label] of [
  ["PlanogramTwinSceneRenderer", "shared renderer integration"],
  ["buildPlanogramUnifiedTwinScene", "unified authored scene"],
  ["buildPlanogramVisualQualityPlan", "governed visual plan"],
  ["buildPlanogramVisualDeliveryPlan", "accelerated texture/LOD plan"],
  ["rotatedRectSvgPoints", "true arbitrary-angle polygon projection in 2D"],
  ["data-coordinate-authority", "coordinate truth rendering"],
  ["data-rotation-deg", "rotation evidence on 2D geometry"],
  ["eay-twin-engineering-dimensions", "engineering floor dimensions"],
  ["eay-twin-scale-bar", "engineering scale bar"],
  ["eay-twin-egress-clearance", "emergency-exit clearance rendering"],
  ["aria-selected", "accessible 2D/3D tabs"],
  ["PLANOGRAM_DIGITAL_TWIN_LIMITS.maxProductInstances3d", "3D render cap"],
]) {
  if (!canonical.includes(needle)) fail(`Canonical Digital Twin missing ${label}: ${needle}`);
}

for (const [needle, label] of [
  ['await import("three")', "dynamic Three.js loading"],
  ['await import("three/examples/jsm/controls/OrbitControls.js")', "dynamic OrbitControls loading"],
  ["InstancedMesh", "bounded product instancing"],
  ["buildFacingInstances", "facing-aware product placement"],
  ["addMetricFixtureFallback", "open metric fixture geometry"],
  ["MeshPhysicalMaterial", "glass/cold-fixture material"],
  ["setColorAt", "SKU-distinguishable product facings"],
  ["ACESFilmicToneMapping", "market-grade tone mapping baseline"],
  ["mesh.rotation.y = (-Number(element.rotationDeg", "arbitrary-angle architecture rotation in 3D"],
  ["group.rotation.y = (-Number(fixture.rotationDeg", "arbitrary-angle fixture rotation in 3D"],
  ["renderer.domElement.tabIndex = 0", "keyboard-focusable 3D canvas"],
  ["assetRuntime.loadProductTexture", "governed packshot/KTX2/atlas texture runtime"],
  ["assetRuntime.loadFixtureLod", "governed runtime fixture LOD"],
]) {
  if (!renderer.includes(needle)) fail(`Shared Digital Twin renderer missing ${label}: ${needle}`);
}

for (const [needle, label] of [
  ['import("three/examples/jsm/loaders/GLTFLoader.js")', "dynamic GLB loader"],
  ['import("three/examples/jsm/loaders/KTX2Loader.js")', "dynamic KTX2 loader"],
  ["new THREE.LOD()", "camera-aware GLB LOD primitive"],
  ["canonical_store_scene", "StoreScene geometry authority"],
]) {
  if (!runtime.includes(needle)) fail(`Three asset runtime missing ${label}: ${needle}`);
}

if (canonical.includes("const width = element.footprintWidthM * scale")) fail("2D architecture must not regress to arbitrary-angle AABB rendering.");
if (canonical.includes("const width = Math.max(module.footprintWidthM * scale, 10)")) fail("2D fixtures must not regress to arbitrary-angle AABB rendering.");
if (renderer.includes("const perRow = Math.max(1, Math.ceil(Math.sqrt(products.length)))")) fail("3D product rendering must not regress to square-root debug-grid placement.");
for (const source of [canonical, renderer, runtime]) {
  if (/from\s+["']three["']/.test(source)) fail("Three.js must remain dynamically loaded rather than entering the eager Planogram chunk.");
  if (source.includes("production_release_allowed ?") || source.includes("productionReleaseAllowed ?")) {
    fail("Digital twin must never unlock production publication from preview payloads.");
  }
}
for (const rule of [
  "eay-twin-egress-clearance",
  "eay-twin-engineering-dimensions",
  "eay-twin-scale-bar",
  "@media (prefers-reduced-motion: reduce)",
  "@media (forced-colors: active)",
  ":focus-visible",
]) {
  if (!css.includes(rule)) fail(`Digital twin accessibility/physical-truth CSS missing: ${rule}`);
}

const moduleDimensionContractResult = {
  planogram: {
    aisles: [{
      aisle_id: "MEASURED",
      modules: [{
        module_id: "M-150",
        module_width_cm: 150,
        module_depth_cm: 65,
        module_height_cm: 210,
        shelves: [{ shelf_no: 1, shelf_width_cm: 100, shelf_depth_cm: 50, products: [] }],
      }],
    }],
  },
};
const moduleDimensionContractCandidate = {
  layout: {
    aisles: [{
      aisle_id: "MEASURED",
      modules: [{
        module_id: "M-150",
        center_x_m: 3,
        center_y_m: 2,
        module_width_cm: 150,
        module_depth_cm: 65,
        module_height_cm: 210,
        rotation_deg: 17,
      }],
    }],
  },
  store_dna: {
    architecture: {
      schema_version: 2,
      coordinate_system: "cartesian_m_centered_rect",
      source: "manual_survey",
      source_ref: "survey://MODULE-DIMENSIONS/v1",
      floor_width_m: 8,
      floor_depth_m: 6,
      elements: [],
    },
  },
};
const moduleDimensionContract = buildPlanogramDigitalTwinModel(moduleDimensionContractResult, moduleDimensionContractCandidate);
const measuredModule = moduleDimensionContract?.modules?.[0];
if (!measuredModule) fail("module_*_cm regression fixture did not render.");
if (!closeTo(measuredModule.widthM, 1.5) || !closeTo(measuredModule.depthM, 0.65)) {
  fail("module_*_cm must override shelf fallback geometry in the digital twin.");
}
if (!closeTo(measuredModule.heightM, 2.1)) fail("module_height_cm must drive the physical 3D fixture height.");
for (const [scale, expectedMeters, expectedPixels] of [[20, 2, 40], [200, 0.2, 40]]) {
  const grid = metricGridStep({ scale });
  if (!closeTo(grid.meters, expectedMeters) || !closeTo(grid.pixels, expectedPixels)) {
    fail("Metric grid must remain scale-correct across small and large floorplans.");
  }
}
const angle = 17 * Math.PI / 180;
const expectedFootprintWidth = 1.5 * Math.abs(Math.cos(angle)) + 0.65 * Math.abs(Math.sin(angle));
const expectedFootprintDepth = 1.5 * Math.abs(Math.sin(angle)) + 0.65 * Math.abs(Math.cos(angle));
if (!closeTo(measuredModule.footprintWidthM, expectedFootprintWidth)
  || !closeTo(measuredModule.footprintDepthM, expectedFootprintDepth)) {
  fail("module_*_cm must feed arbitrary-angle physical geometry.");
}

console.log("Planogram canonical 2D/3D unified digital twin truth, V2 spatial preview and governed facing renderer contract: PASS");
