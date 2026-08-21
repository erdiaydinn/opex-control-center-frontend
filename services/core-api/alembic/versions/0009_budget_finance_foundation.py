"""Budget planning schema.

Revision ID: 0009_budget_finance_foundation
Revises: 0008_preauth_provider_resolver
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0009_budget_finance_foundation"
down_revision: str | None = "0008_preauth_provider_resolver"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic creates alembic_version as VARCHAR(32) by default. Budget revision
    # identifiers exceed that capacity, so widen the existing version table from
    # inside the first Budget migration before Alembic writes this revision ID.
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(128)"
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "budget_plan",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="TRY"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("activated_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE')", name="ck_budget_plan_status"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_plan_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", "fiscal_year", name="uq_budget_plan_name_year"),
    )
    op.create_table(
        "fiscal_period",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("closed_by", sa.String(255)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_fiscal_period_range"),
        sa.CheckConstraint("status IN ('OPEN','CLOSED')", name="ck_fiscal_period_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "plan_id"], ["budget_plan.tenant_id", "budget_plan.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fiscal_period_tenant_id"),
        sa.UniqueConstraint("tenant_id", "plan_id", "code", name="uq_fiscal_period_code"),
    )
    op.create_table(
        "cost_center",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("store_code", sa.String(80)),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cost_center_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_cost_center_code"),
    )
    op.create_table(
        "budget_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cost_center_id", UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(160), nullable=False),
        sa.Column("supplier_id", sa.String(120)),
        sa.Column("supplier_name", sa.String(240)),
        sa.Column("store_code", sa.String(80)),
        sa.Column("budget_base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("budget_base_amount >= 0", name="ck_budget_line_amount"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "plan_id"], ["budget_plan.tenant_id", "budget_plan.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "fiscal_period_id"], ["fiscal_period.tenant_id", "fiscal_period.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "cost_center_id"], ["cost_center.tenant_id", "cost_center.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_budget_line_tenant_id"),
        sa.UniqueConstraint("tenant_id", "id", "fiscal_period_id", "cost_center_id", name="uq_budget_line_scope_key"),
    )
    op.create_index("ix_budget_line_scope", "budget_line", ["tenant_id", "cost_center_id", "fiscal_period_id"])


def downgrade() -> None:
    op.drop_table("budget_line")
    op.drop_table("cost_center")
    op.drop_table("fiscal_period")
    op.drop_table("budget_plan")
