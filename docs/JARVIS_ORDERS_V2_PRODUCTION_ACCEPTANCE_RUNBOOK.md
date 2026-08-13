# EAY Jarvis Orders-v2 Production Acceptance Runbook

## Purpose

This runbook is the operational release path for `ops.kpi.orders.v2`. It does not create a new security abstraction, approval layer, fingerprint layer, or synthetic proof. It reuses the canonical reviewed chain and requires real BigQuery evidence before policy promotion.

Synthetic fixtures, fake clients, unit tests, schema-contract tests, and PR CI MUST NOT be recorded as live production evidence.

## Frozen and canonical boundaries

Frozen foundations:

- PR #15 — EAY AI Core foundation — frozen.
- PR #16 — Security Phase 1 foundation — frozen.

Canonical Orders-v2 release line:

`#46 -> #47 -> #48 -> #51/#52 -> #53 -> #54 -> #56 -> #57 -> #59`

Special cases:

- PR #38 remains PARKED.
- PR #44 remains historical/superseded.
- PR #49 and #50 remain development evidence history; #50 synthetic proof cannot satisfy a live gate.

No direct `main` merge, force push, automatic production promotion, model-authored SQL, or production model-weight mutation is part of this runbook.

## 1. Authorized BigQuery execution identity

The live evidence runner must use an externally managed read-only Google Cloud identity. Workload Identity Federation is preferred for GitHub/CI-style execution so a long-lived service-account JSON key is not stored in the repository.

Minimum intended BigQuery authority:

- ability to create query jobs in the approved execution project (`roles/bigquery.jobUser` or a stricter custom equivalent);
- read/query access only to the authoritative required BigQuery dataset/table scope (`roles/bigquery.dataViewer` or a stricter custom equivalent);
- no BigQuery Data Editor/Admin, dataset-owner, IAM-admin, key-admin, or unrelated project-wide write role.

Official references:

- https://cloud.google.com/bigquery/docs/access-control
- https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines

The identity/environment is an external prerequisite. Do not commit credentials, private keys, access tokens, production tenant/store control values, or populated credential files.

## 2. Exact-head preflight

Before any live query:

1. Record the exact release-candidate Git SHA.
2. Require latest exact-head Platform Core CI = GREEN.
3. Confirm active policy is still `ops.kpi.orders.v1` / `production_ready=false` before evidence collection.
4. Confirm `services/core-api/app/core/ai_orders_v2_query_contract.py` still contains the reviewed `ops.kpi.orders.v2` candidate and mandatory `entity.id IN UNNEST(@entity_ids)` plus `vendor_name IN UNNEST(@stores)` predicates.
5. Confirm model-authored SQL remains disabled; no operator-supplied SQL override is allowed.

If any item differs, stop and re-review the release candidate.

## 3. Real INFORMATION_SCHEMA observation

Use the committed opt-in schema-attestation CLI under the authorized BigQuery identity.

Required environment:

```text
EAY_BQ_SCHEMA_ATTESTATION_ENABLED=true
EAY_BQ_PROJECT=<authorized execution/data project>
EAY_BQ_LOCATION=<approved BigQuery location, if required>
```

From `services/core-api`:

```text
python -m app.cli.attest_orders_v2_schema > orders-v2-schema-attestation.json
```

Acceptance requirements:

- the CLI actually authenticates to BigQuery and submits the fixed `INFORMATION_SCHEMA.COLUMN_FIELD_PATHS` query;
- exactly one metadata row is returned;
- source dataset/table is `curated_data_shared_coredata_business.orders`;
- top-level column is `entity`;
- exact field path is `entity.id`;
- data type is `STRING`;
- artifact project/location match the authorized client;
- output remains privacy-minimized metadata/fingerprints only.

A unit-test/fake-client output is not valid evidence.

## 4. Controlled live cross-tenant proof

The proof must execute the exact reviewed Orders-v2 SQL and the exact reviewed typed parameter contract. It must not accept arbitrary SQL, parameter types, table names, or model-generated query text.

The operator must choose real, known-disjoint control scopes from the authorized environment:

- authorized entity ID set and authorized store set with known non-zero Orders data in the chosen date range;
- one genuine foreign entity sentinel that is outside the authorized tenant/entity set;
- one genuine foreign store sentinel that is outside the authorized store set and is known to belong to a disjoint control scope.

Run three bounded read-only queries using the same exact candidate SQL:

1. **Positive control:** authorized entity IDs + authorized stores. Result must be non-empty and all returned stores must remain inside the authorized store set.
2. **Foreign-store negative control:** authorized entity IDs + foreign store sentinel. Result row count must be `0`.
3. **Foreign-entity negative control:** foreign entity sentinel + authorized stores. Result row count must be `0`.

A zero-row negative control is meaningful only when the selected foreign sentinel is known to exist in the authoritative dataset/control period. Do not use invented or synthetic sentinel values.

Every live query must have:

- Standard SQL;
- typed parameters from the reviewed #47/#48 contract;
- explicit approved maximum-bytes-billed cap;
- bounded timeout;
- no write statement;
- no query text override;
- no raw production row persistence beyond the controlled in-memory verification step.

The #53 evidence artifact must persist only privacy-minimized hashes/fingerprints for job IDs, authorized/foreign scope descriptors, returned rowset, and exact reviewed contracts. `foreign_sentinel_match_count` must equal `0`.

Any foreign match is a hard FAIL. Do not continue to promotion.

## 5. Schema attestation and existing approval chain

After the real schema observation and live cross-tenant proof both pass, feed the exact real-evidence fingerprints into the existing chain only:

`#54 human review/release gate -> #56 deployment authorization -> #57 manual policy-promotion proposal -> #59 transition guard`

Do not add a parallel approval path.

Required checks:

- human review binds the exact live schema attestation and live cross-tenant evidence;
- release approval and deployment authorization bind the same evidence lineage;
- policy proposal targets only `ops.kpi.orders.v2`;
- transition guard sees the expected current v1 policy and rejects stale/replayed/drifted proposals;
- all required approval identities remain separated according to the already-reviewed contracts.

## 6. Activate Orders-v2 policy for governed staging

Only after the real evidence chain is complete may a release/integration change propose the active `ops_kpi_query` policy transition from v1 to v2.

Before staging execution, require:

- exact v2 template fingerprint pinned;
- exact `entity.id` discriminator confirmed by live schema evidence;
- exact live cross-tenant proof fingerprint pinned;
- `production_ready=true` only when the existing policy validator's complete reviewed evidence requirements are satisfied;
- repo-wide CI GREEN on the exact policy-transition release candidate.

No model-authored SQL is enabled by this transition.

## 7. Governed staging execution acceptance

Staging acceptance is PASS only when all of the following are observed on the exact release candidate:

- authorized tenant/store request executes the v2 template successfully;
- out-of-scope tenant/store request is denied or returns no foreign data according to the existing authorization/data-scope contract;
- cross-tenant foreign leak count remains `0`;
- single-use grant replay remains rejected;
- stale query/data-scope/tenant-context binding remains rejected;
- transient BigQuery failure fails closed and does not silently fall back to v1, synthetic data, broader scope, or model-authored SQL;
- a retry is performed only after the prior execution outcome is known and through the existing governed grant/idempotency path;
- duplicate/replayed execution does not create an untracked second authorized execution;
- audit/observability records contain the existing privacy-minimized execution/security fingerprints and outcome without raw sensitive scope values;
- audit failure remains fail-closed where the existing contract requires it.

Do not mark staging PASS from unit tests alone.

## 8. Production acceptance

Production acceptance requires the same exact reviewed v2 policy/evidence lineage that passed staging. Re-run the release gates on the production deployment artifact and require:

- exact-head repo-wide CI GREEN;
- active tenant-safe reviewed v2 policy;
- live BigQuery schema proof;
- controlled live cross-tenant leak count `0`;
- staging governed execution PASS;
- failure/retry/idempotency acceptance PASS;
- observability/audit PASS;
- rollback procedure reviewed and executable.

Production acceptance must not change model weights or enable model-authored SQL.

## 9. Rollback

Rollback is a release/configuration rollback, not a destructive data reset.

If any staging or production acceptance condition fails:

1. stop/disable new v2 governed execution through the deployment/release control plane;
2. preserve all live evidence, audit records, failed job metadata, and exact release SHA for investigation;
3. redeploy the last-known-good release artifact whose active policy is the reviewed v1 state;
4. verify the active policy is `ops.kpi.orders.v1` and `production_ready=false` for the blocked v2 candidate;
5. verify Platform/Core/Jarvis health and exact-head CI for the rollback artifact;
6. verify no v2 execution path remains enabled;
7. document the failed acceptance criterion and do not reuse the failed evidence as promotion authority.

Forbidden rollback actions:

- deleting or rewriting audit/evidence history;
- database reset/drop;
- `docker compose down -v` as a production recovery method;
- force-pushing frozen foundations;
- weakening tenant/query authorization to restore service.

## 10. KPI-family rollout after Orders-v2

Only after Orders-v2 reaches production acceptance, apply the same production-evidence standard in this order:

1. NSFR / PFR / Refund
2. Prep / Picking
3. OTP
4. Putaway

For every family require real schema evidence, reviewed KPI semantics, reviewed deterministic SQL/template, tenant/store scoping, controlled live cross-tenant proof, staging governed execution, observability/audit, and rollback acceptance. Model-authored SQL remains disabled.

## >=95% exit gate

The AI/Jarvis production-acceptance target is not reached until all are true:

- repo-wide CI GREEN;
- active tenant-safe reviewed policy;
- live BigQuery proof;
- cross-tenant leak count = 0;
- staging execution PASS;
- failure/retry/idempotency acceptance PASS;
- observability/audit PASS;
- documented and reviewed rollback/runbook.
