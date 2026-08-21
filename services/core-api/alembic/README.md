# OPEX Database Migration Policy

- Every schema change is an Alembic revision.
- Never edit an already deployed revision; add a new revision.
- Test `alembic upgrade head` on a fresh PostgreSQL database in CI.
- Tenant-owned tables require `tenant_id`, Row-Level Security and `FORCE ROW LEVEL SECURITY`.
- Composite foreign keys must prevent cross-tenant references.
- Runtime queries must set transaction-local `app.tenant_id` from the verified principal.
- Production uses separate migration and runtime database roles.
- Destructive migrations require a backup, restore test, staged rollout and explicit rollback plan.
- Data migrations must be restartable or idempotent.
- Never place customer data, credentials or secrets inside migration files.
