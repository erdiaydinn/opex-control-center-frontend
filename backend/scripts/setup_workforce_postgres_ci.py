"""Provision a least-privilege Workforce runtime role for CI acceptance tests."""

from pathlib import Path
import os

import psycopg


admin_url = os.environ["WORKFORCE_MIGRATION_DATABASE_URL"]
tenant_id = os.environ["WORKFORCE_TENANT_ID"]
v29_migration = Path(__file__).resolve().parents[1] / "migrations" / "002_workforce_v29.sql"
v30_migration = Path(__file__).resolve().parents[1] / "migrations" / "003_workforce_v30_acceptance.sql"

with psycopg.connect(admin_url) as database, database.cursor() as cursor:
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (tenant_id,))
    cursor.execute(v29_migration.read_text(encoding="utf-8"))
    # Rehearse the real upgrade shape: V29 created these tables at application
    # startup without tenant columns. Seed a row so V30 must preserve/backfill it.
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
        """SELECT tenant_id FROM recruitment_settings
           WHERE id='v29-upgrade-fixture'"""
    )
    upgraded_tenant = cursor.fetchone()
    if upgraded_tenant is None or upgraded_tenant[0] != tenant_id:
        raise RuntimeError("V29 -> V30 recruitment tenant backfill failed")
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
           ON workforce_entities, workforce_collection_versions, workforce_notification_outbox
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
    database.commit()
