"""Provision a least-privilege Workforce runtime role for CI acceptance tests."""

from pathlib import Path
import os

import psycopg


admin_url = os.environ["WORKFORCE_MIGRATION_DATABASE_URL"]
tenant_id = os.environ["WORKFORCE_TENANT_ID"]
migration = Path(__file__).resolve().parents[1] / "migrations" / "002_workforce_v29.sql"

with psycopg.connect(admin_url) as database, database.cursor() as cursor:
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (tenant_id,))
    cursor.execute(migration.read_text(encoding="utf-8"))
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
    cursor.execute("GRANT SELECT, INSERT ON workforce_audit TO workforce_runtime")
    cursor.execute("GRANT SELECT ON workforce_schema_migrations TO workforce_runtime")
    cursor.execute("GRANT EXECUTE ON FUNCTION workforce_current_tenant() TO workforce_runtime")
    cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO workforce_runtime")
    database.commit()
