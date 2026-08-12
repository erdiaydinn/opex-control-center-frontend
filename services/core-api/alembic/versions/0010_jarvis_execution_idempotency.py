"""Add durable tenant-scoped Jarvis execution idempotency.

Revision ID: 0010_jarvis_idempotency
Revises: 0009_ai_tool_permissions
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_jarvis_idempotency"
down_revision: str | None = "0009_ai_tool_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
UUID = postgresql.UUID(as_uuid=True)
TABLE = "jarvis_execution_idempotency"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_subject_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "request_fingerprint",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "actor_subject_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_jarvis_idempotency_actor_sha256",
        ),
        sa.CheckConstraint(
            "idempotency_key_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_jarvis_idempotency_key_sha256",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_jarvis_idempotency_request_sha256",
        ),
        sa.CheckConstraint(
            "state IN ('reserved', 'dispatched', 'completed', "
            "'indeterminate', 'denied')",
            name="ck_jarvis_idempotency_state",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_subject_sha256",
            "idempotency_key_sha256",
            name="uq_jarvis_idempotency_actor_key",
        ),
    )
    op.create_index(
        "ix_jarvis_idempotency_tenant_expires",
        TABLE,
        ["tenant_id", "expires_at"],
    )

    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''
        CREATE POLICY "{TABLE}_tenant_isolation"
        ON "{TABLE}"
        USING (
            tenant_id = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )::uuid
        )
        '''
    )

    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {TABLE} "
        f"TO {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        f"REVOKE ALL PRIVILEGES ON TABLE {TABLE} FROM {RUNTIME_ROLE}"
    )
    op.drop_table(TABLE)
