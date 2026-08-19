import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_SCENARIO_MESSAGES } from "../src/platform/i18n/planogramScenarioMessages.js";
import {
  buildPlanogramScenarioPortfolio,
  safePhysicalLayoutPortfolioResponse,
} from "../src/modules/planogram/planogramScenarioPortfolio.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const englishKeys = Object.keys(PLANOGRAM_SCENARIO_MESSAGES.en).sort();
for (const { code } of SUPPORTED_LOCALES) {
  const table = PLANOGRAM_SCENARIO_MESSAGES[code];
  if (!table) fail(`Missing Planogram scenario locale: ${code}`);
  if (JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(englishKeys)) {
    fail(`Planogram scenario locale coverage drifted: ${code}`);
  }
}

function candidate(label, fingerprint, moved, values) {
  return {
    label,
    layout_fingerprint: fingerprint,
    moved_module_count: moved,
    moved_modules: Array.from({ length: moved }, (_, index) => `M-${index + 1}`),
    production_authority: false,
    tour_p95_m: values.p95,
    tour_average_m: values.avg,
    objective: {
      hard_violation_count: 0,
      weighted_unplaced_sales: values.unplacedSales,
      unplaced_sku_count: values.unplacedSkus,
      tour_unsimulated_order_count: 0,
      tour_p95_m: values.p95,
      tour_average_m: values.avg,
      coverage_shortfall: values.coverage,
      brand_fragmentation: values.brand,
      capacity_pressure: 0,
    },
  };
}

const baseline = candidate("baseline", "fp-baseline", 0, {
  p95: 40, avg: 35, unplacedSales: 10, unplacedSkus: 1, coverage: 2, brand: 1,
});
const selected = candidate("swap::A<->B", "fp-selected", 2, {
  p95: 30, avg: 25, unplacedSales: 0, unplacedSkus: 0, coverage: 0, brand: 1,
});
const fastest = candidate("swap::A<->C", "fp-fast", 2, {
  p95: 20, avg: 18, unplacedSales: 5, unplacedSkus: 1, coverage: 0, brand: 2,
});
const quality = candidate("swap::B<->C", "fp-quality", 4, {
  p95: 35, avg: 30, unplacedSales: 0, unplacedSkus: 0, coverage: 0, brand: 0,
});
const dominated = candidate("swap::C<->D", "fp-dominated", 4, {
  p95: 50, avg: 45, unplacedSales: 12, unplacedSkus: 2, coverage: 3, brand: 3,
});

const result = {
  production_authority: false,
  physical_relocation_authority: false,
  installation_approved: false,
  capex_approved: false,
  physical_layout_optimizer: {
    production_authority: false,
    physical_relocation_authority: false,
    installation_approved: false,
    selected_layout_fingerprint: selected.layout_fingerprint,
    baseline_layout_fingerprint: baseline.layout_fingerprint,
    candidates: [baseline, selected, fastest, quality, dominated],
  },
};

const portfolio = buildPlanogramScenarioPortfolio(result);
if (!portfolio.available) fail("Scenario portfolio was not produced from valid V5 candidates.");
if (portfolio.globalOptimumClaim !== false || portfolio.capexCompared !== false) {
  fail("Scenario portfolio crossed global-optimum or CAPEX truth boundary.");
}
if (portfolio.frontier.some((row) => row.layout_fingerprint === dominated.layout_fingerprint)) {
  fail("Dominated V5 candidate leaked into the Pareto frontier.");
}
if (!portfolio.plans.some((plan) => plan.roles.includes("baseline"))) fail("Baseline plan missing.");
if (!portfolio.plans.some((plan) => plan.roles.includes("engineSelected"))) fail("Engine-selected plan missing.");
if (!portfolio.plans.some((plan) => plan.roles.includes("fastestRoute") && plan.candidate.layout_fingerprint === "fp-fast")) {
  fail("Fastest-route decision role did not use real route metrics.");
}
if (!portfolio.plans.some((plan) => plan.roles.includes("qualityFirst"))) fail("Quality-first plan missing.");
if (portfolio.plans.some((plan) => plan.productionAuthority !== false || plan.executionAuthority !== false)) {
  fail("Scenario plan gained execution or production authority.");
}

const safeResponse = {
  preview_only: true,
  production_release_allowed: false,
  physical_relocation_execution_allowed: false,
  installation_approval_allowed: false,
  capex_approval_allowed: false,
  result,
};
if (!safePhysicalLayoutPortfolioResponse(safeResponse)) fail("Safe V5 portfolio response was rejected.");
for (const mutate of [
  (row) => { row.capex_approval_allowed = true; },
  (row) => { row.result.physical_relocation_authority = true; },
  (row) => { row.result.physical_layout_optimizer.installation_approved = true; },
]) {
  const forged = structuredClone(safeResponse);
  mutate(forged);
  if (safePhysicalLayoutPortfolioResponse(forged) !== null) {
    fail("Scenario UI accepted an authority leak.");
  }
}

const component = fs.readFileSync("src/modules/planogram/PlanogramScenarioPortfolio.jsx", "utf8");
for (const needle of [
  "/v1/planogram/physical-layout-search-preview",
  "safePhysicalLayoutPortfolioResponse",
  "buildPlanogramScenarioPortfolio",
  "candidate?.order_baskets?.length",
  "layout_fingerprint",
]) {
  if (!component.includes(needle)) fail(`Scenario UI contract missing: ${needle}`);
}
const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
if (!studio.includes("<PlanogramScenarioPortfolio")) {
  fail("Planogram Studio does not expose the V5 scenario portfolio.");
}

console.log("Planogram V5 Pareto decision-portfolio boundary: PASS");
