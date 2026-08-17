import assert from "node:assert/strict";
import fs from "node:fs";

import { planogramExperienceMessageCoverage } from "../src/platform/i18n/planogramExperienceMessages.js";
import { buildPlanogramScene } from "../src/modules/planogram/planogramSceneModel.js";

const LOCALES = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const coverage = planogramExperienceMessageCoverage(LOCALES);
for (const locale of LOCALES) {
  assert.deepEqual(coverage.missing[locale], [], `Missing Planogram 2D/3D messages for ${locale}`);
  assert.deepEqual(coverage.extra[locale], [], `Unexpected Planogram 2D/3D messages for ${locale}`);
}

const fixture = {
  production_ready: false,
  planogram: {
    store_code: "TEST",
    aisles: [
      {
        aisle_id: "A",
        row: 1,
        position: 1,
        modules: [
          {
            module_id: 1,
            side: "L",
            module_type: "regular_shelf",
            module_width_cm: 100,
            module_height_cm: 70,
            module_depth_cm: 50,
            shelves: [
              {
                shelf_no: 1,
                shelf_width_cm: 100,
                shelf_height_cm: 35,
                shelf_depth_cm: 50,
                products: [
                  {
                    sku: "SKU-1",
                    product_name: "Exact product",
                    width_cm: 10,
                    height_cm: 20,
                    depth_cm: 8,
                    facing: 2,
                    used_width_cm: 22,
                    position_order: 1,
                    dimension_source: "master",
                  },
                  {
                    sku: "SKU-2",
                    product_name: "Second exact product",
                    width_cm: 8,
                    height_cm: 18,
                    depth_cm: 7,
                    facing: 1,
                    used_width_cm: 9,
                    position_order: 2,
                    dimension_source: "master",
                  },
                ],
              },
              {
                shelf_no: 2,
                shelf_width_cm: 100,
                shelf_height_cm: 35,
                shelf_depth_cm: 50,
                products: [],
              },
            ],
          },
        ],
      },
    ],
  },
};

const scene = buildPlanogramScene(fixture);
assert.equal(scene.renderable, true);
assert.equal(scene.modules.length, 1);
assert.equal(scene.geometryReadyCount, 1);
assert.equal(scene.productCount, 2);
assert.equal(scene.modules[0].widthCm, 100);
assert.equal(scene.modules[0].heightCm, 70);
assert.equal(scene.modules[0].shelves[0].products[0].xCm, 0);
assert.equal(scene.modules[0].shelves[0].products[1].xCm, 22);
assert.equal(scene.modules[0].shelves[0].products[0].facing, 2);

const missingDepth = structuredClone(fixture);
delete missingDepth.planogram.aisles[0].modules[0].shelves[0].products[0].depth_cm;
const blocked = buildPlanogramScene(missingDepth);
assert.equal(blocked.modules[0].geometryReady, false, "Missing product depth must fail closed");

const overflow = structuredClone(fixture);
overflow.planogram.aisles[0].modules[0].shelves[0].products[1].used_width_cm = 90;
const overflowScene = buildPlanogramScene(overflow);
assert.equal(overflowScene.modules[0].geometryReady, false, "Inconsistent used width must fail closed");

const noPlan = buildPlanogramScene({ production_ready: false, planogram: null });
assert.equal(noPlan.renderable, false);

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
const experience = fs.readFileSync("src/modules/planogram/PlanogramExperience.jsx", "utf8");
assert.match(studio, /PlanogramExperience/);
assert.match(experience, /OrbitControls/);
assert.match(experience, /prefers-reduced-motion/);
assert.match(experience, /productionAuthorityBlocked/);
assert.doesNotMatch(experience, /Spline|iframe|postMessage\(|access_token/);

console.log("MASTER_27_SCENE_MODEL=PASS");
console.log("MASTER_27_EXACT_GEOMETRY_FAIL_CLOSED=PASS");
console.log("MASTER_27_10_LOCALES=PASS");
console.log("MASTER_27_NO_LEGACY_VISUAL_AUTHORITY=PASS");
