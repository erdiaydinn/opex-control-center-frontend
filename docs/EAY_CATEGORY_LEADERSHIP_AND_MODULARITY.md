# EAY Category Leadership + Modular Product Contract

## Product rule

EAY must win twice:

1. Every module must be independently purchasable and useful without requiring unrelated modules.
2. When multiple modules are enabled, shared identity/data/event truth may create cross-module intelligence without duplicating authority.

No module may require a customer to license another commercial module merely to perform its core workflow.

## Shared platform capabilities (not commercial-module lock-in)

- Identity / tenant / role authority
- Audit / outbox / notification primitives
- Localization / accessibility / product-quality contract
- Operational Data Collection / Field Registry
- Integration/API/event contracts
- Evidence/readiness boundaries

These are platform capabilities consumed by modules. They are not competing product databases.

## Operational Data Collection / Field Registry

The shared collection capability must support independent use and module composition.

Representative records:

- SKU/product barcode, lot/batch, quantity, expiry, condition
- pallet count/type/capacity/identifier/location
- cabinet/freezer/chiller/HDR/rack/fixture count and measured dimensions
- store/depot physical attributes and Store DNA evidence
- equipment/asset serial, QR/NFC/barcode, condition, ownership and location
- arbitrary tenant-defined operational forms

Required product behavior:

- versioned templates and immutable submission provenance
- tenant/location/actor/device/source/time context bound server-side
- web + managed mobile + scanner + bulk + API ingestion
- offline capture and conflict-safe synchronization
- barcode/QR/NFC/photo/signature/GPS where policy permits
- conditional fields, required fields, range/reference validation and calculations
- reusable reference/master data
- maker-checker / approval workflows for governed datasets
- append-only audit and correction history; no silent overwrite of accepted evidence
- schema/version migration support
- exports/integrations governed by tenant permissions
- module subscriptions consume published records through explicit contracts

A generic form submission is not automatically authoritative product, inventory, Planogram or finance truth. Each consuming module owns promotion rules into its own authority.

## Workforce scheduling truth

The supplied global picker scheduling model is the canonical demand-shaping basis. The scheduling pipeline is separated into:

Demand truth -> shift optimization -> employee assignment -> intraday replan -> outcome feedback.

Hourly demand composes operational task man-hours before assigning people:

- picking
- packing
- hand-off
- PO receiving
- store-transfer receiving
- putaway
- cycle count
- expiry check
- quality check
- replenishment
- outbound transfers where applicable
- returned/cancelled-order putaway where applicable
- fatigue + buffer tasks + break overheads

Shift candidate generation must respect warehouse open/close hours and market-specific allowed shift lengths. Optimization must not silently replace global/market rules with competitor-inspired heuristics.

Category-leadership extensions after canonical demand truth are verified:

- employee availability and preferences
- skill/role eligibility
- contract/legal/rest/break/overtime constraints
- labor cost and overtime risk
- fairness and undesirable-shift balancing
- open-shift / swap workflow
- forecast uncertainty/scenarios
- intraday reforecast and replan
- explainable recommendation delta vs published roster
- immutable optimizer input/output/version evidence

## Competitive product standard

### Workforce
Benchmark against leading HCM/WFM products for forecasting, scheduling, employee self-service, shift marketplace, mobile workflows and compliance. EAY differentiation: darkstore-native demand from actual operational workload components.

### Hiring
Benchmark ATS/CRM leaders for sourcing, structured assessment, candidate experience, scheduling and funnel analytics. EAY differentiation: closed lifecycle through Employee Master, first roster, Academy, retention and operational performance.

### Inventory
Benchmark tier-1 WMS and managed-device workflows for directed work, replenishment, exception handling, offline/scanner ergonomics and orchestration. EAY must remain usable as a standalone inventory product.

### Planogram
Benchmark space-planning leaders for assortment/space optimization, store-specific planning, financial optimization, planogram execution and compliance. EAY differentiation: darkstore picker travel + replenishment + availability + physical constraints.

### DockOS
Benchmark dock/yard platforms for carrier self-service, appointment scheduling, gate/driver workflows, yard visibility, dwell, scorecards and alerts. Standalone DockOS must not require Inventory.

### Budget Intelligence
Benchmark enterprise planning products for driver-based planning, scenarios, rolling forecasts, allocations, approvals and variance analysis. Standalone finance authority must not depend on operational modules; integrations add richer drivers only.

### Academy
Benchmark enterprise learning/skills platforms for learning paths, assessments, skill graph, proficiency, recommendations, collaborative authoring and analytics. Academy must remain fully usable standalone; Workforce linkage enriches role/skill targeting.

### Jarvis / KPI / Insight
Benchmark governed conversational BI and proactive analytics. Standalone analytics works over explicitly connected governed sources; cross-module use adds EAY operational graph intelligence.

## Roadmap gate

Before creating any feature, answer both:

1. Does it close a verified customer/product gap or production acceptance blocker?
2. Does it preserve standalone module value and shared-authority boundaries?

If either answer is no, defer it.
