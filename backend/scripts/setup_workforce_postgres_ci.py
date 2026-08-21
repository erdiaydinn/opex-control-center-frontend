"""Provision a least-privilege Workforce runtime role for CI acceptance tests."""

from pathlib import Path
import os
import re

import psycopg


admin_url = os.environ["WORKFORCE_MIGRATION_DATABASE_URL"]
tenant_id = os.environ["WORKFORCE_TENANT_ID"]
migration_dir = Path(__file__).resolve().parents[1] / "migrations"
v29_migration = migration_dir / "002_workforce_v29.sql"
v30_migration = migration_dir / "003_workforce_v30_acceptance.sql"
v31_migration = migration_dir / "004_workforce_v31_lifecycle_acceptance.sql"
v32_migration = migration_dir / "005_workforce_v32_identity_revocation.sql"


def workforce_version(path: Path) -> int | None:
    match = re.search(r"_workforce_v(\d+)_", path.name)
    return int(match.group(1)) if match else None


post_v32_migrations = sorted(
    (
        path
        for path in migration_dir.glob("*_workforce_v*.sql")
        if (workforce_version(path) or 0) > 32
    ),
    key=lambda path: workforce_version(path) or 0,
)
expected_post_v32_versions = [workforce_version(path) for path in post_v32_migrations]

with psycopg.connect(admin_url) as database, database.cursor() as cursor:
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (tenant_id,))
    cursor.execute(v29_migration.read_text(encoding="utf-8"))

    # Rehearse the real upgrade shape only while the recruitment tables still
    # have their pre-V30 schema. After V30 the primary/unique authority is
    # tenant-aware, so replaying a legacy ON CONFLICT(id) fixture would be both
    # invalid and unlike a real migration replay.
    cursor.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema='public'
            AND table_name='recruitment_settings'
            AND column_name='tenant_id'
        )
        """
    )
    recruitment_already_tenant_aware = bool(cursor.fetchone()[0])
    if not recruitment_already_tenant_aware:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS recruitment_requests (
              id text PRIMARY KEY,status text NOT NULL,warehouse_id text NOT NULL,
              created_at timestamptz NOT NULL,payload jsonb NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recruitment_settings (
              id text PRIMARY KEY,payload jsonb NOT NULL,updated_at timestamptz NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recruitment_norms (
              id text PRIMARY KEY,warehouse text NOT NULL,payload jsonb NOT NULL,updated_at timestamptz NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS recruitment_norm_warehouse_idx
              ON recruitment_norms(lower(warehouse));
            CREATE TABLE IF NOT EXISTS recruitment_email_outbox (
              id text PRIMARY KEY,request_id text NOT NULL,recipient_group text NOT NULL,
              status text NOT NULL DEFAULT 'PENDING',attempts integer NOT NULL DEFAULT 0,
              last_error text,created_at timestamptz NOT NULL,delivered_at timestamptz,payload jsonb NOT NULL
            );
            INSERT INTO recruitment_settings(id,payload,updated_at)
            VALUES ('v29-upgrade-fixture','{}'::jsonb,now()) ON CONFLICT (id) DO NOTHING;
            """
        )

    cursor.execute(v30_migration.read_text(encoding="utf-8"))
    cursor.execute(
        """INSERT INTO recruitment_norms(tenant_id,id,warehouse,payload,updated_at)
           VALUES (%s,'v31-temp-fixture','Dicle (Diyarbakır)',
                   '{"norm":7,"warehouse":"Dicle (Diyarbakır)"}'::jsonb,now())
           ON CONFLICT (tenant_id,id) DO NOTHING""",
        (tenant_id,),
    )
    cursor.execute(v31_migration.read_text(encoding="utf-8"))
    cursor.execute(v32_migration.read_text(encoding="utf-8"))

    # V33+ Workforce authority is intentionally discovered from the versioned
    # migration series instead of freezing CI at one roadmap checkpoint. This
    # keeps PostgreSQL acceptance aligned with the current repository schema
    # while preserving the special V29 -> V32 upgrade rehearsal above.
    for migration in post_v32_migrations:
        cursor.execute(migration.read_text(encoding="utf-8"))

    cursor.execute(
        """SELECT tenant_id FROM recruitment_settings
           WHERE id='v29-upgrade-fixture'"""
    )
    upgraded_tenant = cursor.fetchone()
    if upgraded_tenant is None or upgraded_tenant[0] != tenant_id:
        raise RuntimeError("V29 -> V30 recruitment tenant backfill failed")
    cursor.execute(
        """SELECT payload->>'base_norm',payload->>'norm',payload->>'temporary_effective_until'
           FROM recruitment_norms WHERE tenant_id=%s AND id='v31-temp-fixture'""",
        (tenant_id,),
    )
    if cursor.fetchone() != ("7", "8", "2026-09-30"):
        raise RuntimeError("V30 -> V31 temporary +1 norm preservation failed")

    if expected_post_v32_versions:
        cursor.execute(
            "SELECT version FROM workforce_schema_migrations WHERE version = ANY(%s) ORDER BY version",
            (expected_post_v32_versions,),
        )
        installed_versions = [row[0] for row in cursor.fetchall()]
        if installed_versions != expected_post_v32_versions:
            raise RuntimeError(
                "Workforce authority migration bootstrap incomplete: "
                f"expected={expected_post_v32_versions} installed={installed_versions}"
            )

    cursor.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='workforce_runtime') THEN
            CREATE ROLE workforce_runtime LOGIN PASSWORD 'workforce_runtime_ci';
          ELSE
            ALTER ROLE workforce_runtime WITH LOGIN PASSWORD 'workforce_runtime_ci';
          END IF;
        END $$;
        """
    )
    cursor.execute(
        """INSERT INTO workforce_tenant_bindings(role_name, tenant_id)
           VALUES ('workforce_runtime', %s)
           ON CONFLICT (role_name) DO UPDATE SET tenant_id=EXCLUDED.tenant_id""",
        (tenant_id,),
    )
    cursor.execute("GRANT CONNECT ON DATABASE workforce_ci TO workforce_runtime")
    cursor.execute("GRANT USAGE ON SCHEMA public TO workforce_runtime")
    cursor.execute(
        """GRANT SELECT, INSERT, UPDATE, DELETE
           ON workforce_entities, workforce_collection_versions, workforce_notification_outbox,
              workforce_identity_revocation_outbox
           TO workforce_runtime"""
    )
    cursor.execute(
        """GRANT SELECT, INSERT, UPDATE, DELETE
           ON recruitment_requests, recruitment_settings, recruitment_norms, recruitment_email_outbox
           TO workforce_runtime"""
    )
    cursor.execute("GRANT SELECT, INSERT ON workforce_audit TO workforce_runtime")
    cursor.execute("GRANT SELECT ON workforce_schema_migrations TO workforce_runtime")

    # Derived authority evidence is append-only. Runtime can read and append
    # snapshots/proposals/receipts, but cannot mutate or delete them. Approval
    # authority tables remain read-only for this least-privilege runtime role.
    cursor.execute(
        """GRANT SELECT, INSERT ON
           workforce_demand_snapshots,
           workforce_capacity_snapshots,
           workforce_dpi_snapshots,
           workforce_optimizer_proposals,
           workforce_replan_scenarios,
           workforce_replan_proposals,
           workforce_manager_overrides,
           workforce_override_outcomes,
           workforce_override_learning_drafts,
           workforce_optimizer_learning_receipts
           TO workforce_runtime"""
    )
    cursor.execute(
        """GRANT SELECT ON
           workforce_labor_standard_versions,
           workforce_replan_model_versions,
           workforce_override_learning_versions
           TO workforce_runtime"""
    )
    cursor.execute("GRANT EXECUTE ON FUNCTION workforce_current_tenant() TO workforce_runtime")
    cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO workforce_runtime")
    database.commit()
