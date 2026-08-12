"""Add explicit Jarvis read-tool permissions.

Revision ID: 0009_ai_tool_permissions
Revises: 0008_preauth_provider_resolver
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_ai_tool_permissions"
down_revision: str | None = "0008_preauth_provider_resolver"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AI_TOOL_PERMISSIONS = (
    "action:ai_assistant:executeOpsRead",
    "action:ai_assistant:executeCatalogRead",
    "action:ai_assistant:executeLegalRead",
)


def upgrade() -> None:
    # Fail closed: the first migration only grants the new AI read
    # capabilities to canonical system super-admin roles. Every other
    # role must receive an explicit tenant-scoped DB grant later.
    op.execute(
        """
        WITH desired(permission_key) AS (
            VALUES
            ('action:ai_assistant:executeOpsRead'),
            ('action:ai_assistant:executeCatalogRead'),
            ('action:ai_assistant:executeLegalRead')
        )
        INSERT INTO role_permissions (
            tenant_id,
            role_id,
            permission_key,
            scope
        )
        SELECT
            r.tenant_id,
            r.id,
            desired.permission_key,
            '{}'::jsonb
        FROM roles AS r
        CROSS JOIN desired
        WHERE r.is_system = true
          AND r.key = 'super_admin'
        ON CONFLICT (
            tenant_id,
            role_id,
            permission_key
        )
        DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions AS rp
        USING roles AS r
        WHERE rp.tenant_id = r.tenant_id
          AND rp.role_id = r.id
          AND r.is_system = true
          AND r.key = 'super_admin'
          AND rp.permission_key IN (
              'action:ai_assistant:executeOpsRead',
              'action:ai_assistant:executeCatalogRead',
              'action:ai_assistant:executeLegalRead'
          )
        """
    )
