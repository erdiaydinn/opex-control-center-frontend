"""Add single-use Audit vision inference authorization receipts.

Revision ID: 0052_audit_vision_inference_authority
Revises: 0051_audit_server_privacy_authority
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0052_audit_vision_inference_authority"
down_revision: str = "0051_audit_server_privacy_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.create_table(
        "audit_vision_inference_authorizations",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column(
            "id",
            UUID,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("audit_run_id", UUID, nullable=False),
        sa.Column("item_key", sa.String(length=180), nullable=False),
        sa.Column("redaction_receipt_id", UUID, nullable=False),
        sa.Column("privacy_verification_event_id", UUID, nullable=False),
        sa.Column("program_key", sa.String(length=120), nullable=False),
        sa.Column("program_version", sa.Integer(), nullable=False),
        sa.Column(
            "question_control_fingerprint",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("model_record_id", sa.String(length=180), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "artifact_provenance_fingerprint",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "production_promotion_fingerprint",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "production_release_proof_fingerprint",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("capabilities", JSONB, nullable=False),
        sa.Column(
            "authorization_fingerprint",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "audit_run_id"],
            ["audit_runs.tenant_id", "audit_runs.id"],
            ondelete="CASCADE",
            name="fk_audit_vision_auth_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "redaction_receipt_id"],
            [
                "audit_redaction_receipts.tenant_id",
                "audit_redaction_receipts.id",
            ],
            ondelete="CASCADE",
            name="fk_audit_vision_auth_redaction",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "privacy_verification_event_id"],
            [
                "audit_redaction_verification_events.tenant_id",
                "audit_redaction_verification_events.id",
            ],
            ondelete="RESTRICT",
            name="fk_audit_vision_auth_privacy_event",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "program_key", "program_version"],
            [
                "audit_program_versions.tenant_id",
                "audit_program_versions.program_key",
                "audit_program_versions.version",
            ],
            ondelete="RESTRICT",
            name="fk_audit_vision_auth_program",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_audit_vision_inference_auth",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "authorization_fingerprint",
            name="uq_audit_vision_authorization_fingerprint",
        ),
        sa.CheckConstraint(
            "program_version > 0",
            name="ck_audit_vision_auth_program_version",
        ),
        sa.CheckConstraint(
            "question_control_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_vision_auth_control_fingerprint",
        ),
        sa.CheckConstraint(
            "artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_audit_vision_auth_artifact_sha",
        ),
        sa.CheckConstraint(
            "artifact_provenance_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_vision_auth_artifact_provenance",
        ),
        sa.CheckConstraint(
            "production_promotion_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_vision_auth_promotion_fingerprint",
        ),
        sa.CheckConstraint(
            "production_release_proof_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_vision_auth_release_proof",
        ),
        sa.CheckConstraint(
            "authorization_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_vision_auth_fingerprint",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(capabilities) = 'array' "
            "AND jsonb_array_length(capabilities) > 0",
            name="ck_audit_vision_auth_capabilities",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_audit_vision_auth_expiry",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= issued_at",
            name="ck_audit_vision_auth_consumed_at",
        ),
    )
    op.create_index(
        "ix_audit_vision_auth_run_item",
        "audit_vision_inference_authorizations",
        ["tenant_id", "audit_run_id", "item_key", "issued_at"],
    )
    op.create_index(
        "ix_audit_vision_auth_privacy_event",
        "audit_vision_inference_authorizations",
        ["tenant_id", "privacy_verification_event_id"],
    )

    op.execute(
        "ALTER TABLE audit_vision_inference_authorizations "
        "ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE audit_vision_inference_authorizations "
        "FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        """CREATE POLICY audit_vision_inference_authorizations_tenant_isolation
        ON audit_vision_inference_authorizations
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE "
        "audit_vision_inference_authorizations TO " + RUNTIME_ROLE
    )
    op.execute(
        "REVOKE DELETE ON TABLE audit_vision_inference_authorizations FROM "
        + RUNTIME_ROLE
    )


def downgrade() -> None:
    op.drop_table("audit_vision_inference_authorizations")
