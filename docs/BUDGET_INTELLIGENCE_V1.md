# EAY Budget Intelligence — Production Finance Foundation

## Canonical architecture

Budget Intelligence is a bounded context inside Platform Core. It reuses the platform identity gateway, OIDC/JWKS verification, active tenant membership, permission assignments, trusted proxy boundary, runtime PostgreSQL role, Redis/platform health and backup controls. It does not create a second authentication or database trust root.

Canonical finance chain:

`Budget Plan → Fiscal Period → Cost Center → Budget Line → Purchase Request → Approval → PO → Invoice → Actual → Commitment → Forecast → Variance`

Excel/CSV/XLSX is ingestion only. The authoritative state is PostgreSQL.

## Financial invariants

- Every Budget row is bound to a real Platform Core tenant.
- Cost-center-bearing aggregates are protected by FORCE RLS using tenant + authorized cost-center scope.
- Budget Plan starts as `DRAFT`. A second actor must activate it before Purchase Requests can be submitted.
- Fiscal periods in the same plan cannot overlap; a PostgreSQL advisory-lock + overlap trigger makes this race-safe without introducing an extra database extension dependency.
- Budget Line definition is created while the plan is DRAFT; Purchase Request requires an ACTIVE plan and an OPEN period.
- Purchase Request creation locks the Budget Line and fails closed if Actual + open Commitment + uncommitted submitted/approved requests + the new request exceeds the line budget.
- PR maker cannot approve their own request.
- PR approver cannot create the PO for the same request.
- PO creator cannot post the invoice for the same PO.
- PO/invoice supplier identity mismatches fail closed.
- Amount mismatch creates a reconciliation HOLD; it is never silently overwritten.
- Reconciliation acceptance is independently authorized and cannot push the Budget Line over budget.
- Positive/negative accounting adjustments are append-only, four-eyes approved Actual events; original Actual and approval evidence are immutable.
- Open commitments, pending requests, held invoices, pending adjustments and open reconciliation issues block fiscal-period close.
- Open POs and requests have explicit audited cancellation paths so period close cannot become permanently stuck.
- All state-changing commands require a durable `Idempotency-Key` bound to tenant + actor + operation + request payload.
- Financial events are append-only hash chains partitioned by tenant + cost center; scoped auditors can verify the exact chain they are authorized to see.
- Export requires an explicit Budget export permission and emits scoped export evidence.

## Permissions

The module does not introduce a parallel finance-role system. Existing Platform Core permission assignments remain authoritative. Budget permissions may be assigned with either:

- `{"all_cost_centers": true}`
- `{"cost_center_ids": ["<uuid>", ...]}`

Master-data, fiscal-close and ingestion permissions require all-cost-center authority in this foundation. Operational read/write permissions can remain cost-center scoped.

## Controlled ingestion

Supported upload formats: UTF-8 CSV/TSV/TXT and XLSX.

Controls include bounded file/row/column sizes, formula rejection, deterministic normalization/fingerprinting, explicit external source identity, preview-before-commit, duplicate detection, staging before materialization, and savepoint-scoped row materialization.

## External system boundary

Corporate identity, gateway trust and backup trust are inherited from Platform Security Phase 1. ARIBA/SAP/BigQuery are represented by controlled source contracts and canonical external identities. Production endpoint URLs, service-account material and corporate IdP secrets are deployment inputs and must be supplied through the existing secret-management boundary; the application fails closed rather than embedding or inventing credentials.

## Canonical repository line

- Base: `feature/phase-1-security-hardening` @ `6a1ab7d8e150a8392ba144c4a3e49dcc73130a1d`
- Product branch: `product/budget-intelligence-v1`
- Budget migrations: `0009_budget_finance_foundation` → `0010_budget_workflow_controls`

`product/budget-intelligence-foundation` and `product/budget-intelligence-production` are historical/superseded pointers only.