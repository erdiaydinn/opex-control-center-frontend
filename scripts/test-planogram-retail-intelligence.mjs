import assert from "node:assert/strict";
import fs from "node:fs";

import { normalizeCandidateBundle } from "../src/modules/planogram/planogramCandidateBundle.js";

const base = {
  products: [{ sku: "SKU-1", width_cm: 10 }],
  layout: { store_code: "STORE-1", aisles: [] },
  store_dna: { store_code: "STORE-1" },
  mode: "HYBRID",
  order_baskets: [],
  retail_intelligence: {
    store_code: "STORE-1",
    total_shelf_width_cm: 100,
    substitution_edges: [],
    historical_pairs: [],
    realogram_events: [],
  },
};

const normalized = normalizeCandidateBundle(base);
assert.ok(normalized);
assert.ok(normalized.retail_intelligence);
assert.equal(Object.keys(normalized).includes("retail_intelligence"), false);
assert.equal(JSON.stringify(normalized).includes("retail_intelligence"), false);

const unsafe = normalizeCandidateBundle({
  ...base,
  products: [{ sku: "SKU-1", customer_id: "customer-1" }],
});
assert.equal(unsafe, null);

const unsafeEvidence = normalizeCandidateBundle({
  ...base,
  retail_intelligence: {
    ...base.retail_intelligence,
    historical_pairs: [{ customer_id: "customer-1" }],
  },
});
assert.equal(unsafeEvidence, null);

const panel = fs.readFileSync(
  new URL("../src/modules/planogram/PlanogramRetailIntelligencePanel.jsx", import.meta.url),
  "utf8"
);
assert.match(panel, /retail-intelligence-preview/);
assert.match(panel, /market_leadership_claim_allowed !== false/);
const studio = fs.readFileSync(
  new URL("../src/modules/planogram/PlanogramStudio.jsx", import.meta.url),
  "utf8"
);
assert.match(studio, /PlanogramRetailIntelligencePanel/);
console.log("PLANOGRAM_RETAIL_INTELLIGENCE_UI=PASS");
console.log("PLANOGRAM_RETAIL_EVIDENCE_ENUMERABLE=FALSE");
console.log("PLANOGRAM_RETAIL_PII_GUARD=PASS");
