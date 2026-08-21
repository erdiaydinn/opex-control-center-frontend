"""Bind private Field evidence object receipts to exact submissions.

Revision ID: 0024_field_evidence_object_upload
Revises: 0023_field_governed_promotion
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024_field_evidence_object_upload"
down_revision: str = "0023_field_governed_promotion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.add_column(
        "field_evidence_object_receipts",
        sa.Column("client_submission_id", UUID, nullable=True),
    )
    op.add_column(
        "field_evidence_object_receipts",
        sa.Column("mission_id", UUID, nullable=True),
    )
    op.add_column(
        "field_evidence_object_receipts",
        sa.Column("location_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "field_evidence_object_receipts",
        sa.Column("field_key", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "field_evidence_object_receipts",
        sa.Column("actor_subject", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "field_evidence_object_receipts",
        sa.Column("storage_receipt_hash", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_field_object_upload_binding_complete",
        "field_evidence_object_receipts",
        "(client_submission_id IS NULL AND mission_id IS NULL AND location_id IS NULL "
        "AND field_key IS NULL AND actor_subject IS NULL AND storage_receipt_hash IS NULL) OR "
        "(client_submission_id IS NOT NULL AND mission_id IS NOT NULL AND location_id IS NOT NULL "
        "AND field_key IS NOT NULL AND actor_subject IS NOT NULL "
        "AND storage_receipt_hash ~ '^[0-9a-f]{64}$')",
    )
    op.create_unique_constraint(
        "uq_field_object_submission_field",
        "field_evidence_object_receipts",
        ["tenant_id", "client_submission_id", "field_key"],
    )
    op.create_index(
        "ix_field_object_submission_binding",
        "field_evidence_object_receipts",
        ["tenant_id", "client_submission_id", "mission_id", "location_id"],
    )
    op.execute(f"GRANT INSERT ON TABLE field_evidence_object_receipts TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE INSERT ON TABLE field_evidence_object_receipts FROM {RUNTIME_ROLE}")
    op.drop_index("ix_field_object_submission_binding", table_name="field_evidence_object_receipts")
    op.drop_constraint(
        "uq_field_object_submission_field",
        "field_evidence_object_receipts",
        type_="unique",
    )
    op.drop_constraint(
        "ck_field_object_upload_binding_complete",
        "field_evidence_object_receipts",
        type_="check",
    )
    for column in (
        "storage_receipt_hash",
        "actor_subject",
        "field_key",
        "location_id",
        "mission_id",
        "client_submission_id",
    ):
        op.drop_column("field_evidence_object_receipts", column)
