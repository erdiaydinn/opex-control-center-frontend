# EAY Inventory Encrypted Queue v4

## Change

The proven SQLCipher/Room queue now has durable quarantine semantics rather than only `PENDING` and `ACKED`.

States:

- `PENDING`
- `RETRY_WAIT`
- `ACKED`
- `QUARANTINED`

A quarantined event retains its immutable id, device sequence, encrypted canonical payload, payload hash and auth binding plus a machine-readable quarantine reason and last server code.

## Fail-closed handling

- local payload hash corruption -> `CORRUPT_EVENT` quarantine;
- interactive auth-binding change -> `AUTH_BINDING_CHANGED` quarantine;
- HTTP 403 -> `POLICY_REJECTED` quarantine;
- HTTP 409 -> `BUSINESS_CONFLICT` quarantine;
- HTTP 410 -> `DEVICE_REVOKED` quarantine;
- other permanent 4xx -> `PERMANENT_REJECTED` quarantine;
- 408/429/5xx/network exception -> bounded retry;
- repeated 401 clears the in-memory access token and forces refresh within the same auth binding; retry exhaustion quarantines;
- exact idempotent replay is ACKED, never duplicated.

A permanent bad event no longer destroys the worker run or deletes evidence. Later independent device-sequence events may continue because the production backend enforces event-id/device-nonce uniqueness rather than requiring contiguous sequence numbers.

## Retry durability

`RETRY_WAIT` is included in pending accounting. If no event is due yet but retryable work still exists, WorkManager returns retry rather than success, preventing a future-due event from being stranded.

## Migration

Room schema v3 -> v4 adds nullable `quarantineReason`, nullable `lastServerCode`, and an index on `(state,nextAttemptAt)`. Existing event identity and encrypted database key handling remain unchanged.

## Remaining field proof

Process death during state transition, reboot with future-due retries, 10k-event pressure, SQLCipher corruption recovery, WorkManager OS throttling, network flapping and supervisor quarantine-resolution UX remain managed-device acceptance work and cannot be closed by repository tests alone.
