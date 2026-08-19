import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_ECONOMICS_MESSAGES } from "../src/platform/i18n/planogramEconomicsMessages.js";
import {
  normalizePlanogramEconomicsAssumptions,
  safePlanogramEconomicsPreview,
} from "../src/modules/planogram/planogramEconomicsAssumptions.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const englishKeys = Object.keys(PLANOGRAM_ECONOMICS_MESSAGES.en).sort();
for (const locale of SUPPORTED_LOCALES) {
  const table = PLANOGRAM_ECONOMICS_MESSAGES[locale];
  if (!table) fail(`Missing Planogram economics locale: ${locale}`);
  const keys = Object.keys(table).sort();
  if (JSON.stringify(keys) !== JSON.stringify(englishKeys)) {
    fail(`Planogram economics locale coverage drifted: ${locale}`);
  }
}

const valid = {
  currency: "eur",
  orders_per_day: { low: 800, base: 1000, high: 1200, source_ref: "bq://orders/30d", attested: true },
  operating_days_per_year: { low: 350, base: 360, high: 365, source_ref: "ops://calendar/2026", attested: true },
  effective_seconds_per_meter: { low: 0.8, base: 1, high: 1.2, source_ref: "study://picker-walk/2026", attested: true },
  loaded_labor_cost_per_hour: { low: 8, base: 10, high: 12, source_ref: "finance://labor-cost/2026", attested: true },
  capex_items: [
    { label: "Fixture move", amount: 5000, currency: "EUR", source_ref: "quote://fixture/001", attested: true },
  ],
};
const normalized = normalizePlanogramEconomicsAssumptions(valid);
if (!normalized || normalized.currency !== "EUR") fail("Valid economics assumptions were rejected.");

for (const forged of [
  { ...valid, finance_approved: true },
  { ...valid, investment_decision_allowed: true },
  { ...valid, realized_savings_proven: true },
]) {
  if (normalizePlanogramEconomicsAssumptions(forged) !== null) {
    fail("Client economics boundary accepted a forged authority field.");
  }
}

const safeResponse = {
  preview_only: true,
  production_release_allowed: false,
  physical_relocation_execution_allowed: false,
  installation_approval_allowed: false,
  capex_approval_allowed: false,
  finance_approval_allowed: false,
  investment_decision_allowed: false,
  realized_savings_proven: false,
  result: {
    production_authority: false,
    physical_relocation_authority: false,
    installation_approved: false,
    capex_approved: false,
    finance_approved: false,
    investment_decision_allowed: false,
    realized_savings_proven: false,
    economics: {
      production_evidence: false,
      finance_approved: false,
      investment_decision_allowed: false,
    },
  },
};
if (!safePlanogramEconomicsPreview(safeResponse)) fail("Safe economics response was rejected.");
for (const mutate of [
  (row) => { row.realized_savings_proven = true; },
  (row) => { row.capex_approval_allowed = true; },
  (row) => { row.result.finance_approved = true; },
  (row) => { row.result.economics.production_evidence = true; },
]) {
  const forged = structuredClone(safeResponse);
  mutate(forged);
  if (safePlanogramEconomicsPreview(forged) !== null) {
    fail("Economics UI accepted an authority leak from the server response.");
  }
}

const panel = fs.readFileSync("src/modules/planogram/PlanogramEconomicsPanel.jsx", "utf8");
for (const needle of [
  "/v1/planogram/physical-layout-economics-preview",
  "safePlanogramEconomicsPreview",
  "normalizePlanogramEconomicsAssumptions",
  "canCreate && canApprove",
  "candidate?.order_baskets?.length",
  "economics_fingerprint",
  "source_manifest",
]) {
  if (!panel.includes(needle)) fail(`CFO economics panel contract missing: ${needle}`);
}

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
if (!studio.includes("<PlanogramEconomicsPanel")) {
  fail("Planogram Studio does not expose the CFO economics panel.");
}

console.log("Planogram CFO economics UI authority and provenance boundary: PASS");
