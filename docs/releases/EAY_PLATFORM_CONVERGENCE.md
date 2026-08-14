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
- Academy canonical v1 through Alembic `0015_academy_foundation` -> `0016_academy_audit_idempotency` in the existing single Core API runtime;
- selective Planogram deterministic foundation + physical-truth gate while preserving the existing EAY Planogram shell and platform identity authority.

## Verified evidence before this evidence commit

- Dedicated DockOS production convergence passed four-worker startup/load, runtime metrics, database interruption fail-closed, recovery, PostgreSQL restart recovery, and combined Workforce/DockOS backup-restore on cumulative head `2b22aa460ab9241fc4586530554bee8d55dc32fc`.
- Budget Intelligence PostgreSQL foundation passed on the cumulative line after branch-to-branch composition, including `alembic upgrade head`, Budget unit contracts, canonical routes/permissions, ENABLE + FORCE RLS, and a runtime role without `BYPASSRLS`.
- Budget runtime SQL was security-reviewed against the central fail-closed data-access guard. Eighteen Budget SQL-capable functions are exact-count locked across 53 real database execution calls; static SQL and dynamic-SQL/direct-driver guards remain enabled.
- Academy was validated on its child and PR merge-result context before PR #78 composed it into this parent. It uses the existing `app.main` runtime, one Alembic head through `0016_academy_audit_idempotency`, FORCE RLS and a runtime role without `BYPASSRLS`.
- Academy runtime SQL remains under the central guard: 32 SQL-capable functions covering 54 database execution calls are exact-count locked. Academy lifecycle/concurrency, build, clean-state full Core regression and PostgreSQL dump/restore passed before parent composition.
- Planogram was selectively composed from deterministic foundation source `1609816c877d2b806ef145541288629da73f336e` and physical-truth source `bf7d026ee09bb1d46aa8a93daa77771bbd3754bb` through PR #79. Standalone PlanAI `main.py`, auth/security, separate frontend and historical 3D/UI migration were deliberately excluded.
- Planogram physical-truth acceptance passed 37 deterministic/physical tests, compile, a deliberately incomplete raw-master fail-closed audit, platform-authority boundary checks and the existing EAY shell production build. Canonical unit contracts prove a fully approved synthetic truth set can open the gate while missing/estimated dimensions, missing fixtures, invalid picker aisle geometry and unmeasured Store DNA keep it closed.
- PR #79 merge-result validation also exposed and closed two cross-module drifts without weakening security: the stale browser-local access smoke was rewritten to enforce absence of `accessConfig.js` and immutable server-derived authorization; and Workforce XLSX durations above 24 hours were corrected so `[h]:mm:ss` 26:00 resolves to 1,560 minutes while numeric Excel dates are explicitly decoded by the date importer.
- The Workforce duration fix passed targeted import regression, the full Workforce frontend contract suite and production frontend build; subsequent PR merge-result validation passed access, Workforce frontend, Workforce PostgreSQL load/backup-restore, Platform Core, Identity adversarial, Academy and Planogram gates together.
- All temporary write-capable port/format/security/import-fix workflows self-deleted and are absent from the resulting repository tree.

## Current validation requirement

Every change to this convergence line must remain fail-closed until the same exact head passes the authoritative repository gates, including Platform Core CI, EAY Platform Convergence, dedicated DockOS production convergence, EAY Academy Convergence and EAY Planogram Physical Truth Convergence. Module-specific gates may add evidence but do not replace repo-wide release convergence.

## External production acceptance remains open

Repository convergence does not replace live corporate evidence. Remaining external acceptance includes, among other items, corporate OIDC/SSO, live BigQuery production evidence, physical mobile/Zebra/GPS acceptance, real HR/finance inputs and reconciliation, authoritative SKU dimensions/images, measured Store DNA and real fixture geometry/capacity, managed staging/DR, and Academy media/CDN/content/entitlement/operational acceptance.

Planogram must remain `production_ready=false` until real authoritative physical master and warehouse evidence pass the gate. Synthetic fixtures are test evidence only.
