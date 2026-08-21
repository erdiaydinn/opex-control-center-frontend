# EAY Academy Convergence Evidence

This document records repository-level integration evidence only. It does not declare Academy production readiness, authorize a merge to `main`, or replace real media/CDN/content/entitlement acceptance.

## Integration line

- Parent convergence: `release/platform-convergence-v0.1`
- Academy child: `release/platform-convergence-academy-v0.1`
- Canonical Academy source: `product/academy-canonical-v1`

## Cumulative composition decisions

- Academy is composed into the existing Core API runtime through `app.main`; the standalone `main_academy.py` entrypoint is intentionally not carried forward.
- Academy migrations are rebased after Budget as `0015_academy_foundation` -> `0016_academy_audit_idempotency`, preserving a single Alembic head after `0014_budget_rls_controls`.
- The existing central SQL execution boundary remains authoritative; Academy does not replace the platform SQL-boundary test.
- Academy repository facade re-exports are explicit through `__all__` so safe lint automation cannot remove public repository contracts.
- E501 exceptions are scoped to Academy SQL/DDL-heavy repository, migration and selected integration/concurrency test files; general business code remains under the normal Core API line-length gate.
- One-shot write-capable port/quality/security-registration workflows self-delete and are not present in the resulting repository tree.

## Evidence already observed

- Academy frontend/runtime composition build: PASS.
- Academy migration + seed + PostgreSQL dump/restore: PASS through Alembic `0016_academy_audit_idempotency`.
- Full Core Ruff gate after Academy convergence formatting: PASS.
- Academy code and current Core entrypoint compile: PASS.
- Central SQL boundary review: PASS after explicitly registering 32 Academy SQL-capable functions covering 54 database execution calls with exact call-count locking.
- Static SQL literal checks, dynamic raw-SQL rejection, direct-driver rejection and approved-function growth checks remain enabled; no broad Academy SQL exemption was introduced.

## Current exact-head requirement

The Academy child is not eligible to compose back into the parent until the same exact head passes Academy PostgreSQL/RLS, central SQL execution boundary, Academy lifecycle/concurrency, full Core regression, build/runtime composition, and DR gates.
