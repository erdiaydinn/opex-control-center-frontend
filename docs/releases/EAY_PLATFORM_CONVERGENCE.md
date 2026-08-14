# EAY Platform Convergence Evidence

This document records repository-level convergence evidence only. It does not declare production readiness and it does not authorize a merge to `main` or any production activation.

## Cumulative platform line

Canonical branch: `release/platform-convergence-v0.1`

Composed product/security lineage currently includes:

- frozen Security/Core Phase 1 authority;
- Workforce/Hiring V32;
- Inventory synchronized to current Workforce;
- DockOS production runtime delta;
- Budget Intelligence v1 through Alembic `0014_budget_rls_controls`.

## Verified evidence before this evidence commit

- Dedicated DockOS production convergence passed four-worker startup/load, runtime metrics, database interruption fail-closed, recovery, PostgreSQL restart recovery, and combined Workforce/DockOS backup-restore on cumulative head `2b22aa460ab9241fc4586530554bee8d55dc32fc`.
- Budget Intelligence PostgreSQL foundation passed on the cumulative line after branch-to-branch composition, including `alembic upgrade head`, Budget unit contracts, canonical routes/permissions, ENABLE + FORCE RLS, and a runtime role without `BYPASSRLS`.
- Budget's SQL-heavy files retain the canonical Budget CI's E501 exception as a narrowly scoped Ruff per-file policy. Other Ruff classes remain enabled.
- A one-shot Ruff safe-fix workflow verified the full Core API Ruff gate and Budget unit contracts, then deleted its own write-capable workflow. The temporary workflow is not part of the resulting repository tree.

## Current validation requirement

Every change to this convergence line must remain fail-closed until the same exact head passes the authoritative repository gates, including Platform Core CI, EAY Platform Convergence, and the dedicated DockOS production convergence. Module-specific gates may add evidence but do not replace repo-wide release convergence.

## External production acceptance remains open

Repository convergence does not replace live corporate evidence. Remaining external acceptance includes, among other items, corporate OIDC/SSO, live BigQuery production evidence, physical mobile/Zebra/GPS acceptance, real HR/finance inputs and reconciliation, Planogram physical truth, managed staging/DR, and Academy media/CDN operational acceptance.
