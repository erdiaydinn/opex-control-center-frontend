# EAY Portfolio Category Leadership Gate

## Purpose

This contract turns the Rise Era strategy into a repository-enforced portfolio rule.

The platform must win at two levels simultaneously:

1. Every commercial module must remain independently purchasable and useful for its core workflow.
2. Optional cross-module composition may create a stronger EAY operating system, but it may not become commercial lock-in or a second authority model.

The canonical machine-readable contract is:

`config/eay_portfolio_category_leadership.json`

The validator is:

`scripts/validate_portfolio_category_leadership.py`

The CI authority is:

`EAY Portfolio Category Leadership Gate`

## Three priority levels

Every module/capability has exactly one P0, one P1 and one P2 contract.

- **P0 — production acceptance/foundation:** the capability or real-environment evidence that blocks an honest production claim.
- **P1 — verified category parity:** capability depth expected to compete with the strongest products in the category.
- **P2 — EAY leadership moat:** differentiated capability or measurable outcome that should make EAY better, not merely equivalent.

A module may not silently drop one of these levels. CI requires all three and preserves the existing module inventory from `config/eay_category_leadership_gates.json`.

## Implementation truth vs production evidence

Every gate records two separate states:

`implementation_state`

- `implemented_repository`
- `partial_repository`
- `planned`

`production_evidence_state`

- `not_required`
- `missing_external`
- `verified_external`

This separation is mandatory. Repository implementation, green CI, synthetic load, fixtures or mocked integrations do not become real field/staging/production evidence merely because they are repeatable.

`verified_external` requires explicit evidence references. References containing synthetic/mock/fake/fixture semantics are rejected by the validator.

## Claim rules

A module may not claim category parity while any P0/P1 gate is incomplete or missing required external evidence.

A module may not claim category leadership while any P0/P1/P2 gate is incomplete or missing required external evidence.

A module may not claim production readiness while any P0 implementation or required external evidence remains unresolved.

The portfolio-level parity, leadership and production-ready claims remain false until separately evidenced.

## Standalone commercial module rule

For every `commercial_module`:

- `standalone_sale_required=true`
- `required_commercial_dependencies=[]`
- core workflow cannot require licensing another commercial EAY module
- `optional_integrations` may enrich the product but must not become mandatory authority

Shared identity, tenant/RLS, audit, localization, accessibility, notification/accountability, evidence and semantic primitives are platform capabilities rather than separate commercial dependency lock-in.

Hiring remains compatible with the one Employee Master lifecycle without forcing a Workforce commercial license: the authoritative employee identity is a shared domain/platform contract, not a second Hiring employee database.

## Benchmark truth boundary

The benchmark product lists are comparison targets only. Their presence in the contract does **not** assert that every named product currently implements every listed capability.

Competitive claims must be refreshed from authoritative market research before being used externally. The repository contract stores what EAY intends to match or exceed; it does not fabricate competitor evidence.

## Current portfolio shape

The initial contract contains 16 product/platform areas and 48 P0/P1/P2 gates covering:

- Platform Core
- Security
- EAY AI Core
- Jarvis
- Repository Intelligence
- KPI / Insight / Analytics
- Planogram
- Workforce
- Hiring / Recruitment
- Inventory
- DockOS
- Budget Intelligence
- Academy
- Field Intelligence
- Audit
- Shared Services

Each gate includes capability intent, acceptance condition, evidence type, repository implementation state, external-evidence state and blocker.

## Update discipline

A future change may move a gate from `planned` to `partial_repository` or `implemented_repository` only when repository evidence exists.

A future change may move `missing_external` to `verified_external` only when exact external evidence references exist and the evidence is not synthetic/test-only.

A new commercial dependency may not be added to make a module appear complete. If a capability is only optional cross-module value, it belongs under `optional_integrations` and the standalone core path must continue to work.

A benchmark or roadmap feature should be added only when it closes one of three things:

1. a verified production acceptance blocker,
2. a verified category-parity gap,
3. a measurable EAY differentiation opportunity.

Anything else is backlog noise and should not bypass this gate.
