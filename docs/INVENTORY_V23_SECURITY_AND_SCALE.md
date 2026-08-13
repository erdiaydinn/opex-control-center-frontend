# OPEX Inventory V23 — Security and Scale Gate

V23 closes the pilot-only identity and lock gaps without weakening blind-count rules.

## Implemented

- Admin-created named users, roles, active/passive state and warehouse assignments.
- One-time bootstrap admin; no hard-coded password.
- PBKDF2-SHA256 password hashing with 600,000 iterations and 256-bit salts.
- Five-failure account lock, 15-minute access tokens, rotating 7-day refresh tokens.
- Token version invalidation when a user is disabled or password changes.
- Server-derived warehouse scope; client warehouse input is never authorization evidence.
- Redis atomic location locks with TTL and PostgreSQL RLS migration.
- Idempotent scan events and append-only audit trails.
- Android secrets and offline queue encrypted with Android Keystore-backed AES.
- HTTPS-only Android network policy.
- PostgreSQL and Redis are isolated on an internal Docker network and expose no host ports.

## Go-live gates

1. Replace every `CHANGE_...` value with independently generated secrets.
2. Run `backend/migrations/001_inventory_v23.sql` as the migration owner, then run the app with a non-owner DB role.
3. Delete bootstrap admin environment variables after first login and force the initial password change.
4. Terminate TLS at the approved company ingress; do not publish ports 8000, 5432, 6379 or 9090.
5. Store secrets in the company secret manager, not `.env`, for production.
6. Require signed release APK, MDM enrollment and device revocation.
7. Run `ops/load/k6-inventory-v23.js` in 400, 2,000, 5,000 and 10,000-user stages.
8. Approve restore test, Redis-loss test, API rolling-restart test and cross-warehouse red-team test.

The package contains the production controls. Actual 500-warehouse capacity is accepted only after the target cloud environment passes these gates.
