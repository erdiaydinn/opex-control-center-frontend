import fs from "node:fs";
import process from "node:process";

import {
  buildPlanogramDigitalTwinModel,
  PLANOGRAM_DIGITAL_TWIN_LIMITS,
} from "../src/modules/planogram/planogramDigitalTwinModel.js";

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

const engineResult = {
  planogram: {
    aisles: [
      { aisle_id: "A", modules: [{ module_id: 1, shelves: [{ products: [{ sku: "FAST", facing_count: 2 }] }] }] },
      { aisle_id: "PALLET", modules: [{ module_id: 1, fixture_type: "pallet", shelves: [{ products: [{ sku: "WATER", facing_count: 1 }] }] }] },
    ],
  },
  architecture_route_objective: {
    available: true,
    metric: "sales_weighted_single_origin_walk_m",
    value: 195,
    basis: "architecture-grid-astar-v1",
    picker_entry_m: [0.5, 0.5],
    module_distances_m: { "A::1": 2.5, "PALLET::1": 8.5 },
    route_hotspots: [
      {
        module_id: "PALLET::1",
        distance_m: 8.5,
        sales_weight: 20,
        placed_product_count: 1,
        weighted_cost: 170,
        path_m: [[0.5, 0.5], [0.5, 2], [8.5, 2], [8.5, 1.5]],
      },
      {
        module_id: "A::1",
        distance_m: 2.5,
        sales_weight: 10,
        placed_product_count: 1,
        weighted_cost: 25,
        path_m: [[0.5, 0.5], [2.5, 0.5], [2.5, 1.25]],
      },
    ],
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
      elements: [{ element_id: "ENTRY", element_type: "picker_entry", x_m: 0.25, y_m: 0.25, width_m: 0.5, depth_m: 0.5 }],
    },
  },
};

const model = buildPlanogramDigitalTwinModel(engineResult, candidate);
assert(model?.route?.available, "Route evidence must reach the digital twin model.");
assert(JSON.stringify(model.route.pickerEntryM) === JSON.stringify([0.5, 0.5]), "Picker origin was lost.");
assert(model.route.hotspots.length === 2, "Route hotspots were not projected.");
assert(model.route.hotspots[0].moduleId === "PALLET::1", "Hotspot ordering must remain backend-authoritative.");
assert(model.route.hotspots[0].pathM.length === 4, "Shortest-path polyline was lost.");
assert(model.modules.find((row) => row.key === "PALLET::1")?.routeHotspot?.rank === 1, "Hotspot did not bind to exact spatial module.");
assert(model.modules.find((row) => row.key === "A::1")?.routeDistanceM === 2.5, "Module distance did not bind to exact spatial module.");
assert(PLANOGRAM_DIGITAL_TWIN_LIMITS.maxVisibleRouteHotspots <= 12, "Route hotspot rendering cap is too high.");

const canonical = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
const sharedRenderer = fs.readFileSync("src/modules/planogram/PlanogramTwinSceneRenderer.jsx", "utf8");
const css = fs.readFileSync("src/modules/planogram/planogram-digital-twin.css", "utf8");
const routeCss = fs.readFileSync("src/modules/planogram/planogram-digital-twin-routes.css", "utf8");

for (const needle of ["eay-twin-route-path", "routeHotspot", "pickerEntryM", "RouteHotspots"]) {
  assert(canonical.includes(needle), `Canonical route explainability contract missing: ${needle}`);
}
for (const needle of ["addRouteLines", "sceneModel.route?.hotspots", "hotspot.pathM"]) {
  assert(sharedRenderer.includes(needle), `Shared 3D route explainability contract missing: ${needle}`);
}
assert(css.startsWith('@import "./planogram-digital-twin-routes.css";'), "Canonical twin CSS does not load route overlay styles.");
for (const needle of ["eay-twin-route-path", "eay-twin-route-origin", "is-route-hotspot", "@media (forced-colors: active)"]) {
  assert(routeCss.includes(needle), `Route overlay style contract missing: ${needle}`);
}

console.log("Planogram route explainability unified digital twin flow: PASS");
