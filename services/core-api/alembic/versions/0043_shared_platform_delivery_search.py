"""Master 42 notification preference and escalation authority.

Revision ID: 0043_shared_platform_delivery_search
Revises: 0042_shared_platform_authorities
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043_shared_platform_delivery_search"
down_revision: str | None = "0042_shared_platform_authorities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME = "opex_runtime"
_TABLES = (
    "platform_notification_preference",
    "platform_notification_escalation_policy",
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
        """CREATE TABLE platform_notification_preference (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          subject varchar(255) NOT NULL,
          module varchar(80) NOT NULL,
          event_key varchar(160) NOT NULL,
          channel varchar(30) NOT NULL,
          enabled boolean NOT NULL DEFAULT true,
          digest_mode varchar(20) NOT NULL DEFAULT 'IMMEDIATE',
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (channel IN ('IN_APP', 'EMAIL', 'PUSH', 'WEBHOOK')),
          CHECK (digest_mode IN ('IMMEDIATE', 'DAILY', 'WEEKLY')),
          UNIQUE (tenant_id, subject, module, event_key, channel),
          UNIQUE (tenant_id, id)
        )"""
    )
    op.execute(
        """CREATE TABLE platform_notification_escalation_policy (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          module varchar(80) NOT NULL,
          event_key varchar(160) NOT NULL,
          after_minutes integer NOT NULL,
          escalate_channel varchar(30) NOT NULL,
          max_attempts integer NOT NULL DEFAULT 5,
          enabled boolean NOT NULL DEFAULT true,
          CHECK (after_minutes > 0),
          CHECK (max_attempts BETWEEN 1 AND 20),
          CHECK (escalate_channel IN ('IN_APP', 'EMAIL', 'PUSH', 'WEBHOOK')),
          UNIQUE (tenant_id, module, event_key),
          UNIQUE (tenant_id, id)
        )"""
    )
    for table in _TABLES:
        _tenant_rls(table)

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {', '.join(_TABLES)} TO {RUNTIME}")
    op.execute(f"REVOKE DELETE ON {', '.join(_TABLES)} FROM {RUNTIME}")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
