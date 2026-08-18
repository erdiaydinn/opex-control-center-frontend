"""Add tenant-safe Planogram Store DNA approval authority after Field governance.

Revision ID: 0030_planogram_store_dna_foundation
Revises: 0029_field_template_lifecycle_column_grant
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_planogram_store_dna_foundation"
down_revision: str = "0029_field_template_lifecycle_column_grant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(f"""CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE planogram_store_dna_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            store_code varchar(80) NOT NULL,
            store_name varchar(160),
            version_number integer NOT NULL CHECK (version_number > 0),
            source varchar(40) NOT NULL CHECK (source IN
            ('warehouse_bootstrap','warehouse_revision','inventory_seed')),
            status varchar(20) NOT NULL DEFAULT 'draft' CHECK (status IN
            ('draft','submitted','approved','rejected','superseded')),
            configuration jsonb NOT NULL,
            summary jsonb NOT NULL,
            configuration_sha256 char(64) NOT NULL CHECK (configuration_sha256 ~
            '^[0-9a-f]{64}$'),
            geometry_attested boolean NOT NULL DEFAULT FALSE,
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            submitted_by varchar(255), submitted_at timestamptz,
            approved_by varchar(255), approved_at timestamptz,
            rejected_by varchar(255), rejected_at timestamptz, rejection_reason varchar(500),
            supersedes_version_id uuid,
            CONSTRAINT uq_planogram_store_dna_version UNIQUE (tenant_id, store_code,
            version_number),
            CONSTRAINT uq_planogram_store_dna_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT fk_planogram_store_dna_supersedes FOREIGN KEY (tenant_id,
            supersedes_version_id)
                REFERENCES planogram_store_dna_versions(tenant_id, id),
            CONSTRAINT ck_planogram_store_dna_rejection CHECK (
                status <> 'rejected' OR (rejected_by IS NOT NULL AND rejected_at IS NOT NULL AND
                rejection_reason IS NOT NULL)
            )
        )
        """)
    op.execute(
        "CREATE UNIQUE INDEX uq_planogram_store_dna_active_edit ON planogram_store_dna_versions"
        " (tenant_id, store_code) WHERE status IN ('draft','submitted')"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_planogram_store_dna_approved ON planogram_store_dna_versions"
        " (tenant_id, store_code) WHERE status='approved'"
    )
    op.execute(
        "CREATE INDEX ix_planogram_store_dna_store_status ON planogram_store_dna_versions"
        " (tenant_id, store_code, status, version_number DESC)"
    )
    op.execute("""
        CREATE TABLE planogram_store_dna_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            store_dna_version_id uuid NOT NULL,
            event_type varchar(40) NOT NULL CHECK (event_type IN
    ('bootstrapped','updated','submitted','approved','rejected','superseded','revised')),
            actor_subject varchar(255) NOT NULL,
            from_status varchar(20), to_status varchar(20), reason varchar(500),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_planogram_store_dna_event_version FOREIGN KEY (tenant_id,
            store_dna_version_id)
                REFERENCES planogram_store_dna_versions(tenant_id, id) ON DELETE RESTRICT
        )
        """)
    op.execute(
        "CREATE INDEX ix_planogram_store_dna_events_version ON planogram_store_dna_events"
        " (tenant_id, store_dna_version_id, created_at)"
    )
    _tenant_policy("planogram_store_dna_versions")
    _tenant_policy("planogram_store_dna_events")
    op.execute("""
        CREATE OR REPLACE FUNCTION planogram_store_dna_immutable_history()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = 'superseded' THEN
                RAISE EXCEPTION 'Superseded Store DNA versions are immutable';
            END IF;
            IF OLD.status = 'approved' THEN
                IF NEW.status <> 'superseded'
                   OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                   OR NEW.store_code IS DISTINCT FROM OLD.store_code
                   OR NEW.store_name IS DISTINCT FROM OLD.store_name
                   OR NEW.version_number IS DISTINCT FROM OLD.version_number
                   OR NEW.source IS DISTINCT FROM OLD.source
                   OR NEW.configuration IS DISTINCT FROM OLD.configuration
                   OR NEW.summary IS DISTINCT FROM OLD.summary
                   OR NEW.configuration_sha256 IS DISTINCT FROM OLD.configuration_sha256
                   OR NEW.geometry_attested IS DISTINCT FROM OLD.geometry_attested
                   OR NEW.created_by IS DISTINCT FROM OLD.created_by
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at
                   OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by
                   OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at
                   OR NEW.approved_by IS DISTINCT FROM OLD.approved_by
                   OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
                   OR NEW.rejected_by IS DISTINCT FROM OLD.rejected_by
                   OR NEW.rejected_at IS DISTINCT FROM OLD.rejected_at
                   OR NEW.rejection_reason IS DISTINCT FROM OLD.rejection_reason
                   OR NEW.supersedes_version_id IS DISTINCT FROM OLD.supersedes_version_id
    THEN RAISE EXCEPTION 'Approved Store DNA is immutable except approved -> superseded';
                END IF;
            END IF;
            RETURN NEW;
        END; $$
        """)
    op.execute(
        "CREATE TRIGGER trg_planogram_store_dna_immutable_history BEFORE UPDATE ON"
        " planogram_store_dna_versions FOR EACH ROW EXECUTE FUNCTION"
        " planogram_store_dna_immutable_history()"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON planogram_store_dna_versions TO {RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON planogram_store_dna_events TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_planogram_store_dna_immutable_history ON"
        " planogram_store_dna_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS planogram_store_dna_immutable_history()")
    op.execute("DROP TABLE planogram_store_dna_events")
    op.execute("DROP TABLE planogram_store_dna_versions")
