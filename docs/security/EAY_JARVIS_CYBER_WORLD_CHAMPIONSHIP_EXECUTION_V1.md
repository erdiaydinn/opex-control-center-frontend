# EAY Jarvis Cyber World Championship Execution v1

## Purpose

Turn the Cyber World Championship from a claim gate into a real, falsifiable execution protocol while preserving EAY's defensive-only and production-truth boundaries.

Canonical sequence:

`independent sealed bank → authorized sandbox → Jarvis run → external baseline runs → blind evaluator → scoring → failure taxonomy → loss-only remediation queue → fresh sealed rotation → re-race`

## Security Guardian Gate 0

Risk tier: **S3 critical** because the workflow touches external security products, organization identities, security telemetry, model evaluation and potentially sensitive incident context.

Forbidden flows:

- no sealed answer or ground truth in Git, CI logs, runner prompts or training data;
- no competitor receives evaluator ground truth or score before execution completes;
- no browser/client credential path;
- no reusable vendor credential in receipts or artifacts;
- no production mutation, exploit execution, credential capture or destructive action;
- no vendor marketing claim is converted into a benchmark score;
- no repository/synthetic run is presented as an authorized-sandbox or field run;
- no automatic production model-weight update from championship failures;
- no re-race on the same sealed rotation after remediation.

## 1. Independent sealed task bank

The repository contains the verifier contract, not the task answers.

A valid `SealedTaskBankReceipt` binds:

- independent provider reference;
- bank and rotation identity;
- complete 11-track distribution;
- public manifest digest;
- task-set fingerprint;
- sealed ground-truth digest;
- evaluator key identity;
- immutable external sealed-storage reference;
- issue/expiry timestamps.

It hard-fails if ground truth is embedded in the repository, visible to competitors or mutable after issue.

A truly independent championship therefore still requires an external evaluator-controlled bank/storage/signing authority. Repository CI cannot manufacture this evidence.

## 2. Authorized sandbox

`ChampionshipSandboxAuthorization` requires strong benchmark evidence (`AUTHORIZED_SANDBOX` or `FIELD_READ_ONLY`) and binds the championship environment fingerprint to:

- Security Guardian authorization evidence;
- worker/runtime attestations;
- deny-by-default network policy;
- workload identity;
- explicit expiry.

Production writes, exploit execution, credential capture, unrestricted networking and ground-truth access are hard-disabled.

This composes with the canonical Jarvis worker provisioning control plane rather than creating a second runtime authority. The existing worker plane already models digest-pinned images, workload identity, `vault://` secret references, tenant-isolated namespaces and runtime attestation.

## 3. Real run receipts

Every system run returns an immutable `SystemExecutionReceipt` containing only evidence-safe metadata and output digests. It binds:

- exact system/version;
- same task-set fingerprint;
- same environment fingerprint;
- same sandbox fingerprint;
- full bank task count;
- output bundle digest/reference;
- runner attestation references;
- safety-event counters.

Any ground-truth access, raw credential persistence, score visibility during execution or execution authority invalidates the receipt.

## 4. CrowdStrike / Google / Microsoft adapters

Required external baselines remain:

- CrowdStrike Charlotte AI;
- Google Security Operations / Gemini;
- Microsoft Security Copilot.

The repository now owns credential-gated adapter specifications and a `CompetitorRunnerPort`, not fabricated HTTP responses. A real run requires an organization-owned authorization receipt proving scoped identity, resource binding, explicit competition permission and read-only scope.

If the organization tenant/license/identity is unavailable, the state is `MISSING_ORGANIZATION_ACCESS` / fail-closed. No synthetic substitute may satisfy the leaderboard.

## 5. Blind scoring

The runner never sees sealed ground truth. The independent evaluator emits opaque per-task result digests and a signed result digest. `blind_score_run` verifies:

- bank ↔ evaluator binding;
- bank ↔ run task-set binding;
- sandbox ↔ run environment binding;
- evaluator ↔ run binding;
- complete task count;
- every championship track represented;
- zero ground-truth disclosure.

Only then is a per-track and overall score receipt materialized.

## 6. Failure taxonomy

Failed Jarvis evaluations are reduced to aggregate failure classes such as:

- detection miss / false positive;
- wrong prioritization / stale intelligence;
- exposure applicability / tenant / identity scope errors;
- supply-chain / incident-sequence errors;
- hallucinated evidence / unsupported attribution;
- unsafe action suggestion;
- overconfidence / avoidable abstention;
- latency/resource/provider integration failure;
- unknown-unknown miss.

The aggregate deliberately contains no task identifier and no ground truth.

## 7. Loss-only remediation queue

`build_lost_domain_remediation_queue` compares Jarvis with all three real baseline score receipts and queues only tracks where Jarvis is strictly below the strongest baseline.

Queue material contains only:

- track;
- failure class;
- aggregate failure count;
- approved public/canonical curriculum source families;
- minimum fresh training-case target.

Sealed task content and sealed ground truth are forbidden. Automatic production weight update/promotion is forbidden. A later weight update, if any, requires the normal model-evaluation and human promotion authority.

## 8. Fresh-rotation re-race

After remediation, the next championship bank must have a different:

- rotation epoch;
- task-set fingerprint;
- sealed ground-truth digest.

Reusing the same bank is rejected to prevent benchmark memorization and leakage-driven overfitting.

## Current truth boundary

Repository implementation can verify the protocol and fail-closed behavior. It cannot itself produce:

1. an independent externally sealed bank receipt;
2. a real authorized EAY championship sandbox observation;
3. real CrowdStrike Charlotte AI execution without a licensed/authorized Falcon organization identity;
4. real Google SecOps/Gemini execution without an authorized Google SecOps organization identity;
5. real Microsoft Security Copilot execution without an authorized Security Copilot resource/Entra identity.

Until those real receipts exist:

- `CHALLENGE_READY` may be repository verified;
- `VERIFIED_LEADER=false`;
- `PRODUCTION_SECURITY_SUPERIORITY=false`;
- no market-leadership claim may be made.

## Evidence surfaces

- `app/cyber_championship_execution.py`
- `app/cyber_championship_vendor_adapters.py`
- `app/cyber_championship_learning.py`
- `tests/test_cyber_championship_execution.py`
- `tests/test_cyber_championship_learning.py`
- canonical `app/cyber_world_championship.py`
- canonical `app/agent_worker_provisioning.py`
