# EAY Budget Intelligence — Canonical Finance Foundation

## Architecture

Budget Intelligence is a bounded context inside Platform Core. It reuses the existing OIDC/JWKS principal, active tenant membership, DB-backed permission assignments, transaction-local tenant context, runtime PostgreSQL role, platform audit, trusted gateway boundary and backup controls. It does not introduce a second authentication, tenant or database trust root.

Canonical domain:

`Budget Plan → Fiscal Period → Cost Center → Budget Line → Purchase Request → Approval → PO → Invoice → Actual → Commitment → Forecast → Variance`

PostgreSQL is authoritative. External finance systems and files are ingestion sources, never the ledger.

## Persistence

Migration chain on this branch:

`0008_preauth_provider_resolver`
→ `0009_budget_finance_foundation`
→ `0010_budget_procurement_foundation`
→ `0011_budget_ledger_foundation`
→ `0012_budget_import_foundation`
→ `0013_budget_evidence_foundation`
→ `0014_budget_rls_controls`

The model persists Budget Plan, Fiscal Period, Cost Center, Budget Line, Purchase Request, Approval, Purchase Order, Invoice, Commitment, Actual, Forecast, Reconciliation Issue, Import Batch/Row, Financial Event and durable Budget Command state.

## Tenant and cost-center security

Every Budget table is tenant-bound. `0014_budget_rls_controls` enables and forces PostgreSQL RLS. Tenant-only tables use the existing Platform Core `app.tenant_id` transaction context. Finance aggregates with a cost center additionally require server-derived `app.budget_cost_center_ids` scope.

Budget action permissions are registered in the canonical Platform Core permission catalog. Non-superadmin users require explicit DB assignments. Assignment scope is either:

- `{"all_cost_centers": true}`
- `{"cost_center_ids": ["<uuid>", ...]}`

Empty, malformed or missing cost-center scope fails closed. Master-data, import, period close and export require all-cost-center authority.

## Workflow invariants

The service applies row locks and one database transaction per command.

- Budget Plan creator cannot activate their own plan.
- Plan activation requires at least one Fiscal Period and Budget Line.
- Fiscal Period creation is serialized by a PostgreSQL advisory transaction lock and rejects overlapping ranges.
- Budget Lines are defined only while the plan is DRAFT and must reference a period from the same plan.
- Purchase Request requires ACTIVE plan + OPEN period.
- Purchase Request creation locks the Budget Line and rejects exposure above budget.
- PR maker cannot approve their own request.
- PR approver cannot create the resulting PO.
- PO creator cannot post an invoice against that PO.
- PO/request amount or supplier mismatch becomes `RECONCILIATION_HOLD`; no Commitment is opened until independently resolved.
- Invoice/PO supplier mismatch or invoice amount above remaining Commitment becomes `HOLD`; no Actual is posted.
- Duplicate invoice identity is unique by tenant + supplier + invoice number and returns conflict without creating a second Actual.
- Accepted PO reconciliation re-checks Budget Line exposure while holding the line lock.
- Held invoices cannot be silently accepted; they must be corrected or rejected.
- Fiscal Period close rejects unresolved requests, reconciliation holds, open commitments, held invoices and open reconciliation issues.

Approval, Actual and Financial Event rows are append-only for the runtime DB role because UPDATE is revoked; DELETE is revoked across Budget tables.

## Durable evidence and idempotency

Every state-changing HTTP command requires `Idempotency-Key`. Durable `budget_command` state binds the key to tenant + actor + operation + canonical payload hash. A completed identical replay returns the recorded response; key reuse for a different command returns conflict.

Finance mutations emit `financial_event` evidence in the same PostgreSQL transaction as the domain mutation. Events form a SHA-256 chain partitioned by tenant + cost center (or the tenant-global chain). Chain assignment is serialized with PostgreSQL advisory transaction locks. Export also emits financial evidence.

Platform Core request audit remains active around the same composed ASGI application, so finance-domain evidence complements rather than replaces platform audit.

## Import and authoritative-source boundary

Source contracts explicitly distinguish `ARIBA`, `SAP`, `BIGQUERY` and `MANUAL`. Non-manual procurement identities must carry reviewed canonical external identifiers before materialization.

Import staging normalizes values, fingerprints rows with the source-system/entity namespace and stores them in PostgreSQL. Batch and row hashes are unique within tenant/source/entity scope, making repeated ingestion idempotent. Spreadsheet parsing is an adapter concern; spreadsheets never become authoritative runtime state.

Real ARIBA/SAP/BigQuery endpoint URLs, service identities, schemas and credentials are not invented in this foundation. They remain deployment/integration inputs behind the explicit adapter boundary.

## Backend truth

The variance read model is calculated from the same PostgreSQL finance state and returns Budget, Actual, open Commitment, latest Forecast and Variance with cost-center/category/supplier/store dimensions. It does not read browser-local state or spreadsheet state.

## UI policy

The existing Budget UI is intentionally untouched in this foundation. The backend contract, database migrations and acceptance gates are established first. A minimal UI can consume these routes only after the backend foundation is accepted.

## Repository topology

- Base: `feature/phase-1-security-hardening` @ `6a1ab7d8e150a8392ba144c4a3e49dcc73130a1d`
- Canonical branch: `product/budget-intelligence-v1`
- `product/budget-intelligence-foundation`: historical/superseded; not finance authority
- `product/budget-intelligence-production`: historical/superseded; not finance authority

No direct merge to `main`. The first PR targets the stable Platform Security Phase 1 branch and remains draft until exact-head PostgreSQL CI is green.

## Production-readiness gaps beyond this foundation

This foundation is not equivalent to production acceptance. Remaining gates include real authoritative finance dataset mapping, corporate source credentials, staging reconciliation against real finance records, backup/restore acceptance, load/concurrency acceptance and controlled finance pilot sign-off. Direct-SQL hardening of workflow invariants beyond the current RLS/least-privilege boundary is also a follow-up defense-in-depth gate before high-trust production use.
