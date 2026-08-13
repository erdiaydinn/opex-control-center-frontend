# EAY Jarvis P0 Release Convergence

## P0 rule

AI/Jarvis is in LIVE PRODUCTION TRUTH phase. New security abstractions, approval layers, fingerprint layers, and synthetic-proof PRs are frozen. Work is limited to authoritative live evidence, integration, staging acceptance, production acceptance, and release convergence.

Frozen foundations:

- PR #15 — EAY AI Core foundation — `9e1422df2a584b71593c2f6188d26c8ab4ab4c15`
- PR #16 — Security Phase 1 foundation — `6a1ab7d8e150a8392ba144c4a3e49dcc73130a1d`

No force push, direct `main` merge, risky auto-merge, or foundation rewrite is authorized by this plan.

## Verified exact-head CI

Platform Core CI run #549 on PR #59 head `3702c3c8503b680ee6d82d7910bfaf1b3eeb62a0` completed GREEN.

All repo-wide jobs passed:

- Frontend build
- Core API and tenant isolation
- Jarvis tool security
- Platform configuration
- Identity Gateway adversarial boundary

CI cleanup P0 is therefore closed. Future work must not reopen feature/security-abstraction expansion under the CI-cleanup label.

## Canonical Orders-v2 release composition

The release-candidate evidence topology is:

| Layer | PR | Exact reviewed head SHA | Release status |
|---|---:|---|---|
| Orders-v2 deterministic query candidate | #46 | `d4e7d32afba646953bc624aa5ce6afd3e14151fe` | CANONICAL |
| Typed BigQuery parameter contract | #47 | `1c001f41e63c329e60fe800eba413502a0fbcddd` | CANONICAL |
| BigQuery SDK parameter adapter | #48 | `04196b3fe3488e21db7653869756a52e8e4ad32e` | CANONICAL |
| Read-only live schema collector | #51 | `72a7667a1a90c5c27378b72c9908463c611c5374` | CANONICAL |
| Opt-in schema-attestation CLI | #52 | `087ca502784be0ac4889af50288843ca1953ed47` | CANONICAL |
| Live cross-tenant evidence contract | #53 | `e13a6736c7069e369ef0531c7fe3397143050dbe` | CANONICAL |
| Human promotion review / release evidence | #54 | `868039bb76b57db0ae84e1bc61315934c5ef1c93` | CANONICAL |
| Deployment authorization | #56 | `06b6e2bd60121112eed21c7eaa1001b98ec7f365` | CANONICAL |
| Manual policy-promotion proposal | #57 | `20563fb2fe3fcedc99dbce805ed5c2efb801e0d9` | CANONICAL |
| Policy transition guard / convergence head | #59 | `3702c3c8503b680ee6d82d7910bfaf1b3eeb62a0` | CANONICAL CURRENT HEAD |

The cumulative development ancestry is preserved:

`#16 -> #17 -> #37 -> #40 -> #41 -> #42 -> #43 -> #45 -> #46 -> #47 -> #48 -> #49 -> #50 -> #51 -> #52 -> #53 -> #54 -> #56 -> #57 -> #59`

Development ancestry is not the same as release evidence authority.

## Historical / superseded / parked topology

- PR #38 — PARKED historical AI-Core/Platform-Core execution-bridge sibling; not an Orders-v2 release candidate.
- PR #44 — HISTORICAL/SUPERSEDED for release convergence; canonical Grant V4 continues through #45 from #43.
- PR #39 — Repository Intelligence; outside Orders-v2 release topology.
- PR #58 — Workforce; outside Jarvis release topology.
- PR #49 — schema-evidence contract history; useful contract history but not live observation by itself.
- PR #50 — synthetic cross-tenant proof history; MUST NOT satisfy any live-evidence gate.

Branch-only historical/parked heads are not release-candidate heads:

- `platform-core/orders-v2-live-evidence`
- `platform-core/eay-v2-jarvis-orders-deployment-authorization`
- `platform-core/eay-v2-jarvis-orders-human-promotion-review-copy`
- `platform-core/eay-v2-jarvis-orders-consumption-ledger`
- `platform-core/eay-v2-jarvis-orders-consumption-ledger-v2`
- `platform-core/eay-v2-jarvis-orders-provenance-readiness`

Do not merge these branches into the release graph merely because they contain later experimental/history commits.

## Canonical live-truth sequence

No synthetic artifact can substitute for this sequence:

`authorized read-only BigQuery identity/environment`
`-> real INFORMATION_SCHEMA observation`
`-> exact tenant discriminator verification`
`-> controlled live cross-tenant proof`
`-> schema attestation`
`-> #54 human/release evidence`
`-> #56 deployment authorization`
`-> #57 manual policy promotion`
`-> #59 transition guard`
`-> active ops.kpi.orders.v2`
`-> governed staging execution`
`-> production acceptance`

Every evidence handoff must use the exact canonical implementation lineage above.

## Current policy state

Active version-controlled `ops_kpi_query` policy remains:

- contract: `ops.kpi.orders.v1`
- revision: `1`
- `production_ready=false`

Orders-v2 is still a blocked candidate. No current PR/test result is authority to report v2 as active.

## Live evidence state

As of this release convergence update:

- authoritative live BigQuery schema evidence: **NO / NOT RUN**
- exact production tenant discriminator observation: **NO / NOT RUN**
- controlled live cross-tenant proof: **NO / NOT RUN**
- staging governed execution: **NOT RUN**
- active policy: **v1**

`Jarvis Orders Live Schema Collector CI` is contract/test CI only and does not authenticate to production BigQuery or submit the live production observation.

## External P0 blocker

The one P0 external dependency is an authorized read-only production BigQuery execution identity/environment.

At the time of this review the repository exposes no configured GitHub Environment for that production-readonly execution path, and the available integration cannot inspect repository secrets. No credential is invented or inferred.

When the external identity/environment is supplied, follow `docs/JARVIS_ORDERS_V2_PRODUCTION_ACCEPTANCE_RUNBOOK.md` and collect real evidence. Until then:

- do not fabricate evidence;
- do not promote v2;
- do not claim staging PASS;
- do not replace live evidence with synthetic proof;
- do not open another AI/Jarvis security abstraction PR.

## >=95% acceptance gate

The target is not reached until all are true on one reviewable release candidate:

- repo-wide CI GREEN;
- active tenant-safe reviewed policy;
- live BigQuery proof;
- cross-tenant leak count = 0;
- staging execution PASS;
- failure/retry/idempotency acceptance PASS;
- observability/audit PASS;
- documented and reviewed rollback/runbook.

After Orders-v2 production acceptance, apply the same production-evidence standard in order: NSFR/PFR/Refund -> Prep/Picking -> OTP -> Putaway. Model-authored SQL remains disabled.
