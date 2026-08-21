"""Budget import staging schema.

Revision ID: 0012_budget_import_foundation
Revises: 0011_budget_ledger_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0012_budget_import_foundation"
down_revision: str | None = "0011_budget_ledger_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_batch",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="STAGED"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("source_system IN ('ARIBA','SAP','BIGQUERY','MANUAL')", name="ck_budget_import_source"),
        sa.CheckConstraint("status IN ('STAGED','MATERIALIZED','REJECTED')", name="ck_budget_import_status"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_import_batch_tenant_id"),
        sa.UniqueConstraint("tenant_id", "source_system", "entity_type", "content_hash", name="uq_budget_import_batch_hash"),
    )
    op.create_table(
        "import_row",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="READY"),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint("status IN ('READY','MATERIALIZED','REJECTED')", name="ck_budget_import_row_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "batch_id"], ["import_batch.tenant_id", "import_batch.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_import_row_tenant_id"),
        sa.UniqueConstraint("tenant_id", "source_system", "entity_type", "row_hash", name="uq_budget_import_row_hash"),
    )


def downgrade() -> None:
    op.drop_table("import_row")
    op.drop_table("import_batch")
