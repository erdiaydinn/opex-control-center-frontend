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
    shelf_scan_shelves: [],
    shelf_scan_observations: [],
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

const crossStore = normalizeCandidateBundle({
  ...base,
  layout: { store_code: "STORE-2", aisles: [] },
});
assert.equal(crossStore, null);

const orphanObservation = normalizeCandidateBundle({
  ...base,
  retail_intelligence: {
    ...base.retail_intelligence,
    shelf_scan_observations: [{
      sku: "SKU-1",
      aisle_id: "A",
      module_id: "1",
      shelf_no: "1",
      facing_count: 1,
      confidence: 0.99,
    }],
  },
});
assert.equal(orphanObservation, null);

const blindWithoutBaskets = normalizeCandidateBundle({
  ...base,
  retail_intelligence: {
    ...base.retail_intelligence,
    blind_candidate_a: { planogram: { aisles: [{}] } },
    blind_candidate_b: { planogram: { aisles: [{}] } },
  },
});
assert.equal(blindWithoutBaskets, null);

const panel = fs.readFileSync(
  new URL("../src/modules/planogram/PlanogramRetailIntelligencePanel.jsx", import.meta.url),
  "utf8"
);
assert.match(panel, /retail-intelligence-preview/);
assert.match(panel, /market_leadership_claim_allowed !== false/);
assert.match(panel, /physical_capacity_v2/);
assert.match(panel, /open_action_count/);
assert.match(panel, /resolved_action_count/);
assert.match(panel, /order_baskets: candidate\.order_baskets/);

const messages = fs.readFileSync(
  new URL("../src/platform/i18n/planogramRetailIntelligenceMessages.js", import.meta.url),
  "utf8"
);
assert.match(messages, /fullDepthCapacity/);
assert.match(messages, /actionQueue/);

console.log("PLANOGRAM_RETAIL_INTELLIGENCE_V2_UI=PASS");
console.log("PLANOGRAM_RETAIL_EVIDENCE_ENUMERABLE=FALSE");
console.log("PLANOGRAM_RETAIL_PII_AND_STORE_GUARD=PASS");
console.log("PLANOGRAM_RETAIL_BLIND_SHELF_SCAN_CONTRACT=PASS");
