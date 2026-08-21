"""Budget purchase-request, approval and purchase-order schema.

Revision ID: 0010_budget_procurement_foundation
Revises: 0009_budget_finance_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0010_budget_procurement_foundation"
down_revision: str | None = "0009_budget_finance_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "purchase_request",
        _uuid(), _tenant(),
        sa.Column("budget_line_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False, server_default="MANUAL"),
        sa.Column("external_ref", sa.String(160)),
        sa.Column("supplier_id", sa.String(120)),
        sa.Column("supplier_name", sa.String(240)),
        sa.Column("category", sa.String(160), nullable=False),
        sa.Column("store_code", sa.String(80)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requested_base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="SUBMITTED"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("source_system IN ('MANUAL','ARIBA','SAP','BIGQUERY')", name="ck_budget_pr_source"),
        sa.CheckConstraint("status IN ('SUBMITTED','APPROVED','REJECTED','CANCELED')", name="ck_budget_pr_status"),
        sa.CheckConstraint("requested_base_amount > 0", name="ck_budget_pr_amount"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "budget_line_id", "fiscal_period_id", "cost_center_id"],
            ["budget_line.tenant_id", "budget_line.id", "budget_line.fiscal_period_id", "budget_line.cost_center_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_pr_tenant_id"),
    )
    op.create_index(
        "uq_budget_pr_external",
        "purchase_request",
        ["tenant_id", "source_system", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    op.create_index("ix_budget_pr_scope", "purchase_request", ["tenant_id", "cost_center_id", "status"])

    op.create_table(
        "approval",
        _uuid(), _tenant(),
        sa.Column("purchase_request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("step > 0", name="ck_budget_approval_step"),
        sa.CheckConstraint("decision IN ('APPROVE','REJECT')", name="ck_budget_approval_decision"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "purchase_request_id"], ["purchase_request.tenant_id", "purchase_request.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "fiscal_period_id"], ["fiscal_period.tenant_id", "fiscal_period.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_approval_tenant_id"),
        sa.UniqueConstraint("tenant_id", "purchase_request_id", "step", name="uq_budget_approval_step"),
    )

    op.create_table(
        "purchase_order",
        _uuid(), _tenant(),
        sa.Column("purchase_request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("budget_line_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False, server_default="MANUAL"),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("supplier_id", sa.String(120), nullable=False),
        sa.Column("supplier_name", sa.String(240)),
        sa.Column("category", sa.String(160), nullable=False),
        sa.Column("store_code", sa.String(80)),
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("source_system IN ('MANUAL','ARIBA','SAP','BIGQUERY')", name="ck_budget_po_source"),
        sa.CheckConstraint("status IN ('OPEN','RECONCILIATION_HOLD','CANCELED')", name="ck_budget_po_status"),
        sa.CheckConstraint("base_amount > 0", name="ck_budget_po_amount"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "purchase_request_id"], ["purchase_request.tenant_id", "purchase_request.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "budget_line_id"], ["budget_line.tenant_id", "budget_line.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "fiscal_period_id"], ["fiscal_period.tenant_id", "fiscal_period.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_po_tenant_id"),
        sa.UniqueConstraint("tenant_id", "source_system", "external_id", name="uq_budget_po_external"),
    )
    op.create_index("ix_budget_po_scope", "purchase_order", ["tenant_id", "cost_center_id", "status"])


def downgrade() -> None:
    for table in ("purchase_order", "approval", "purchase_request"):
        op.drop_table(table)
