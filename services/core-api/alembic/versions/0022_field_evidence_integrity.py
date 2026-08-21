"""Add Field evidence object, device and camera attestation authority.

Revision ID: 0022_field_evidence_integrity
Revises: 0021_field_mobile_offline
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_field_evidence_integrity"
down_revision: str = "0021_field_mobile_offline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
RUNTIME_ROLE = "opex_runtime"


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def _append_only(table_name: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table_name}_append_only "
        f"BEFORE UPDATE OR DELETE ON {table_name} "
        "FOR EACH ROW EXECUTE FUNCTION prevent_field_evidence_mutation()"
    )


def upgrade() -> None:
    op.create_table(
        "field_evidence_object_receipts",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("receipt_id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("receipt_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=80), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "receipt_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_field_object_receipt_fingerprint"
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_field_object_sha256"),
        sa.CheckConstraint(
            "byte_size > 0 AND byte_size <= 26214400", name="ck_field_object_byte_size"
        ),
        sa.CheckConstraint(
            "media_type IN ('image/jpeg','image/png','image/heic','image/webp')",
            name="ck_field_object_media_type",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "receipt_id", name="pk_field_evidence_object_receipts"
        ),
        sa.UniqueConstraint(
            "tenant_id", "receipt_fingerprint", name="uq_field_object_receipt_fingerprint"
        ),
    )
    _tenant_policy("field_evidence_object_receipts")
    _append_only("field_evidence_object_receipts")
    op.execute(f"GRANT SELECT ON TABLE field_evidence_object_receipts TO {RUNTIME_ROLE}")

    op.create_table(
        "field_device_attestations",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("device_id", sa.String(length=180), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("attestation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "verdict IN ('trusted','rejected')", name="ck_field_device_attestation_verdict"
        ),
        sa.CheckConstraint(
            "attestation_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_device_attestation_fingerprint",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "device_id",
            "attestation_fingerprint",
            name="pk_field_device_attestations",
        ),
    )
    op.create_index(
        "ix_field_device_attestation_latest",
        "field_device_attestations",
        ["tenant_id", "device_id", "observed_at"],
    )
    _tenant_policy("field_device_attestations")
    _append_only("field_device_attestations")
    op.execute(f"GRANT SELECT ON TABLE field_device_attestations TO {RUNTIME_ROLE}")

    op.create_table(
        "field_capture_attestations",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("receipt_id", UUID, nullable=False),
        sa.Column("capture_session_id", UUID, nullable=False),
        sa.Column("device_id", sa.String(length=180), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("attestation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "receipt_id"],
            [
                "field_evidence_object_receipts.tenant_id",
                "field_evidence_object_receipts.receipt_id",
            ],
            ondelete="RESTRICT",
            name="fk_field_capture_attestation_receipt",
        ),
        sa.CheckConstraint(
            "verdict IN ('trusted','rejected')", name="ck_field_capture_attestation_verdict"
        ),
        sa.CheckConstraint(
            "attestation_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_capture_attestation_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_capture_attestations"),
        sa.UniqueConstraint(
            "tenant_id",
            "receipt_id",
            "capture_session_id",
            "device_id",
            "attestation_fingerprint",
            name="uq_field_capture_attestation_identity",
        ),
    )
    op.create_index(
        "ix_field_capture_attestation_receipt",
        "field_capture_attestations",
        ["tenant_id", "receipt_id", "capture_session_id", "device_id"],
    )
    _tenant_policy("field_capture_attestations")
    _append_only("field_capture_attestations")
    op.execute(f"GRANT SELECT ON TABLE field_capture_attestations TO {RUNTIME_ROLE}")

    op.add_column(
        "field_offline_receipts",
        sa.Column("authority_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_field_offline_authority_fingerprint",
        "field_offline_receipts",
        "authority_fingerprint IS NULL OR authority_fingerprint ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_field_offline_authority_fingerprint",
        "field_offline_receipts",
        type_="check",
    )
    op.drop_column("field_offline_receipts", "authority_fingerprint")

    op.execute(
        "DROP TRIGGER IF EXISTS field_capture_attestations_append_only ON"
        " field_capture_attestations"
    )
    op.drop_table("field_capture_attestations")
    op.execute(
        "DROP TRIGGER IF EXISTS field_device_attestations_append_only ON field_device_attestations"
    )
    op.drop_table("field_device_attestations")
    op.execute(
        "DROP TRIGGER IF EXISTS field_evidence_object_receipts_append_only ON"
        " field_evidence_object_receipts"
    )
    op.drop_table("field_evidence_object_receipts")
