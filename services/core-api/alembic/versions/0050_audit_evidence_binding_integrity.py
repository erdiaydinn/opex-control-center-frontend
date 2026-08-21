"""Add immutable Audit-to-Field evidence binding integrity.

Revision ID: 0050_audit_evidence_binding_integrity
Revises: 0049_audit_location_accountability
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0050_audit_evidence_binding_integrity"
down_revision: str = "0049_audit_location_accountability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "audit_redaction_receipts",
        sa.Column("field_evidence_receipt_id", UUID, nullable=True),
    )
    op.add_column(
        "audit_redaction_receipts",
        sa.Column("redacted_object_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "audit_redaction_receipts",
        sa.Column("redacted_object_byte_size", sa.BigInteger(), nullable=True),
    )

    op.create_check_constraint(
        "ck_audit_redaction_server_binding_complete",
        "audit_redaction_receipts",
        """
        field_evidence_receipt_id IS NULL OR (
          redacted_evidence_ref = 'field-evidence-receipt:' || field_evidence_receipt_id::text
          AND redacted_object_sha256 ~ '^[0-9a-f]{64}$'
          AND redacted_object_byte_size > 0
        )
        """,
    )
    op.create_check_constraint(
        "ck_audit_redaction_unbound_server_fields_null",
        "audit_redaction_receipts",
        """
        field_evidence_receipt_id IS NOT NULL OR (
          redacted_object_sha256 IS NULL
          AND redacted_object_byte_size IS NULL
        )
        """,
    )
    op.create_index(
        "uq_audit_redaction_field_receipt_binding",
        "audit_redaction_receipts",
        ["tenant_id", "audit_run_id", "field_evidence_receipt_id"],
        unique=True,
        postgresql_where=sa.text("field_evidence_receipt_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_audit_redaction_field_receipt_binding",
        table_name="audit_redaction_receipts",
    )
    op.drop_constraint(
        "ck_audit_redaction_unbound_server_fields_null",
        "audit_redaction_receipts",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_redaction_server_binding_complete",
        "audit_redaction_receipts",
        type_="check",
    )
    op.drop_column("audit_redaction_receipts", "redacted_object_byte_size")
    op.drop_column("audit_redaction_receipts", "redacted_object_sha256")
    op.drop_column("audit_redaction_receipts", "field_evidence_receipt_id")
