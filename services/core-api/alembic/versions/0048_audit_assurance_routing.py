"""Add current-state assurance cases and governed disagreement routing.

Revision ID: 0048_audit_assurance_routing
Revises: 0047_audit_privacy_verification
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0048_audit_assurance_routing"
down_revision: str = "0047_audit_privacy_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.create_table(
        "audit_assurance_cases",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_run_id", UUID, nullable=False),
        sa.Column("item_key", sa.String(length=180), nullable=False),
        sa.Column("ai_decision_event_id", UUID, nullable=False),
        sa.Column("auditor_decision_event_id", UUID, nullable=False),
        sa.Column("auditor_subject", sa.String(length=255), nullable=False),
        sa.Column("manager_subject", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("manager_disposition", sa.String(length=40), nullable=True),
        sa.Column("standards_disposition", sa.String(length=40), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "opened_at",
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "audit_run_id"],
            ["audit_runs.tenant_id", "audit_runs.id"],
            ondelete="RESTRICT",
            name="fk_audit_assurance_case_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ai_decision_event_id"],
            ["audit_item_decision_events.tenant_id", "audit_item_decision_events.id"],
            ondelete="RESTRICT",
            name="fk_audit_assurance_case_ai_decision",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "auditor_decision_event_id"],
            ["audit_item_decision_events.tenant_id", "audit_item_decision_events.id"],
            ondelete="RESTRICT",
            name="fk_audit_assurance_case_auditor_decision",
        ),
        sa.CheckConstraint("version > 0", name="ck_audit_assurance_case_version"),
        sa.CheckConstraint(
            "state IN ('MANAGER_REVIEW','MANAGER_UNASSIGNED',"
            "'OPERATIONS_STANDARDS_REVIEW','OPERATIONS_STANDARDS_UNASSIGNED','RESOLVED')",
            name="ck_audit_assurance_case_state",
        ),
        sa.CheckConstraint(
            "manager_disposition IS NULL OR manager_disposition IN"
            " ('AI_CONFIRMED','AUDITOR_CONFIRMED')",
            name="ck_audit_assurance_case_manager_disposition",
        ),
        sa.CheckConstraint(
            "standards_disposition IS NULL OR standards_disposition IN"
            " ('AI_CONFIRMED','AUDITOR_CONFIRMED','STANDARD_CHANGED',"
            "'MODEL_REVIEW_REQUIRED','NO_CHANGE')",
            name="ck_audit_assurance_case_standards_disposition",
        ),
        sa.CheckConstraint(
            "state <> 'RESOLVED' OR resolved_at IS NOT NULL",
            name="ck_audit_assurance_case_resolved_at",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_assurance_cases"),
        sa.UniqueConstraint(
            "tenant_id",
            "audit_run_id",
            "item_key",
            name="uq_audit_assurance_case_run_item",
        ),
    )
    op.create_index(
        "ix_audit_assurance_cases_state",
        "audit_assurance_cases",
        ["tenant_id", "state", "manager_subject", "updated_at"],
    )
    op.create_index(
        "ix_audit_assurance_cases_auditor",
        "audit_assurance_cases",
        ["tenant_id", "auditor_subject", "updated_at"],
    )

    op.execute("ALTER TABLE audit_assurance_cases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_assurance_cases FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY audit_assurance_cases_tenant_isolation
        ON audit_assurance_cases
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE audit_assurance_cases TO " + RUNTIME_ROLE
    )
    op.execute("REVOKE DELETE ON TABLE audit_assurance_cases FROM " + RUNTIME_ROLE)


def downgrade() -> None:
    op.drop_table("audit_assurance_cases")
