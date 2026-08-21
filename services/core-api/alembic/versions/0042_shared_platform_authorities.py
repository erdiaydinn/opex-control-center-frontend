"""Master 41-44 shared-platform authorities after Academy.

Revision ID: 0042_shared_platform_authorities
Revises: 0041_academy_learning_os
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0042_shared_platform_authorities"
down_revision: str | None = "0041_academy_learning_os"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME = "opex_runtime"
_PROTECTED_TABLES = (
    "audit_field_binding",
    "platform_notification_outbox",
    "operational_search_document",
    "integration_contract_version",
)


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {table}_tenant ON {table}
        USING (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )"""
    )


def upgrade() -> None:
    op.execute(
        """CREATE TABLE audit_field_binding (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          audit_program_key varchar(160) NOT NULL,
          field_template_id uuid,
          field_mission_id uuid,
          evidence_policy_key varchar(160),
          created_by varchar(255) NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (field_template_id IS NOT NULL OR field_mission_id IS NOT NULL),
          UNIQUE (tenant_id, id)
        )"""
    )
    op.execute(
        """CREATE TABLE platform_notification_outbox (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          module varchar(80) NOT NULL,
          event_key varchar(160) NOT NULL,
          recipient_subject varchar(255) NOT NULL,
          channel varchar(30) NOT NULL,
          payload jsonb NOT NULL,
          idempotency_key varchar(255) NOT NULL,
          status varchar(20) NOT NULL DEFAULT 'PENDING',
          attempt_count integer NOT NULL DEFAULT 0,
          next_attempt_at timestamptz NOT NULL DEFAULT now(),
          created_at timestamptz NOT NULL DEFAULT now(),
          delivered_at timestamptz,
          CHECK (channel IN ('IN_APP', 'EMAIL', 'PUSH', 'WEBHOOK')),
          CHECK (status IN ('PENDING', 'DELIVERED', 'DEAD_LETTER')),
          UNIQUE (tenant_id, idempotency_key),
          UNIQUE (tenant_id, id)
        )"""
    )
    op.execute(
        """CREATE TABLE operational_search_document (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          source_module varchar(80) NOT NULL,
          source_type varchar(80) NOT NULL,
          source_id varchar(255) NOT NULL,
          title text NOT NULL,
          search_text text NOT NULL,
          permission_key varchar(160) NOT NULL,
          source_provenance jsonb NOT NULL,
          indexed_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, source_module, source_type, source_id),
          UNIQUE (tenant_id, id)
        )"""
    )
    op.execute(
        """CREATE TABLE integration_contract_version (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          connector_key varchar(160) NOT NULL,
          direction varchar(20) NOT NULL,
          version integer NOT NULL,
          schema_json jsonb NOT NULL,
          validation_policy jsonb NOT NULL,
          status varchar(20) NOT NULL DEFAULT 'DRAFT',
          created_by varchar(255) NOT NULL,
          approved_by varchar(255),
          created_at timestamptz NOT NULL DEFAULT now(),
          approved_at timestamptz,
          CHECK (direction IN ('INBOUND', 'OUTBOUND', 'BIDIRECTIONAL')),
          CHECK (status IN ('DRAFT', 'APPROVED', 'RETIRED')),
          CHECK (version > 0),
          UNIQUE (tenant_id, connector_key, version),
          UNIQUE (tenant_id, id)
        )"""
    )

    for table in _PROTECTED_TABLES:
        _tenant_rls(table)

    op.execute(
        """CREATE OR REPLACE FUNCTION integration_contract_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.status = 'APPROVED' AND (
            NEW.schema_json <> OLD.schema_json
            OR NEW.validation_policy <> OLD.validation_policy
            OR NEW.connector_key <> OLD.connector_key
            OR NEW.version <> OLD.version
          ) THEN
            RAISE EXCEPTION 'approved integration contract is immutable';
          END IF;
          IF OLD.status = 'DRAFT' AND NEW.status = 'APPROVED' AND (
            NEW.approved_by IS NULL OR NEW.approved_by = OLD.created_by
          ) THEN
            RAISE EXCEPTION 'independent integration contract approval required';
          END IF;
          RETURN NEW;
        END
        $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_integration_contract_guard
        BEFORE UPDATE ON integration_contract_version
        FOR EACH ROW EXECUTE FUNCTION integration_contract_guard()"""
    )

    op.execute(
        f"GRANT SELECT, INSERT ON {', '.join(_PROTECTED_TABLES)} TO {RUNTIME}"
    )
    op.execute(
        f"""GRANT UPDATE (
          status, attempt_count, next_attempt_at, delivered_at
        ) ON platform_notification_outbox TO {RUNTIME}"""
    )
    op.execute(
        f"""GRANT UPDATE (
          status, approved_by, approved_at
        ) ON integration_contract_version TO {RUNTIME}"""
    )
    op.execute(f"REVOKE DELETE ON {', '.join(_PROTECTED_TABLES)} FROM {RUNTIME}")


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_integration_contract_guard "
        "ON integration_contract_version"
    )
    op.execute("DROP FUNCTION IF EXISTS integration_contract_guard()")
    for table in reversed(_PROTECTED_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
