"""Allow non-idempotent learning events while deduplicating keyed events.

Revision ID: 0016_academy_audit_idempotency
Revises: 0015_academy_foundation
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_academy_audit_idempotency"
down_revision: str | None = "0015_academy_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE academy_learning_events "
        "DROP CONSTRAINT IF EXISTS uq_academy_learning_event_idempotency"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_academy_learning_event_idempotency
        ON academy_learning_events (tenant_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute("GRANT UPDATE ON TABLE academy_entitlements, academy_quizzes TO opex_runtime")
    op.execute("GRANT DELETE ON TABLE academy_document_chunks TO opex_runtime")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON TABLE academy_document_chunks FROM opex_runtime")
    op.execute("REVOKE UPDATE ON TABLE academy_entitlements, academy_quizzes FROM opex_runtime")
    op.execute("DROP INDEX IF EXISTS uq_academy_learning_event_idempotency")
    op.execute(
        """
        ALTER TABLE academy_learning_events
        ADD CONSTRAINT uq_academy_learning_event_idempotency
        UNIQUE NULLS NOT DISTINCT (tenant_id, idempotency_key)
        """
    )
