"""Budget invoice, commitment, actual, forecast and reconciliation schema.

Revision ID: 0011_budget_ledger_foundation
Revises: 0010_budget_procurement_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0011_budget_ledger_foundation"
down_revision: str | None = "0010_budget_procurement_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "invoice",
        _uuid(), _tenant(),
        sa.Column("purchase_order_id", UUID(as_uuid=True), nullable=False),
        sa.Column("budget_line_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False, server_default="MANUAL"),
        sa.Column("invoice_number", sa.String(160), nullable=False),
        sa.Column("supplier_id", sa.String(120), nullable=False),
        sa.Column("supplier_name", sa.String(240)),
        sa.Column("category", sa.String(160), nullable=False),
        sa.Column("store_code", sa.String(80)),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="POSTED"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("source_system IN ('MANUAL','ARIBA','SAP','BIGQUERY')", name="ck_budget_invoice_source"),
        sa.CheckConstraint("status IN ('POSTED','HOLD','REJECTED')", name="ck_budget_invoice_status"),
        sa.CheckConstraint("base_amount > 0", name="ck_budget_invoice_amount"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "purchase_order_id"], ["purchase_order.tenant_id", "purchase_order.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "budget_line_id"], ["budget_line.tenant_id", "budget_line.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "fiscal_period_id"], ["fiscal_period.tenant_id", "fiscal_period.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_invoice_tenant_id"),
        sa.UniqueConstraint("tenant_id", "supplier_id", "invoice_number", name="uq_budget_invoice_identity"),
    )
    op.create_index("ix_budget_invoice_scope", "invoice", ["tenant_id", "cost_center_id", "status"])

    op.create_table(
        "commitment",
        _uuid(), _tenant(),
        sa.Column("purchase_order_id", UUID(as_uuid=True), nullable=False),
        sa.Column("budget_line_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("remaining_base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("original_base_amount > 0", name="ck_budget_commitment_original"),
        sa.CheckConstraint("remaining_base_amount >= 0", name="ck_budget_commitment_remaining"),
        sa.CheckConstraint("status IN ('OPEN','CLOSED','CANCELED')", name="ck_budget_commitment_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "purchase_order_id"], ["purchase_order.tenant_id", "purchase_order.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "budget_line_id"], ["budget_line.tenant_id", "budget_line.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "fiscal_period_id"], ["fiscal_period.tenant_id", "fiscal_period.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_commitment_tenant_id"),
        sa.UniqueConstraint("tenant_id", "purchase_order_id", name="uq_budget_commitment_po"),
    )

    op.create_table(
        "actual",
        _uuid(), _tenant(),
        sa.Column("invoice_id", UUID(as_uuid=True), nullable=False),
        sa.Column("budget_line_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("base_amount > 0", name="ck_budget_actual_amount"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "invoice_id"], ["invoice.tenant_id", "invoice.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "budget_line_id"], ["budget_line.tenant_id", "budget_line.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "fiscal_period_id"], ["fiscal_period.tenant_id", "fiscal_period.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_actual_tenant_id"),
        sa.UniqueConstraint("tenant_id", "invoice_id", name="uq_budget_actual_invoice"),
    )

    op.create_table(
        "forecast",
        _uuid(), _tenant(),
        sa.Column("budget_line_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("forecast_base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("forecast_base_amount >= 0", name="ck_budget_forecast_amount"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "budget_line_id"], ["budget_line.tenant_id", "budget_line.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "fiscal_period_id"], ["fiscal_period.tenant_id", "fiscal_period.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_forecast_tenant_id"),
    )

    op.create_table(
        "reconciliation_issue",
        _uuid(), _tenant(),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("expected_base_amount", sa.Numeric(18, 2)),
        sa.Column("observed_base_amount", sa.Numeric(18, 2)),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolution_decision", sa.String(30)),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("resolved_by", sa.String(255)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("entity_type IN ('PURCHASE_ORDER','INVOICE')", name="ck_budget_reconciliation_entity"),
        sa.CheckConstraint("status IN ('OPEN','RESOLVED')", name="ck_budget_reconciliation_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_reconciliation_tenant_id"),
    )
    op.create_index("ix_budget_reconciliation_open", "reconciliation_issue", ["tenant_id", "cost_center_id", "status"])


def downgrade() -> None:
    for table in ("reconciliation_issue", "forecast", "actual", "commitment", "invoice"):
        op.drop_table(table)
