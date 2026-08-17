import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_DIGITAL_TWIN_MESSAGES } from "../src/platform/i18n/planogramDigitalTwinMessages.js";
import {
  buildPlanogramDigitalTwinModel,
  PLANOGRAM_DIGITAL_TWIN_LIMITS,
} from "../src/modules/planogram/planogramDigitalTwinModel.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const engineResult = {
  planogram: {
    aisles: [
      {
        aisle_id: "A",
        modules: [
          {
            module_id: 1,
            side: "L",
            shelves: [
              {
                shelf_no: 1,
                shelf_width_cm: 100,
                shelf_depth_cm: 50,
                products: [
                  { sku: "A-1", facing_count: 2, sales_qty_7d: 10, width_cm: 8, height_cm: 18, depth_cm: 7 },
                ],
              },
            ],
          },
        ],
      },
      {
        aisle_id: "PALLET",
        modules: [
          {
            module_id: 1,
            fixture_type: "pallet",
            shelves: [
              {
                shelf_no: 1,
                shelf_width_cm: 120,
                shelf_depth_cm: 100,
                products: [{ sku: "WATER", facing_count: 1, sales_qty_7d: 20 }],
              },
            ],
          },
        ],
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
  fail("Rotated module center must use the backend-equivalent footprint.");
}
const rotatedWall = measured.elements.find((item) => item.id === "WALL-90");
if (rotatedWall.footprintWidthM !== 0.2 || rotatedWall.footprintDepthM !== 2) {
  fail("Rotated architecture footprint must match collision geometry.");
}
const emergencyExit = measured.elements.find((item) => item.id === "EXIT");
if (emergencyExit.clearanceM !== 1.1) fail("Emergency-exit clearance must remain visible in the twin model.");

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
  if (JSON.stringify(keys) !== JSON.stringify(enKeys)) {
    fail(`Digital twin translation key drift for ${locale}.`);
  }
}

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
const renderer = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
const css = fs.readFileSync("src/modules/planogram/planogram-digital-twin.css", "utf8");

for (const [needle, label] of [
  ["PlanogramDigitalTwin", "canonical Studio integration"],
  ["engineResult?.planogram ?", "fail-closed renderer activation"],
]) {
  if (!studio.includes(needle)) fail(`Planogram Studio missing ${label}: ${needle}`);
}

for (const [needle, label] of [
  ['await import("three")', "dynamic Three.js loading"],
  ['await import("three/examples/jsm/controls/OrbitControls.js")', "dynamic OrbitControls loading"],
  ["InstancedMesh", "bounded product instancing"],
  ["data-coordinate-authority", "coordinate truth rendering"],
  ["footprintWidthM", "backend-equivalent rotated footprint rendering"],
  ["eay-twin-egress-clearance", "emergency-exit clearance rendering"],
  ["aria-selected", "accessible 2D/3D tabs"],
  ["tabIndex = 0", "keyboard-focusable 3D canvas"],
  ["maxProductInstances3d", "3D render cap"],
]) {
  if (!renderer.includes(needle)) fail(`Digital twin renderer missing ${label}: ${needle}`);
}

if (/from\s+["']three["']/.test(renderer)) {
  fail("Three.js must remain dynamically loaded rather than entering the eager Planogram chunk.");
}
if (studio.includes("production_release_allowed ?") || renderer.includes("production_release_allowed ?")) {
  fail("Digital twin must never unlock production publication from preview payloads.");
}
for (const rule of [
  "eay-twin-egress-clearance",
  "@media (prefers-reduced-motion: reduce)",
  "@media (forced-colors: active)",
  ":focus-visible",
]) {
  if (!css.includes(rule)) fail(`Digital twin accessibility/physical-truth CSS missing: ${rule}`);
}

console.log("Planogram canonical 2D/3D digital twin truth contract: PASS");
