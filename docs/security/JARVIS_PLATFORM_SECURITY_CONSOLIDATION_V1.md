# Jarvis Platform Security Consolidation V1

Status: repository acceptance workstream; not production activation evidence.

## Non-negotiable lineage rule

PR #15 (EAY AI Core foundation) and PR #16 (Security Phase 1) remain frozen
reference baselines. This workstream does **not** commit to, rebase, merge or
revive either historical branch. Unique authorities are ported into the current
Jarvis / Platform Core architecture and are accepted only on a current exact
head.

The immediate parent for this workstream is the current governed-execution
security line represented by PR #161 / `agent/jarvis-security-consolidation-v3`.
Historical PRs #30, #35 and #36 are authority sources only; their old broker,
migration numbering and topology are not restored wholesale.

## Current execution chain

```text
user request
  -> server-derived tenant / role / data scope
  -> reviewed query-contract readiness
  -> grant-issuance Idempotency-Key reservation
  -> Grant V4 issue
  -> fresh Jarvis service identity
  -> Grant V4 atomic single-use consume
  -> current tenant query-context re-resolution
  -> distributed tenant + actor admission lease
  -> durable Platform audit event
  -> trusted execution context returned to AI Core
  -> vetted template / bounded BigQuery execution
  -> opaque admission lease release
```

The deliberate ordering difference from the historical broker is important:
Grant V4 is now the single-use execution authority. Admission is therefore
reserved **after** atomic grant consumption. If readiness, admission or audit
fails after consumption, the grant stays burned rather than becoming an
ambiguous retry token.

## Capability convergence matrix

| Historical / required authority | Current canonical implementation | Evidence target | Status |
|---|---|---|---|
| Jarvis service identity and replay resistance | PR #161 service assertion / Platform authorizer | governed-execution security tests | PORTED |
| Caller cannot supply tenant, actor or permission scope | `services/core-api/app/ai_tool_routes.py` + AI Core request contract | Core + AI Core adversarial tests | PORTED |
| Exact tool + arguments + human reason binding | Grant V4 + AI Core context revalidation | grant and governed execution tests | PORTED |
| Single-use execution authorization | `RedisAiToolGrantStore.consume_authorized_invocation` | grant replay tests | CURRENT AUTHORITY |
| Request retry idempotency before grant issue | `jarvis_grant_idempotency.py` | real Redis replay/conflict/privacy acceptance | PORTED / MODERNIZED |
| Distributed tenant + actor rate control | `jarvis_execution_admission.py` | real Redis rate acceptance | PORTED / MODERNIZED |
| Distributed tenant + actor concurrency | `jarvis_execution_admission.py` | real Redis concurrency + opaque release acceptance | PORTED / MODERNIZED |
| Durable execution authorization audit | existing Platform audit sink | audit fail-closed tests | CURRENT AUTHORITY |
| Tamper-evident per-tenant audit sequence/hash | migration `0045_jarvis_audit_hash_chain` | PostgreSQL recomputation + append-only acceptance | PORTED / MODERNIZED |
| No raw tenant/actor/args/reason in Redis admission/idempotency state | hashed scopes and fingerprints only | real Redis privacy assertions | PORTED |
| AI Core releases capacity without re-supplying tenant/actor authority | opaque lease release route + AI Core `release_admission` | success/failure/Voice tests | NEW HARDENING |
| Denial/unknown authorization prevents BigQuery execution | `authorize_and_execute_with_adapter` | AI Core and Voice adversarial tests | CURRENT + REVALIDATED |
| Query context / contract / execution fingerprints survive split boundary | expanded `TrustedToolExecutionContext` | exact response validation tests | FIXED / REVALIDATED |

## Audit evidence boundary

The PostgreSQL chain is **tamper-evident**, not WORM and not tamper-proof. A
database owner can replace database functions or triggers. Independent signed
checkpointing / immutable external retention remains a separate control and
must not be represented as completed by this migration.

## Production boundary

This workstream must not set `production_ready=true`, merge to `main`, or imply
that synthetic repository acceptance is production evidence. Production still
requires, at minimum, production-shaped Redis/PostgreSQL deployment evidence,
corporate identity, operational monitoring/recovery and the relevant live data
acceptance chain.

## Closure rule

This V1 slice is closed only when the same exact head is GREEN for:

1. real Redis Grant V4 issuance idempotency;
2. real Redis distributed admission;
3. cumulative PostgreSQL migration + audit hash-chain verification;
4. Core route/grant/audit regressions;
5. AI Core governed execution + Voice regression;
6. full AI Core regression.

After this slice is GREEN, perform the broader #15/#16 capability coverage
matrix (`historical capability -> current canonical file/PR -> exact-head
proof`). Any genuinely missing capability is ported into the modern current
head; neither frozen historical branch is revived.
