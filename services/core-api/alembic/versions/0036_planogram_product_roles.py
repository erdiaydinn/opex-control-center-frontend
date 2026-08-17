"""Seed canonical Planogram editor/admin system roles for existing tenants.

Revision ID: 0036_planogram_product_roles
Revises: 0035_planogram_plan_lifecycle_hardening
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0036_planogram_product_roles"
down_revision: str = "0035_planogram_plan_lifecycle_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLANOGRAM_EDITOR_PERMISSIONS = (
    "module:planogram:view",
    "feature:planogram:layoutView",
    "feature:planogram:layoutEdit",
    "feature:planogram:fixtureEdit",
    "action:planogram:view",
    "action:planogram:create",
    "action:planogram:edit",
    "action:planogram:export",
)

PLANOGRAM_ADMIN_PERMISSIONS = PLANOGRAM_EDITOR_PERMISSIONS + (
    "module:planogram:admin",
    "feature:planogram:ruleEdit",
    "feature:planogram:productAssign",
    "feature:planogram:aiRecommend",
    "action:planogram:approve",
    "action:planogram:delete",
    "action:planogram:acceptFieldEvidence",
)

ROLE_POLICIES = {
    "planogram_editor": ("Planogram Editor", PLANOGRAM_EDITOR_PERMISSIONS),
    "planogram_admin": ("Planogram Admin", PLANOGRAM_ADMIN_PERMISSIONS),
}


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM roles
                    WHERE key='{escaped}' AND is_system IS FALSE
                ) THEN
                    RAISE EXCEPTION 'Canonical Planogram role collision: {escaped}';
                END IF;
            END $$;
            """
        )

    for role_key, (role_name, permissions) in ROLE_POLICIES.items():
        escaped_key = role_key.replace("'", "''")
        escaped_name = role_name.replace("'", "''")
        permission_array = _sql_array(permissions)
        op.execute(
            f"""
            INSERT INTO roles (tenant_id, key, name, is_system)
            SELECT id, '{escaped_key}', '{escaped_name}', TRUE
            FROM tenants
            ON CONFLICT (tenant_id, key)
            DO UPDATE SET name=EXCLUDED.name
            WHERE roles.is_system IS TRUE
            """
        )
        op.execute(
            f"""
            INSERT INTO role_permissions (tenant_id, role_id, permission_key, scope)
            SELECT r.tenant_id, r.id, p.permission_key, '{{}}'::jsonb
            FROM roles r
            CROSS JOIN unnest({permission_array}) AS p(permission_key)
            WHERE r.key='{escaped_key}' AND r.is_system IS TRUE
            ON CONFLICT (tenant_id, role_id, permission_key)
            DO UPDATE SET scope='{{}}'::jsonb
            """
        )


def downgrade() -> None:
    role_keys = "'planogram_editor','planogram_admin'"
    op.execute(
        f"""
        DELETE FROM role_permissions rp
        USING roles r
        WHERE rp.tenant_id=r.tenant_id
          AND rp.role_id=r.id
          AND r.key IN ({role_keys})
          AND r.is_system IS TRUE
        """
    )
    op.execute(
        f"""
        DELETE FROM roles r
        WHERE r.key IN ({role_keys})
          AND r.is_system IS TRUE
          AND NOT EXISTS (
              SELECT 1 FROM membership_roles mr
              WHERE mr.tenant_id=r.tenant_id AND mr.role_id=r.id
          )
        """
    )
