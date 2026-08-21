"""Add Field mobile/offline replay receipts and governed evidence policy.

Revision ID: 0021_field_mobile_offline
Revises: 0020_field_ui_operations
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021_field_mobile_offline"
down_revision: str = "0020_field_ui_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
RUNTIME_ROLE = "opex_runtime"


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)'''
    )


def upgrade() -> None:
    op.create_table(
        "field_template_evidence_policies",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("template_id", sa.String(length=120), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column(
            "camera_only_photo", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "managed_device_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "template_id", "template_version"],
            ["field_templates.tenant_id", "field_templates.template_id", "field_templates.version"],
            ondelete="RESTRICT",
            name="fk_field_template_evidence_policy_template",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "template_id",
            "template_version",
            name="pk_field_template_evidence_policies",
        ),
    )
    _tenant_policy("field_template_evidence_policies")
    op.execute(
        "CREATE TRIGGER field_template_evidence_policies_append_only "
        "BEFORE UPDATE OR DELETE ON field_template_evidence_policies "
        "FOR EACH ROW EXECUTE FUNCTION prevent_field_evidence_mutation()"
    )
    op.execute(f"GRANT SELECT, INSERT ON TABLE field_template_evidence_policies TO {RUNTIME_ROLE}")

    op.create_table(
        "field_offline_receipts",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("client_submission_id", UUID, nullable=False),
        sa.Column("device_id", sa.String(length=180), nullable=False),
        sa.Column("device_sequence", sa.BigInteger(), nullable=False),
        sa.Column("target_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", UUID, nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id", "location_id"],
            [
                "field_mission_targets.tenant_id",
                "field_mission_targets.mission_id",
                "field_mission_targets.location_id",
            ],
            ondelete="RESTRICT",
            name="fk_field_offline_receipt_target",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["field_evidence.tenant_id", "field_evidence.id"],
            ondelete="RESTRICT",
            name="fk_field_offline_receipt_evidence",
        ),
        sa.CheckConstraint("device_sequence > 0", name="ck_field_offline_device_sequence_positive"),
        sa.CheckConstraint(
            "target_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_field_offline_target_fingerprint"
        ),
        sa.CheckConstraint(
            "payload_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_field_offline_payload_fingerprint"
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_offline_receipts"),
        sa.UniqueConstraint(
            "tenant_id", "device_id", "device_sequence", name="uq_field_offline_device_sequence"
        ),
        sa.UniqueConstraint(
            "tenant_id", "client_submission_id", name="uq_field_offline_client_submission"
        ),
    )
    op.create_index(
        "ix_field_offline_mission_received",
        "field_offline_receipts",
        ["tenant_id", "mission_id", "received_at"],
    )
    _tenant_policy("field_offline_receipts")
    op.execute(
        "CREATE TRIGGER field_offline_receipts_append_only "
        "BEFORE UPDATE OR DELETE ON field_offline_receipts "
        "FOR EACH ROW EXECUTE FUNCTION prevent_field_evidence_mutation()"
    )
    op.execute(f"GRANT SELECT, INSERT ON TABLE field_offline_receipts TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS field_offline_receipts_append_only ON field_offline_receipts"
    )
    op.drop_table("field_offline_receipts")
    op.execute(
        "DROP TRIGGER IF EXISTS field_template_evidence_policies_append_only "
        "ON field_template_evidence_policies"
    )
    op.drop_table("field_template_evidence_policies")
