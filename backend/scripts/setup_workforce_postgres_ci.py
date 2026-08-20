"""Provision a least-privilege Workforce runtime role for CI acceptance tests."""

from pathlib import Path
import os

import psycopg


admin_url = os.environ["WORKFORCE_MIGRATION_DATABASE_URL"]
tenant_id = os.environ["WORKFORCE_TENANT_ID"]
v29_migration = Path(__file__).resolve().parents[1] / "migrations" / "002_workforce_v29.sql"
v30_migration = Path(__file__).resolve().parents[1] / "migrations" / "003_workforce_v30_acceptance.sql"
v31_migration = Path(__file__).resolve().parents[1] / "migrations" / "004_workforce_v31_lifecycle_acceptance.sql"
v32_migration = Path(__file__).resolve().parents[1] / "migrations" / "005_workforce_v32_identity_revocation.sql"
authority_migrations = tuple(
    Path(__file__).resolve().parents[1] / "migrations" / name
    for name in (
        "010_workforce_v33_demand_authority.sql",
        "011_workforce_v34_capacity_authority.sql",
        "012_workforce_v35_dpi_authority.sql",
        "013_workforce_v36_optimizer_authority.sql",
        "014_workforce_v37_replan_authority.sql",
        "015_workforce_v38_override_learning.sql",
        "023_recruitment_candidate_upload_authority.sql",
        "024_recruitment_production_authority.sql",
        "025_recruitment_request_evidence_scan_authority.sql",
        "026_recruitment_evidence_release_authority.sql",
        "027_recruitment_scanner_role_isolation.sql",
        "028_recruitment_orchestration.sql",
        "029_workforce_audit_chain_fencing.sql",
        "030_recruitment_interview_scheduling.sql",
    )
)
recruitment_security_migrations = authority_migrations[-8:]

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
    # CI disables application auto-migration to exercise the production
    # bootstrap contract. Keep the full authority chain ordered and replay-safe.
    for migration in authority_migrations:
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
    cursor.execute("GRANT EXECUTE ON FUNCTION workforce_current_tenant() TO workforce_runtime")
    cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO workforce_runtime")

    # Security/product migrations grant role privileges conditionally when the
    # runtime role exists. Replay after provisioning so CI proves production shape.
    for migration in recruitment_security_migrations:
        cursor.execute(migration.read_text(encoding="utf-8"))

    cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
    if int(cursor.fetchone()[0] or 0) < 46:
        raise RuntimeError("Canonical Workforce/Hiring schema did not reach V46")
    database.commit()
