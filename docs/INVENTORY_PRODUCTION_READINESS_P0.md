# EAY Inventory Production Readiness P0

Canonical continuation base: PR #61, branch `product/workforce-field-pilot-v28`,
head `ed3a933bd9e4b979d2d73cf9c548215f3090626f`.

Legacy PR #3 (`agent/opex-inventory-v22`, `9546c9a1...`) is evidence/reference
only. It is not the production base and its debug APK is not releasable.

## Implemented production boundaries

- production mode has no SQLite fallback; legacy endpoints return HTTP 410
- PostgreSQL tenant RLS, durable events/responses/revisions/audit/outbox
- PostgreSQL advisory-lock exact-event serialization independent of Redis
- event UUID + device sequence uniqueness and payload-substitution rejection
- P-256 signed timestamp/nonce/body-hash device proof and replay nonce table
- single-use MDM activation, stable MDM UUID and employee binding
- backend-authoritative blind task, unexpected SKU and reconciliation surfaces
- optimistic document revision and maker-checker approval/lock separation
- OIDC authorization-code + PKCE Android entry, no embedded password form
- certificate-pinned HTTPS with active and backup pins
- SQLCipher 4.17 encrypted Room queue with Android Keystore-wrapped random key
- WorkManager retry, token-expiry pause and queue-integrity fail-closed behavior
- managed signing workflow, signature/hash verification and protected Environment
- Android Enterprise force-install/high-priority update policy template

## Release gates

The managed release job intentionally fails unless the protected GitHub
Environment supplies the corporate keystore, alias/passwords, HTTPS API, OIDC
issuer/client and two different certificate pins. Debug artifacts never satisfy
the release gate.

Production readiness remains below 95% until all of the following are evidenced:

- signed release APK and verified signing certificate lineage
- corporate MDM private-app deployment and device replacement procedure
- real IdP issuer/client/audience plus `tenant_id`, `employee_id`, roles,
  permissions and `warehouse_scope` claim mapping
- migration executed by production migration identity and runtime RLS role tests
- load target agreed and passed with p95/error/idempotency thresholds
- backup/restore plus DB/Redis restart and regional DR rehearsal
- every required physical Zebra row passed
- controlled field pilot signed off by Operations, Security and IT/MDM owners

No percentage at or above 95 may be reported from repository tests alone.
