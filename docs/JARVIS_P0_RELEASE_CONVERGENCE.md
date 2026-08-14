# EAY Jarvis P0 Release Convergence

## P0 rule

AI/Jarvis is in LIVE PRODUCTION TRUTH phase. New security abstractions, approval layers, fingerprint layers, and synthetic-proof PRs are frozen. Work is limited to authoritative live evidence, integration, staging acceptance, production acceptance, and release convergence.

Frozen foundations:

- PR #15 — EAY AI Core foundation — `9e1422df2a584b71593c2f6188d26c8ab4ab4c15`
- PR #16 — Security Phase 1 foundation — `6a1ab7d8e150a8392ba144c4a3e49dcc73130a1d`

No force push, direct `main` merge, risky auto-merge, foundation rewrite, model-authored SQL, or synthetic promotion evidence is authorized by this plan.

## Verified CI baseline

Platform Core CI run #549 on PR #59 head `3702c3c8503b680ee6d82d7910bfaf1b3eeb62a0` completed GREEN across Frontend, Core API and tenant isolation, Jarvis tool security, Platform configuration, and Identity Gateway adversarial boundary. CI cleanup P0 is closed.

A later release-documentation composition at `42b3f5f93314f4f9d1f20c7c50c5b7ecb20c853e` also completed repo-wide Platform Core CI GREEN in run #550. The current #59 documentation head must obtain its own exact-head CI before it is treated as the release-candidate CI authority.

## Canonical Orders-v2 release composition

| Layer | PR | Exact reviewed head SHA | Status |
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
| Policy transition guard / convergence PR | #59 | current branch head | CANONICAL CURRENT RELEASE PR |

Cumulative development ancestry is preserved:

`#16 -> #17 -> #37 -> #40 -> #41 -> #42 -> #43 -> #45 -> #46 -> #47 -> #48 -> #49 -> #50 -> #51 -> #52 -> #53 -> #54 -> #56 -> #57 -> #59`

Development ancestry is not release evidence authority.

## Historical / superseded / parked topology

- PR #38 — PARKED historical AI-Core/Platform-Core execution-bridge sibling.
- PR #44 — HISTORICAL/SUPERSEDED; canonical Grant V4 continues through #45 from #43.
- PR #39 — Repository Intelligence; outside Orders-v2 release topology.
- PR #58 — Workforce; outside Jarvis release topology.
- PR #49 — schema-evidence contract history; not a live observation.
- PR #50 — synthetic cross-tenant proof history; MUST NOT satisfy any live-evidence gate.

Branch-only historical/parked heads are not release candidates: `platform-core/orders-v2-live-evidence`, unsuffixed deployment-authorization, human-promotion-review-copy, both consumption-ledger branches, and orders-provenance-readiness.

## Canonical live-truth sequence

No synthetic artifact may substitute for:

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

## Active policy and live evidence

Active version-controlled `ops_kpi_query` remains `ops.kpi.orders.v1`, revision `1`, `production_ready=false`.

Current live state:

- authoritative live BigQuery schema evidence: **NO / NOT RUN**
- exact production tenant discriminator observation: **NO / NOT RUN**
- controlled live cross-tenant proof: **NO / NOT RUN**
- staging governed execution: **NOT RUN**
- active policy: **v1**

The existing live-schema workflow is contract/test CI only; it does not authenticate to production BigQuery and does not itself constitute live production evidence.

## Production acceptance procedure

### 1. Authorized identity

Use an externally managed read-only BigQuery identity. The required authority is limited to creating approved query jobs and reading/querying only the authoritative dataset/table scope. Do not commit credentials, keys, access tokens, or populated credential files.

### 2. Exact-head preflight

Before any live query:

1. record the exact #59 release-candidate SHA;
2. require exact-head Platform Core CI GREEN;
3. confirm active policy is still v1 / `production_ready=false` before evidence collection;
4. confirm the reviewed Orders-v2 candidate still contains mandatory `entity.id IN UNNEST(@entity_ids)` and `vendor_name IN UNNEST(@stores)` predicates;
5. confirm model-authored SQL and operator SQL override remain disabled.

### 3. Real INFORMATION_SCHEMA observation

Under the authorized BigQuery identity run the committed schema-attestation CLI with explicit opt-in (`EAY_BQ_SCHEMA_ATTESTATION_ENABLED=true`) and configured project/location. Acceptance requires a real BigQuery-authenticated fixed `INFORMATION_SCHEMA.COLUMN_FIELD_PATHS` observation returning exactly one metadata row proving the authoritative Orders source, `entity.id`, and expected type. Fake-client or unit-test output is invalid.

### 4. Controlled live cross-tenant proof

Use only the exact reviewed Orders-v2 SQL and #47/#48 typed parameter contract. Choose real, known-disjoint production control scopes: one authorized entity/store set with known non-zero data, one genuine foreign entity sentinel, and one genuine foreign store sentinel.

Run three bounded read-only controls:

1. authorized entities + authorized stores => non-empty result, all rows within authorized store scope;
2. authorized entities + genuine foreign store => row count `0`;
3. genuine foreign entity + authorized stores => row count `0`.

A zero-row negative control is valid only when the foreign sentinel is known to exist in the authoritative dataset/control period. Never invent a synthetic sentinel. Every query must use Standard SQL, reviewed typed parameters, bounded timeout/cost, no write statement, no SQL override, and no unnecessary raw-row persistence. The #53 privacy-minimized evidence artifact must report `foreign_sentinel_match_count=0`. Any foreign match is a hard FAIL.

### 5. Existing review/promotion chain

After real schema and cross-tenant proof both pass, feed only that exact evidence lineage through `#54 -> #56 -> #57 -> #59`. Do not create a parallel approval path.

### 6. Governed staging acceptance

Only after the real evidence chain completes may an integration change propose active v2. Staging PASS requires observed execution on the exact release candidate:

- authorized v2 execution succeeds;
- out-of-scope access yields no foreign data;
- cross-tenant leak count remains `0`;
- single-use grant replay is rejected;
- stale query/data-scope/tenant-context bindings are rejected;
- transient BigQuery failure fails closed with no fallback to v1, synthetic data, broader scope, or model-authored SQL;
- retries use the existing governed grant/idempotency path only after prior outcome is known;
- duplicate/replayed execution creates no untracked second authorized execution;
- existing privacy-minimized audit/observability records capture execution outcome/security lineage;
- audit failure remains fail-closed where the existing contract requires it.

Unit tests alone cannot mark staging PASS.

### 7. Production acceptance

Production acceptance requires the same exact v2 evidence lineage that passed staging, exact-head repo-wide CI GREEN, live BigQuery proof, leak count `0`, staging PASS, failure/retry/idempotency PASS, observability/audit PASS, and reviewed rollback readiness. Model-authored SQL remains disabled.

## Rollback

Rollback is release/configuration rollback, not destructive data reset. On any failed staging/production criterion:

1. disable new v2 governed execution through the release/deployment control plane;
2. preserve live evidence, audit records, failed job metadata, and exact release SHA;
3. redeploy the last-known-good reviewed v1 release artifact;
4. verify active policy is `ops.kpi.orders.v1` and blocked v2 is non-production-ready;
5. verify Platform/Core/Jarvis health and exact-head CI for the rollback artifact;
6. verify no v2 execution path remains enabled;
7. document the failed criterion and never reuse failed evidence as promotion authority.

Forbidden rollback actions: deleting/re-writing evidence/audit history, production database reset/drop, `docker compose down -v` as recovery, force-pushing frozen foundations, or weakening tenant/query authorization.

## External P0 blocker

The single external dependency remains an authorized read-only production BigQuery execution identity/environment. The repository currently exposes no configured GitHub Environment for that path through the available integration, and repository secrets are not inspectable through the available connector. No credential is invented or inferred.

Until that external dependency exists: do not fabricate evidence, promote v2, claim staging PASS, replace live proof with synthetic proof, or open another AI/Jarvis security abstraction PR.

## >=95% acceptance gate

The target is not reached until all are true on one reviewable release candidate:

- repo-wide CI GREEN;
- active tenant-safe reviewed policy;
- live BigQuery proof;
- cross-tenant leak count = 0;
- staging execution PASS;
- failure/retry/idempotency acceptance PASS;
- observability/audit PASS;
- documented/reviewed rollback procedure.

After Orders-v2 production acceptance, apply the same standard in order: NSFR/PFR/Refund -> Prep/Picking -> OTP -> Putaway. Model-authored SQL remains disabled.
