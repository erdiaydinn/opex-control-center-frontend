# EAY Customer Promise & Delivery Experience — Product Lifecycle Item 6

## Product intent

Customer Promise & Delivery Experience makes the customer-visible commitment measurable and recoverable without creating a shadow OMS, courier platform, CRM customer master or finance executor.

The canonical loop is:

`Promise → Fulfillment events → Actual outcome → Deviation → Evidence / cause status → Recovery proposal → Approval → downstream execution → learning`

Item 6 owns the promise/evidence contract up to approved recovery intent. The configurable workflow/policy engine belongs to Item 7 and may later orchestrate rules without weakening the truth and approval boundaries defined here.

## Authority boundaries

- The external OMS/order source remains authoritative for order identity and order lifecycle.
- Delivery/courier sources remain authoritative for delivery observations.
- EAY stores an immutable, versioned copy of what was promised to the customer and source provenance for that promise.
- EAY delivery events are append-only imported evidence. They do not become a second fulfillment state machine.
- Root cause is never silently inferred as fact. A `hypothesis` remains a hypothesis; a `verified_evidence` assertion requires an evidence reference.
- Customer compensation is a proposal and approval record only. Financial recovery cannot bypass human approval and this capability contains no silent money-execution path.
- KPI formulas are not defined here. Promise adherence, lateness, failed-delivery, instruction-compliance, fee-discrepancy and recovery metrics must be registered in the governed KPI/semantic layer before they become authoritative reporting truth.

## Privacy and data minimization

The repository contract intentionally does not contain customer name, phone, postal address, door code or raw delivery-instruction text. Customer-sensitive instructions stay in their authoritative protected system and are represented here only through an opaque reference and SHA-256 fingerprint. External order references are operational references, not a customer profile.

A future customer-history use case must use a policy-approved pseudonymous subject reference and explicit retention/access rules. Item 6 does not create a marketing CRM or behavioral customer profile by default.

## Promise contract

Every promise version contains tenant, promise id, external order reference, immutable version/supersession, source system and source record, commit time, promised delivery window, service level, optional customer-visible fee and optional protected instruction reference/fingerprint.

Changing ETA/window, fee or another customer-visible commitment creates a new immutable promise version. Previous promise versions are never overwritten, because later analysis must distinguish what the customer actually saw at each point in time.

## Delivery evidence and deterministic evaluation

Delivery events carry source system, source event reference, event time, idempotency key and payload fingerprint. The first evaluator is deterministic and compares a selected promise version with an authoritative actual-outcome snapshot.

Timing semantics are explicit: delivery inside the promised window is `on_time`; before the start is `early`; after the end is `late`; failed/cancelled/in-progress remain separate outcomes. Timing delta is negative for early minutes, positive for late minutes and zero for on-time delivery. Fee variance is computed only when both sides use the same currency. Delivery-instruction compliance can be met, breached, unknown or not applicable, and an instruction breach cannot be asserted when no instruction promise exists.

The evaluator does not decide why the deviation happened.

## Cause and recovery

Cause assertions have two truth states:

- `verified_evidence`: evidence reference required; model-confidence fields are forbidden;
- `hypothesis`: may carry bounded confidence but may not be presented as verified truth.

Examples of possible evidence sources include a governed Field Intelligence verification, authoritative Workforce capacity observation, Inventory exception record, DockOS event or external delivery-platform incident. Optional integrations enrich explanation but are not required for the core Customer Promise capability.

Recovery requests can represent customer communication, fee refund, credit, reorder or manual review. Fee refund and credit require a monetary amount and human approval. Rejected recovery cannot execute. An approved recovery is only authorization for a separately governed downstream executor; this domain does not perform payment/accounting mutations.

## Standalone and cross-module value

The capability can operate with only an external OMS/delivery integration and EAY Platform Core. When other modules are licensed, they may contribute evidence or explanation without becoming mandatory dependencies:

- Workforce: effective-capacity/pressure evidence;
- Inventory: stock/substitution/exception evidence;
- Planogram: physical/findability evidence when governed;
- DockOS: inbound disruption evidence;
- Field Intelligence: physical verification missions;
- Jarvis: explanation and recovery proposal using only authorized evidence;
- Academy: remediation/training links for verified recurrent process gaps;
- KPI/Insight: governed promise/recovery metrics.

No integration may silently promote correlation into causal truth.

## Repository acceptance for Item 6

Repository-ready acceptance requires immutable promise revisions, deterministic early/on-time/late/failed/cancelled evaluation, exact fee comparison, instruction-compliance truth boundaries, cause fact-vs-hypothesis separation, approval-bound financial recovery, PII-minimized models, PostgreSQL append-only persistence, tenant RLS, cross-tenant zero-read/write proof, duplicate-event/idempotency constraints, restart durability and isolated backup/restore rehearsal.

Passing repository CI is not customer, field or production acceptance.

## External production acceptance still required

Production readiness requires real OMS and delivery event contracts, production identity/tenant mapping, source-event replay/idempotency testing, real customer-visible promise capture, fee source reconciliation, protected instruction access, support/operations UAT, notification delivery, compensation-system integration with maker-checker controls, retention/privacy-owner approval, production-shape load/DR and controlled pilot evidence.

`production_ready` remains false until those external gates pass.
