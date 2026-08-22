# EAY Mobile Offline and Sync Contract v1

## Rule

Offline execution is a bounded continuation of previously authorized work. It is not independent authority. Every synchronized mutation is re-authorized against current server state.

## Queue binding

A queued event remains bound to the tenant, actor/session, device, installation, mission, operation, payload hash, sequence and ledger chain that created it. A new login, device replacement or reinstall does not silently inherit the old queue.

## States

- `QUEUED` — eligible for evaluation.
- `RETRY_WAIT` — transient failure; deterministic bounded backoff applies.
- `ACKED` — committed or exact replay confirmed by the server.
- `QUARANTINED` — human/system reconciliation is required; automatic replay stops.

No accepted design contains a silent DROP state for a valid business event.

## Quarantine causes

Events are quarantined for structural corruption, ledger-chain mismatch, tenant/device/installation/auth-binding change, revoked device, policy rejection, business conflict, permanent rejection or retry exhaustion.

A business conflict is never resolved by last-write-wins. Inventory/count/reconciliation conflicts surface to the governed server workflow and supervisor where required.

## Retry

Only explicitly retryable transport/server failures and refreshable authentication failures may enter bounded exponential retry. Offline waiting does not consume attempts. Retry exhaustion quarantines the event instead of deleting it.

## Idempotency

A server response that proves the exact event was already committed is an acknowledged success. Same event id with different payload, same device sequence with a different event or ledger-chain corruption is not an idempotent retry and must fail closed.

## Session change

Refresh within the same logical auth binding may continue. A new auth binding cannot replay an event created under the old binding. The event remains preserved for explicit reconciliation rather than being reassigned silently.

## Production acceptance

Repository unit tests prove the state-machine contract only. Physical process-death/reboot, network flapping, token expiry, backend restart, 10k-event queues, device replacement and queue-corruption tests remain required field/managed-lab evidence before production readiness.
