"""Fence Audit inference leases to one-way server-time consumption only.

Revision ID: 0059_audit_inference_lease_immutability
Revises: 0058_audit_video_replay_fence
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0059_audit_inference_lease_immutability"
down_revision: str = "0058_audit_video_replay_fence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
LEASE_TABLES = (
    "audit_vision_inference_authorizations",
    "audit_video_inference_authorizations",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_audit_inference_lease_consumption_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'consumed_at') IS DISTINCT FROM
               (to_jsonb(OLD) - 'consumed_at') THEN
                RAISE EXCEPTION 'Audit inference lease authority fields are immutable';
            END IF;

            IF OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL THEN
                RAISE EXCEPTION 'Audit inference lease permits one-way consumption only';
            END IF;

            NEW.consumed_at := CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$
        """
    )

    for table_name in LEASE_TABLES:
        op.execute(
            f"REVOKE UPDATE ON TABLE {table_name} FROM {RUNTIME_ROLE}"
        )
        op.execute(
            f"GRANT UPDATE (consumed_at) ON TABLE {table_name} TO {RUNTIME_ROLE}"
        )
        op.execute(
            f"CREATE TRIGGER {table_name}_consume_only "
            f"BEFORE UPDATE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION "
            "enforce_audit_inference_lease_consumption_only()"
        )


def downgrade() -> None:
    for table_name in LEASE_TABLES:
        op.execute(
            f"DROP TRIGGER IF EXISTS {table_name}_consume_only ON {table_name}"
        )
        op.execute(
            f"REVOKE UPDATE (consumed_at) ON TABLE {table_name} FROM {RUNTIME_ROLE}"
        )
        op.execute(
            f"GRANT UPDATE ON TABLE {table_name} TO {RUNTIME_ROLE}"
        )

    op.execute("DROP FUNCTION IF EXISTS enforce_audit_inference_lease_consumption_only()")
