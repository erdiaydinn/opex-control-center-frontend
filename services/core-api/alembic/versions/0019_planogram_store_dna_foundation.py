"""Add tenant-safe Planogram Store DNA approval foundation.

Revision ID: 0019_planogram_store_dna_foundation
Revises: 0018_academy_product_roles
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_planogram_store_dna_foundation"
down_revision: str = "0018_academy_product_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"

PLANOGRAM_EDITOR = (
    "module:planogram:view",
    "feature:planogram:layoutView",
    "feature:planogram:layoutEdit",
    "feature:planogram:fixtureEdit",
    "action:planogram:view",
    "action:planogram:create",
    "action:planogram:edit",
    "action:planogram:export",
)

PLANOGRAM_ADMIN = PLANOGRAM_EDITOR + (
    "module:planogram:admin",
    "feature:planogram:ruleEdit",
    "feature:planogram:productAssign",
    "feature:planogram:aiRecommend",
    "action:planogram:approve",
    "action:planogram:delete",
)

ROLE_POLICIES = {
    "planogram_editor": ("Planogram Editor", PLANOGRAM_EDITOR),
    "planogram_admin": ("Planogram Admin", PLANOGRAM_ADMIN),
}


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''
        CREATE POLICY "{table_name}_tenant_isolation"
        ON "{table_name}"
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        '''
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE planogram_store_dna_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            store_code varchar(80) NOT NULL,
            store_name varchar(160),
            version_number integer NOT NULL,
            source varchar(40) NOT NULL DEFAULT 'warehouse_bootstrap',
            status varchar(20) NOT NULL DEFAULT 'draft',
            configuration jsonb NOT NULL,
            summary jsonb NOT NULL,
            configuration_sha256 char(64) NOT NULL,
            geometry_attested boolean NOT NULL DEFAULT FALSE,
            created_by varchar(255) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            submitted_by varchar(255),
            submitted_at timestamptz,
            approved_by varchar(255),
            approved_at timestamptz,
            rejected_by varchar(255),
            rejected_at timestamptz,
            rejection_reason varchar(500),
            supersedes_version_id uuid,
            CONSTRAINT fk_planogram_store_dna_supersedes
                FOREIGN KEY (tenant_id, supersedes_version_id)
                REFERENCES planogram_store_dna_versions(tenant_id, id),
            CONSTRAINT ck_planogram_store_dna_status
                CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'superseded')),
            CONSTRAINT ck_planogram_store_dna_source
                CHECK (source IN ('warehouse_bootstrap', 'warehouse_revision', 'inventory_seed')),
            CONSTRAINT ck_planogram_store_dna_version CHECK (version_number > 0),
            CONSTRAINT ck_planogram_store_dna_sha
                CHECK (configuration_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_planogram_store_dna_rejection
                CHECK (
                    status <> 'rejected'
                    OR (rejected_by IS NOT NULL AND rejected_at IS NOT NULL AND rejection_reason IS NOT NULL)
                ),
            CONSTRAINT uq_planogram_store_dna_version
                UNIQUE (tenant_id, store_code, version_number),
            CONSTRAINT uq_planogram_store_dna_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_planogram_store_dna_active_edit
        ON planogram_store_dna_versions (tenant_id, store_code)
        WHERE status IN ('draft', 'submitted')
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_planogram_store_dna_approved
        ON planogram_store_dna_versions (tenant_id, store_code)
        WHERE status = 'approved'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_planogram_store_dna_store_status
        ON planogram_store_dna_versions (tenant_id, store_code, status, version_number DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE planogram_store_dna_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            store_dna_version_id uuid NOT NULL,
            event_type varchar(40) NOT NULL,
            actor_subject varchar(255) NOT NULL,
            from_status varchar(20),
            to_status varchar(20),
            reason varchar(500),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_planogram_store_dna_event_version
                FOREIGN KEY (tenant_id, store_dna_version_id)
                REFERENCES planogram_store_dna_versions(tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_planogram_store_dna_event_type
                CHECK (event_type IN ('bootstrapped', 'updated', 'submitted', 'approved', 'rejected', 'superseded', 'revised')),
            CONSTRAINT ck_planogram_store_dna_event_from_status
                CHECK (from_status IS NULL OR from_status IN ('draft', 'submitted', 'approved', 'rejected', 'superseded')),
            CONSTRAINT ck_planogram_store_dna_event_to_status
                CHECK (to_status IS NULL OR to_status IN ('draft', 'submitted', 'approved', 'rejected', 'superseded'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_planogram_store_dna_events_version
        ON planogram_store_dna_events (tenant_id, store_dna_version_id, created_at)
        """
    )

    _tenant_policy("planogram_store_dna_versions")
    _tenant_policy("planogram_store_dna_events")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION planogram_store_dna_immutable_approved()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
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
                THEN
                    RAISE EXCEPTION 'Approved Store DNA is immutable except approved -> superseded';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_planogram_store_dna_immutable_approved
        BEFORE UPDATE ON planogram_store_dna_versions
        FOR EACH ROW
        EXECUTE FUNCTION planogram_store_dna_immutable_approved()
        """
    )

    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON planogram_store_dna_versions TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT ON planogram_store_dna_events TO {RUNTIME_ROLE}"
    )

    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM roles
                    WHERE key = '{escaped}' AND is_system IS FALSE
                ) THEN
                    RAISE EXCEPTION 'Canonical Planogram role collision: {escaped}';
                END IF;
            END $$;
            """
        )

    for role_key, (role_name, permissions) in ROLE_POLICIES.items():
        escaped_key = role_key.replace("'", "''")
        escaped_name = role_name.replace("'", "''")
        permission_array = _sql_array(tuple(permissions))
        op.execute(
            f"""
            INSERT INTO roles (tenant_id, key, name, is_system)
            SELECT id, '{escaped_key}', '{escaped_name}', TRUE
            FROM tenants
            ON CONFLICT (tenant_id, key)
            DO UPDATE SET name = EXCLUDED.name
            WHERE roles.is_system IS TRUE
            """
        )
        op.execute(
            f"""
            INSERT INTO role_permissions (tenant_id, role_id, permission_key, scope)
            SELECT r.tenant_id, r.id, p.permission_key, '{{}}'::jsonb
            FROM roles AS r
            CROSS JOIN unnest({permission_array}) AS p(permission_key)
            WHERE r.key = '{escaped_key}' AND r.is_system IS TRUE
            ON CONFLICT (tenant_id, role_id, permission_key)
            DO UPDATE SET scope = '{{}}'::jsonb
            """
        )


def downgrade() -> None:
    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            f"""
            DELETE FROM role_permissions AS rp
            USING roles AS r
            WHERE rp.tenant_id = r.tenant_id
              AND rp.role_id = r.id
              AND r.key = '{escaped}'
              AND r.is_system IS TRUE
            """
        )
        op.execute(
            f"""
            DELETE FROM roles AS r
            WHERE r.key = '{escaped}'
              AND r.is_system IS TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM membership_roles AS mr
                  WHERE mr.tenant_id = r.tenant_id
                    AND mr.role_id = r.id
              )
            """
        )

    op.execute("DROP TRIGGER IF EXISTS trg_planogram_store_dna_immutable_approved ON planogram_store_dna_versions")
    op.execute("DROP FUNCTION IF EXISTS planogram_store_dna_immutable_approved()")
    op.execute("DROP TABLE planogram_store_dna_events")
    op.execute("DROP TABLE planogram_store_dna_versions")
