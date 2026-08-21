# OPEX Database Security Runbook

## Role separation

OPEX uses two PostgreSQL roles with different purposes:

- `opex_migrator`: owns schema migrations and is never used by the running API.
- `opex_runtime`: used by Core API, is non-superuser and has `NOBYPASSRLS`.

The runtime and migration connection URLs must always differ. Core API refuses to start when they are identical.

## Required environment values

```text
OPEX_POSTGRES_DB=opex
OPEX_POSTGRES_MIGRATOR_PASSWORD=<strong migration password>
OPEX_POSTGRES_RUNTIME_PASSWORD=<different strong runtime password>
OPEX_MIGRATION_DATABASE_URL=postgresql+asyncpg://opex_migrator:<migration password>@postgres:5432/opex
OPEX_DATABASE_URL=postgresql+asyncpg://opex_runtime:<runtime password>@postgres:5432/opex
```

Passwords containing URL-reserved characters must be percent-encoded inside connection URLs.

## New local environment

On the first PostgreSQL volume initialization, `infra/postgres/init-runtime-role.sh` creates `opex_runtime` as:

```text
NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS
```

The migration service then grants only the required table privileges. Row-Level Security remains the tenant data boundary.

## Existing local volume migration

The PostgreSQL entrypoint does not rerun initialization scripts on an existing data volume. For disposable local development data, reset the stack:

```powershell
docker compose -f docker-compose.platform.yml down -v
docker compose -f docker-compose.platform.yml up --build -d
```

This deletes local database, Redis and Ollama volumes. Do not use it where data must be preserved.

For a non-disposable environment, create `opex_runtime` manually with an approved password, confirm `NOBYPASSRLS`, set both connection URLs, and then run:

```powershell
docker compose -f docker-compose.platform.yml run --rm migrate
```

Back up and test restoration before changing production roles or credentials.

## Verification

The CI isolation test connects as `opex_runtime`, not as the table owner or PostgreSQL superuser. It proves:

1. Tenant A reads its own row.
2. Tenant B cannot read Tenant A's row.
3. A transaction without tenant context reads no tenant rows.
4. Tenant B cannot write a Tenant A row.

A test run through `opex_migrator`, the table owner, or a superuser is not accepted as RLS evidence.

## Production requirements

- Store both passwords in a managed secret store, not `.env` committed to Git.
- Rotate runtime and migrator credentials independently.
- Do not grant `BYPASSRLS`, superuser, role creation or database creation to `opex_runtime`.
- Restrict network access so application containers cannot reach PostgreSQL with migrator credentials.
- Run migrations as a controlled deployment job, never from a web request.
- Alert on failed RLS tests, permission changes and unexpected grants.
