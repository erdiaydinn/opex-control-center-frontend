"""Separate client redaction receipt from server privacy verification.

Revision ID: 0047_audit_privacy_verification
Revises: 0046_audit_operating_system
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0047_audit_privacy_verification"
down_revision: str = "0046_audit_operating_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.create_table(
        "audit_redaction_verification_events",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("redaction_receipt_id", UUID, nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("verifier_ref", sa.String(length=300), nullable=False),
        sa.Column("verification_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "redaction_receipt_id"],
            ["audit_redaction_receipts.tenant_id", "audit_redaction_receipts.id"],
            ondelete="RESTRICT",
            name="fk_audit_privacy_verification_receipt",
        ),
        sa.CheckConstraint(
            "verification_status IN ('verified','rejected')",
            name="ck_audit_privacy_verification_status",
        ),
        sa.CheckConstraint(
            "verification_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_privacy_verification_fingerprint",
        ),
        sa.CheckConstraint(
            "verification_status <> 'rejected' OR length(trim(COALESCE(reason,''))) > 0",
            name="ck_audit_privacy_rejection_reason",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_redaction_verification_events"),
    )
    op.create_index(
        "ix_audit_privacy_verification_receipt",
        "audit_redaction_verification_events",
        ["tenant_id", "redaction_receipt_id", "verified_at"],
    )

    op.execute("ALTER TABLE audit_redaction_verification_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_redaction_verification_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY audit_redaction_verification_events_tenant_isolation
        ON audit_redaction_verification_events
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )
    op.execute(
        "CREATE TRIGGER audit_redaction_verification_events_append_only "
        "BEFORE UPDATE OR DELETE ON audit_redaction_verification_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_audit_append_only_mutation()"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE audit_redaction_verification_events TO " + RUNTIME_ROLE
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS audit_redaction_verification_events_append_only "
        "ON audit_redaction_verification_events"
    )
    op.drop_table("audit_redaction_verification_events")
