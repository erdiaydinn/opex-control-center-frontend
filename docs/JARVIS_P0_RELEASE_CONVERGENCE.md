# EAY Jarvis P0 Release Convergence

## P0 rule

AI/Jarvis feature and security-abstraction work is frozen until the release stop condition is met. Work in this phase is limited to CI productionization, authoritative live evidence, integration, and release convergence.

Frozen foundations remain unchanged:

- PR #15 — EAY AI Core foundation — frozen.
- PR #16 — Security Phase 1 foundation — frozen.

No force push, direct `main` merge, risky auto-merge, or foundation rewrite is authorized by this plan.

## Verified Platform Core CI evidence

Platform Core CI run #547 on commit `5b34bd3fd843308dc98edb9c0db09cf231eb371d` completed GREEN.

All repo-wide jobs passed:

- Frontend build
- Core API and tenant isolation
- Jarvis tool security
- Platform configuration
- Identity Gateway adversarial boundary

The P0 CI work closed the previously observed xlsx dependency, repo-wide Ruff, Identity Gateway CI file-secret/runtime, and full Core API BigQuery test-dependency closure failures.

## Development-history graph

The cumulative development history is preserved. The current Orders-v2 line is:

`#16 -> #17 -> #37 -> #40 -> #41 -> #42 -> #43 -> #45 -> #46 -> #47 -> #48 -> #49 -> #50 -> #51 -> #52 -> #53 -> #54 -> #56 -> #57 -> #59`

This graph is development history, not a statement that every ancestor is an independent release-candidate gate.

Special cases:

- PR #38 is PARKED: historical AI-Core/Platform-Core execution-bridge sibling, not an Orders-v2 release candidate.
- PR #44 is historical/superseded for release convergence: later canonical Grant V4 PR #45 is based directly on #43 and the later canonical stack omits #44.
- PR #39 is Repository Intelligence work and is outside the Orders-v2 release graph.
- PR #58 is Workforce work and is outside the Jarvis release graph.

## Release-candidate evidence chain

The release candidate must converge on real evidence, not synthetic proof or additional abstractions.

Existing implementation slices are reused as follows:

1. PR #46 — frozen Orders-v2 candidate query contract.
2. PR #47 — typed BigQuery parameter contract.
3. PR #48 — reviewed BigQuery SDK parameter adapter.
4. PR #51 / #52 — live INFORMATION_SCHEMA collector and schema-attestation mechanism.
5. PR #53 — live cross-tenant evidence mechanism.
6. PR #54 — human promotion review plus release-gate artifact.
7. PR #56 — deployment authorization.
8. PR #57 — manual policy-promotion proposal.
9. PR #59 — transition guard and current convergence head.

PR #49 schema-evidence contract and PR #50 synthetic proof remain useful development history, but synthetic evidence MUST NOT satisfy the live-evidence release gate.

The promotion sequence is therefore:

`live schema attestation -> live cross-tenant proof -> human review -> release approval -> deployment authorization -> manual policy promotion -> transition guard`

Every stage must bind the exact reviewed fingerprints produced by the preceding real-evidence stage. No stage may infer readiness from a synthetic fixture.

## Current policy state

The active version-controlled `ops_kpi_query` policy remains:

- contract: `ops.kpi.orders.v1`
- revision: `1`
- `production_ready=false`

Orders-v2 remains a blocked candidate. Production execution, promotion eligibility, and policy mutation remain disabled until authoritative live schema and cross-tenant evidence are executed and the existing review chain is filled with matching fingerprints.

## Parked / superseded side branches

The following branches are not release-candidate heads:

- `platform-core/orders-v2-live-evidence` — PARKED scratch/live-evidence experiment; do not merge blindly into the release graph.
- `platform-core/eay-v2-jarvis-orders-deployment-authorization` — superseded branch-only ancestor; PR #56 uses `...deployment-authorization-v2`.
- `platform-core/eay-v2-jarvis-orders-human-promotion-review-copy` — superseded branch-only ancestor of the canonical human-review branch.
- `platform-core/eay-v2-jarvis-orders-consumption-ledger`
- `platform-core/eay-v2-jarvis-orders-consumption-ledger-v2`
- `platform-core/eay-v2-jarvis-orders-provenance-readiness`

The last three are retained as historical/post-guard development branches and are not promoted as independent release gates under the P0 freeze.

## Live-truth blocker

The repository contains a fixed read-only INFORMATION_SCHEMA collector and an explicit schema-attestation CLI, but the current GitHub CI workflow named `Jarvis Orders Live Schema Collector CI` is contract/test CI only; it does not authenticate to production BigQuery and does not submit the live metadata query.

Therefore, as of this convergence record:

- authoritative live BigQuery schema evidence: NOT RUN
- controlled live cross-tenant proof: NOT RUN
- active policy: v1
- production readiness: false

## Single next P0 dependency

Provide an authorized, read-only BigQuery execution identity/environment for the existing collector and controlled cross-tenant verifier. The live run must:

1. execute the fixed INFORMATION_SCHEMA metadata query against the authoritative Orders table;
2. prove the actual tenant discriminator field from production metadata;
3. execute a controlled cross-tenant verification with zero foreign tenant/store sentinel leakage;
4. persist only privacy-minimized metadata/fingerprints, never unnecessary raw production rows;
5. feed those exact live fingerprints into the existing #54 -> #56 -> #57 -> #59 promotion chain.

Until that dependency is satisfied, no new AI/Jarvis security abstraction PR should be opened and `production_ready` must remain false.
