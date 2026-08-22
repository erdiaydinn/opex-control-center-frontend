import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_ECONOMICS_MESSAGES } from "../src/platform/i18n/planogramEconomicsMessages.js";
import {
  normalizePlanogramEconomicsAssumptions,
  safePlanogramCandidateEconomicsPreview,
  safePlanogramEconomicsPreview,
} from "../src/modules/planogram/planogramEconomicsAssumptions.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const localeCodes = SUPPORTED_LOCALES.map((locale) => locale.code);
const englishKeys = Object.keys(PLANOGRAM_ECONOMICS_MESSAGES.en).sort();
for (const locale of localeCodes) {
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

const fingerprint = "a".repeat(64);
const safeCandidateResponse = {
  preview_only: true,
  production_release_allowed: false,
  physical_relocation_execution_allowed: false,
  installation_approval_allowed: false,
  capex_approval_allowed: false,
  finance_approval_allowed: false,
  investment_decision_allowed: false,
  realized_savings_proven: false,
  candidate_selection_authority: "server_recomputed_fingerprint_match_only",
  result: {
    available: true,
    preview_only: true,
    layout_fingerprint: fingerprint,
    production_evidence: false,
    finance_approved: false,
    investment_decision_allowed: false,
    realized_savings_proven: false,
    economics: {
      available: true,
      production_evidence: false,
      finance_approved: false,
      investment_decision_allowed: false,
      scenarios: [],
    },
  },
};
if (!safePlanogramCandidateEconomicsPreview(safeCandidateResponse, fingerprint)) {
  fail("Safe fingerprint-bound candidate economics response was rejected.");
}
for (const mutate of [
  (row) => { row.result.layout_fingerprint = "b".repeat(64); },
  (row) => { row.candidate_selection_authority = "client_selected"; },
  (row) => { row.result.realized_savings_proven = true; },
  (row) => { row.result.economics.finance_approved = true; },
]) {
  const forged = structuredClone(safeCandidateResponse);
  mutate(forged);
  if (safePlanogramCandidateEconomicsPreview(forged, fingerprint) !== null) {
    fail("Scenario economics UI accepted fingerprint drift or an authority leak.");
  }
}

const panel = fs.readFileSync("src/modules/planogram/PlanogramEconomicsPanel.jsx", "utf8");
for (const needle of [
  "/v1/planogram/physical-layout-economics-preview",
  "/v1/planogram/physical-layout-candidate-economics-preview",
  "safePlanogramEconomicsPreview",
  "safePlanogramCandidateEconomicsPreview",
  "normalizePlanogramEconomicsAssumptions",
  "canCreate && canApprove",
  "candidate?.order_baskets?.length",
  "layout_fingerprint",
  "economics_fingerprint",
  "source_manifest",
]) {
  if (!panel.includes(needle)) fail(`CFO economics panel contract missing: ${needle}`);
}

const scenario = fs.readFileSync("src/modules/planogram/PlanogramScenarioPortfolio.jsx", "utf8");
for (const needle of [
  "<PlanogramEconomicsPanel",
  "layoutFingerprint={scenarioPreview.fingerprint}",
  "canApprove={canApprove}",
]) {
  if (!scenario.includes(needle)) fail(`Scenario economics composition missing: ${needle}`);
}

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
for (const needle of [
  "<PlanogramEconomicsPanel",
  "<PlanogramScenarioPortfolio",
  "canApprove={canApprovePreview}",
]) {
  if (!studio.includes(needle)) fail(`Planogram Studio economics composition missing: ${needle}`);
}

console.log("Planogram CFO economics UI authority, provenance and scenario fingerprint boundary: PASS");
