import fs from "node:fs";
import process from "node:process";

import {
  normalizeCandidateBundle,
  PLANOGRAM_CANDIDATE_LIMITS,
} from "../src/modules/planogram/planogramCandidateBundle.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

function bundle(orderBaskets) {
  return {
    products: [{ sku: "SKU-1" }],
    layout: { aisles: [] },
    store_dna: { store_code: "TEST" },
    mode: "hybrid",
    order_baskets: orderBaskets,
  };
}

const normalized = normalizeCandidateBundle(
  bundle([
    { skus: [" sku-1 ", "Sku-2", "sku-1"] },
    { skus: ["SKU-3"] },
  ])
);
if (!normalized) fail("Anonymous order baskets were dropped by candidate normalization.");
if (normalized.mode !== "HYBRID") fail("Preview mode normalization regressed.");
if (normalized.order_baskets.length !== 2) fail("Basket count was not preserved.");
if (normalized.order_baskets[0].skus.join(",") !== "SKU-1,SKU-2,SKU-1") {
  fail("SKU normalization or duplicate quantity evidence regressed.");
}

for (const forbidden of [
  { skus: ["SKU-1"], order_id: "raw-order-id" },
  { skus: ["SKU-1"], customer_id: "raw-customer-id" },
  { skus: ["SKU-1"], email: "person@example.test" },
  { skus: ["SKU-1"], label: "expert" },
]) {
  if (normalizeCandidateBundle(bundle([forbidden])) !== null) {
    fail(`Identity/label field crossed Studio basket boundary: ${Object.keys(forbidden).join(",")}`);
  }
}

if (
  normalizeCandidateBundle(
    bundle([{ skus: Array.from({ length: PLANOGRAM_CANDIDATE_LIMITS.maxSkusPerBasket + 1 }, () => "SKU") }])
  ) !== null
) {
  fail("Oversized basket bypassed bounded Studio normalization.");
}

if (
  normalizeCandidateBundle(
    bundle(Array.from({ length: PLANOGRAM_CANDIDATE_LIMITS.maxBaskets + 1 }, () => ({ skus: ["SKU"] })))
  ) !== null
) {
  fail("Oversized basket collection bypassed bounded Studio normalization.");
}

const withoutBaskets = normalizeCandidateBundle({
  products: [{ sku: "SKU-1" }],
  layout: { aisles: [] },
  store_dna: { store_code: "TEST" },
});
if (!withoutBaskets || withoutBaskets.order_baskets.length !== 0) {
  fail("Missing baskets must remain explicitly empty; synthetic baskets are forbidden.");
}

const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
if (!studio.includes('from "./planogramCandidateBundle.js"')) {
  fail("Planogram Studio is not wired to the canonical candidate-bundle boundary.");
}
if (studio.includes("function normalizeCandidateBundle(")) {
  fail("Planogram Studio retained a stale local normalizer that can drop basket evidence.");
}

console.log("Planogram anonymous basket Studio boundary: PASS");
