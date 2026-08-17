import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};

const app = read("src/App.jsx");
const wrapper = read("src/modules/budget-intelligence/BudgetWorkspace.jsx");
const planning = read("src/modules/budget-intelligence/BudgetPlanningWorkspace.jsx");
const routes = read("services/core-api/app/modules/budget/routes.py");
const readModels = read("services/core-api/app/modules/budget/read_models.py");
const migration = read("services/core-api/alembic/versions/0037_budget_planning_authority.py");
const preferences = read("src/platform/preferences/PlatformPreferencesContext.jsx");

assert(
  app.includes('import("./modules/budget-intelligence/BudgetWorkspace.jsx")'),
  "Budget route must lazy-load the canonical BudgetWorkspace"
);
assert(
  !app.includes('import("./modules/budget-intelligence/BudgetIntelligence.jsx")'),
  "App must not route /budget directly to the legacy operational screen"
);
assert(
  wrapper.includes("<BudgetPlanningWorkspace />") && wrapper.includes("<BudgetIntelligence />"),
  "Budget wrapper must preserve operational history while defaulting to real planning"
);
assert(
  wrapper.includes('useState("planning")'),
  "Authoritative planning must be the default Budget product view"
);

for (const route of [
  "/v1/budget/plans",
  "/v1/budget/cost-centers",
  "/v1/budget/periods",
  "/v1/budget/lines",
  "/v1/budget/forecasts",
  "/activate",
  "/workspace",
]) {
  assert(planning.includes(route), `Planning workspace missing canonical route: ${route}`);
}
assert(
  planning.includes('"Idempotency-Key"'),
  "Every Budget planning mutation must use the canonical idempotency boundary"
);
assert(
  planning.includes("activation_snapshot_attested"),
  "Planning UI must distinguish attested activation evidence from reconstruction"
);
assert(
  planning.includes('t("budgetLegacyReconstruction")'),
  "Legacy migration reconstruction must be visibly labelled as non-historical evidence"
);
assert(
  !planning.includes("/budget/summary") && !planning.includes("Ask Budget AI"),
  "Master 28 planning view must not reuse legacy/local-state finance truth"
);
assert(
  !planning.includes(">Master 28<"),
  "Roadmap ordinal must not leak as hard-coded user-facing UI text"
);

for (const fragment of [
  '@router.get("/plans")',
  '@router.get("/cost-centers")',
  '@router.get("/plans/{plan_id}/workspace")',
]) {
  assert(routes.includes(fragment), `Budget routes missing product read-model endpoint: ${fragment}`);
}
assert(
  routes.includes("all_cost_centers=True"),
  "Full planning read model must remain bound to all-cost-center Budget authority"
);
assert(
  readModels.includes("async def plan_snapshot") &&
    readModels.includes("latest_forecast_base_amount") &&
    readModels.includes("planning_snapshot_provenance"),
  "Budget planning read model must expose exact scope, forecast, and provenance"
);
assert(
  readModels.includes("planning_snapshot_provenance='ACTIVATION_TRIGGER'"),
  "Read model must derive activation attestation from provenance, not UI inference"
);

assert(
  migration.includes('ACTIVATION_TRIGGER = "ACTIVATION_TRIGGER"') &&
    migration.includes('LEGACY_RECONSTRUCTION = "LEGACY_MIGRATION_RECONSTRUCTION"'),
  "Migration must preserve activation-vs-reconstruction truth boundary"
);
assert(
  migration.includes("planning_snapshot_at = CURRENT_TIMESTAMP") &&
    migration.includes("NEW.planning_snapshot_at := NEW.activated_at"),
  "Legacy observation time and real activation time must remain distinct"
);

assert(
  preferences.includes("translateProduct(locale, key, params) ?? translate(locale, key, params)"),
  "Platform translation authority must compose product messages centrally"
);

const productMessagesUrl = pathToFileURL(
  path.join(root, "src/platform/i18n/productMessages.js")
).href;
const { PRODUCT_MESSAGES, productMessageCoverage } = await import(productMessagesUrl);
const coverage = productMessageCoverage();
const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
assert(
  JSON.stringify(Object.keys(PRODUCT_MESSAGES)) === JSON.stringify(expectedLocales),
  "Budget product messages must use the canonical 10-locale matrix"
);
for (const locale of expectedLocales) {
  assert(
    Array.isArray(coverage.missing[locale]) && coverage.missing[locale].length === 0,
    `Budget product translations incomplete for ${locale}: ${coverage.missing[locale]}`
  );
}

for (const key of [
  "budgetPlanning",
  "budgetActivationEvidence",
  "budgetSnapshotHash",
  "budgetSnapshotProvenance",
  "budgetLegacyReconstruction",
  "budgetForecast",
]) {
  assert(coverage.referenceKeys.includes(key), `Missing required Budget translation key: ${key}`);
}

console.log("MASTER_28_BUDGET_PLANNING_UI=PASS");
console.log("MASTER_28_CANONICAL_API_BINDING=PASS");
console.log("MASTER_28_10_LOCALE_COVERAGE=PASS");
console.log("MASTER_28_ACTIVATION_PROVENANCE_UI=PASS");
