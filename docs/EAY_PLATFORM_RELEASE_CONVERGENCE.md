# EAY Platform Release Convergence

Status: **repository integration validation in progress**  
Production-ready: **false**  
Direct main merge: **not permitted by this branch**

## Canonical ancestry composed here

- Frozen Security/Core Phase 1: PR #16 @ `6a1ab7d8e150a8392ba144c4a3e49dcc73130a1d`
- Workforce/Hiring V32: PR #61 @ `b966cec5969859f91f26096b2b8fd64259da152e`
- Inventory production terminal after Workforce V32 sync: PR #66 @ `19f7c93547078b9cec18cec0d39420e33a30f218`

Frozen PR #16 was merged only into this dedicated convergence branch. No frozen source branch and no `main` branch was mutated.

## Closed repository blockers

- Browser-local authorization authority removed from the converged application shell.
- Central bearer-token API boundary restored; caller-provided identity/authorization override is rejected.
- Inventory product provider and backend-authoritative access-management route restored on the secure shell.
- SheetJS 0.20.3 local-tarball dependency is deterministically materialized from the pinned upstream artifact and SHA-512 verified before `npm ci` and Docker frontend builds.
- Core API safe Ruff debt was reduced with a temporary safe-only fixer; the temporary write workflow was removed immediately.
- The remaining seven Core Ruff findings were fixed by an exact-string, test-gated, self-deleting workflow; that workflow is no longer present in the tree.
- Identity Gateway runtime health acceptance now allows only a bounded recovery window and still fails closed if readiness never becomes healthy; Docker health diagnostics are retained on failure.

## Required exact-head acceptance

The branch is not considered repository-converged until one exact head passes all of:

1. Platform Core frontend build.
2. Core API Ruff, secure SQL boundary, migrations, AI database-role isolation and full tests.
3. Platform Compose and Core/frontend container builds.
4. Identity Gateway signer, secret, runtime network/key/crypto adversarial boundary.
5. EAY Platform Convergence topology, browser-authority regression, build and backend compile gates.

## External blockers not satisfiable by repository CI

Corporate OIDC/SSO, live BigQuery identity/evidence, physical mobile/Zebra/GPS acceptance, real Planogram physical master/Store DNA, customer HR/finance inputs, managed staging/DR, CDN/media and operational pilots remain separate production-acceptance gates. Passing this repository convergence does not set `production_ready=true`.
