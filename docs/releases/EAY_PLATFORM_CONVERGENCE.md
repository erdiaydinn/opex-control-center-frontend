# EAY Platform Convergence Evidence

This document records repository-level convergence evidence only. It does not declare production readiness and it does not authorize a merge to `main` or any production activation.

## Cumulative platform line

Canonical branch: `release/platform-convergence-v0.1`

Composed product/security lineage currently includes:

- frozen Security/Core Phase 1 authority;
- Workforce/Hiring V32;
- Inventory synchronized to current Workforce;
- DockOS production runtime delta;
- Budget Intelligence v1 through Alembic `0014_budget_rls_controls`;
- Academy canonical v1 through Alembic `0015_academy_foundation` -> `0016_academy_audit_idempotency` in the existing single Core API runtime.

## Verified evidence before this evidence commit

- Dedicated DockOS production convergence passed four-worker startup/load, runtime metrics, database interruption fail-closed, recovery, PostgreSQL restart recovery, and combined Workforce/DockOS backup-restore on cumulative head `2b22aa460ab9241fc4586530554bee8d55dc32fc`.
- Budget Intelligence PostgreSQL foundation passed on the cumulative line after branch-to-branch composition, including `alembic upgrade head`, Budget unit contracts, canonical routes/permissions, ENABLE + FORCE RLS, and a runtime role without `BYPASSRLS`.
- Budget's SQL-heavy files retain the canonical Budget CI's E501 exception as a narrowly scoped Ruff per-file policy. Other Ruff classes remain enabled.
- Budget runtime SQL was security-reviewed against the central fail-closed data-access guard. Eighteen Budget SQL-capable functions are explicitly registered with exact execution-call counts covering 53 real database execution calls. Static SQL provenance and bound-parameter guards remain enabled; no dynamic SQL exemption was added.
- Academy was first composed and validated on child branch `release/platform-convergence-academy-v0.1`, then PR #78 passed its own merge-result Academy convergence gate before branch-to-branch merge into this parent. `main` was not targeted.
- Academy uses the existing `app.main` runtime; standalone `main_academy.py` was intentionally not carried forward.
- Academy migrations were rebased after Budget to preserve one Alembic head: `0014_budget_rls_controls` -> `0015_academy_foundation` -> `0016_academy_audit_idempotency`.
- Academy FORCE RLS and runtime `NOBYPASSRLS` posture passed, along with Academy lifecycle/concurrency tests, frontend/Core API build, and PostgreSQL dump/restore evidence.
- Academy runtime SQL was reviewed under the same central fail-closed guard: 32 SQL-capable functions covering 54 database execution calls are exact-count locked. Dynamic SQL rejection, static SQL literal checks and direct-driver rejection remain enabled; no broad Academy SQL exemption was added.
- Full Platform Core regression was isolated onto a clean PostgreSQL/Redis state after a prior shared-state duplicate-slug false failure exposed CI state contamination. The clean-state full regression passed before Academy was merged into the parent.
- All one-shot write-capable Budget/Academy port, formatting and SQL-registration workflows self-deleted and are absent from the resulting repository tree.

## Current validation requirement

Every change to this convergence line must remain fail-closed until the same exact head passes the authoritative repository gates, including Platform Core CI, EAY Platform Convergence, dedicated DockOS production convergence, and EAY Academy Convergence. Module-specific gates may add evidence but do not replace repo-wide release convergence.

## External production acceptance remains open

Repository convergence does not replace live corporate evidence. Remaining external acceptance includes, among other items, corporate OIDC/SSO, live BigQuery production evidence, physical mobile/Zebra/GPS acceptance, real HR/finance inputs and reconciliation, Planogram physical truth, managed staging/DR, and Academy media/CDN/content/entitlement/operational acceptance.
