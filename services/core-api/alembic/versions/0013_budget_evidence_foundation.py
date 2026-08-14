"""Budget financial evidence and durable command schema.

Revision ID: 0013_budget_evidence_foundation
Revises: 0012_budget_import_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0013_budget_evidence_foundation"
down_revision: str | None = "0012_budget_import_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True)),
        sa.Column("chain_seq", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(60), nullable=False),
        sa.Column("aggregate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("prev_hash", sa.String(64)),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_financial_event_tenant_id"),
        sa.UniqueConstraint("tenant_id", "event_hash", name="uq_financial_event_hash"),
    )
    op.create_index(
        "uq_financial_event_chain",
        "financial_event",
        ["tenant_id", sa.text("COALESCE(cost_center_id,'00000000-0000-0000-0000-000000000000'::uuid)"), "chain_seq"],
        unique=True,
    )
    op.create_table(
        "budget_command",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("operation", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PROCESSING"),
        sa.Column("response", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PROCESSING','COMPLETED')", name="ck_budget_command_status"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_command_tenant_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_budget_command_key"),
    )


def downgrade() -> None:
    op.drop_table("budget_command")
    op.drop_table("financial_event")
