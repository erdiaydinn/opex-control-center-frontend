"""Add persisted Audit video privacy and inference authority.

Revision ID: 0057_audit_video_authority
Revises: 0056_audit_visit_manifests
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0057_audit_video_authority"
down_revision: str = "0056_audit_visit_manifests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RUNTIME_ROLE = "opex_runtime"
VIDEO_AUTHORITY_VERSION = "server_video_privacy_v1"


def _tenant_policy(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_isolation
        ON {table_name}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )


def upgrade() -> None:
    op.drop_constraint(
        "ck_audit_redaction_frame_count",
        "audit_redaction_receipts",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_redaction_complete_coverage",
        "audit_redaction_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_audit_redaction_media_coverage",
        "audit_redaction_receipts",
        "(media_kind = 'image' AND frame_count = 1 AND processed_frame_count = 1) OR "
        "(media_kind = 'video' AND frame_count = 0 AND processed_frame_count = 0)",
    )

    op.create_table(
        "audit_video_verification_events",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("redaction_receipt_id", UUID, nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("verifier_ref", sa.String(length=300), nullable=False),
        sa.Column("verification_authority_version", sa.String(length=64), nullable=False),
        sa.Column("verification_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("observed_sha256", sa.String(length=64), nullable=False),
        sa.Column("observed_byte_size", sa.BigInteger(), nullable=False),
        sa.Column("decoder_ref", sa.String(length=300), nullable=True),
        sa.Column("decoder_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("canonical_frame_count", sa.BigInteger(), nullable=False),
        sa.Column("processed_frame_count", sa.BigInteger(), nullable=False),
        sa.Column("manifest_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("frame_manifest", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
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
            name="fk_audit_video_verification_redaction",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_audit_video_verification_events",
        ),
        sa.CheckConstraint(
            "verification_status IN ('verified','rejected','blocked','tampered')",
            name="ck_audit_video_verification_status",
        ),
        sa.CheckConstraint(
            f"verification_authority_version = '{VIDEO_AUTHORITY_VERSION}'",
            name="ck_audit_video_authority_version",
        ),
        sa.CheckConstraint(
            "verification_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_verification_fingerprint",
        ),
        sa.CheckConstraint(
            "observed_sha256 ~ '^[0-9a-f]{64}$' AND observed_byte_size > 0",
            name="ck_audit_video_observation_integrity",
        ),
        sa.CheckConstraint(
            "(decoder_ref IS NULL AND decoder_fingerprint IS NULL) OR "
            "(length(trim(decoder_ref)) > 0 AND decoder_fingerprint ~ '^[0-9a-f]{64}$')",
            name="ck_audit_video_decoder_integrity",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms > 0",
            name="ck_audit_video_duration",
        ),
        sa.CheckConstraint(
            "canonical_frame_count >= 0 AND processed_frame_count >= 0 "
            "AND processed_frame_count <= canonical_frame_count",
            name="ck_audit_video_frame_counts",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(frame_manifest) = 'array'",
            name="ck_audit_video_frame_manifest_shape",
        ),
        sa.CheckConstraint(
            "verification_status = 'verified' OR length(trim(COALESCE(reason,''))) > 0",
            name="ck_audit_video_nonverified_reason",
        ),
        sa.CheckConstraint(
            "verification_status <> 'verified' OR "
            "(decoder_ref IS NOT NULL AND decoder_fingerprint IS NOT NULL "
            "AND duration_ms IS NOT NULL AND canonical_frame_count > 0 "
            "AND processed_frame_count = canonical_frame_count "
            "AND jsonb_array_length(frame_manifest) = canonical_frame_count "
            "AND manifest_fingerprint ~ '^[0-9a-f]{64}$')",
            name="ck_audit_video_verified_complete",
        ),
        sa.CheckConstraint(
            "verification_status = 'verified' OR manifest_fingerprint IS NULL",
            name="ck_audit_video_unverified_no_manifest_authority",
        ),
    )
    op.create_index(
        "ix_audit_video_verification_receipt",
        "audit_video_verification_events",
        ["tenant_id", "redaction_receipt_id", "verified_at"],
    )
    _tenant_policy("audit_video_verification_events")
    op.execute(
        "CREATE TRIGGER audit_video_verification_events_append_only "
        "BEFORE UPDATE OR DELETE ON audit_video_verification_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_audit_append_only_mutation()"
    )
    op.execute(
        f"GRANT SELECT, INSERT ON TABLE audit_video_verification_events TO {RUNTIME_ROLE}"
    )

    op.create_table(
        "audit_video_inference_authorizations",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_run_id", UUID, nullable=False),
        sa.Column("item_key", sa.String(length=180), nullable=False),
        sa.Column("redaction_receipt_id", UUID, nullable=False),
        sa.Column("video_verification_event_id", UUID, nullable=False),
        sa.Column("program_key", sa.String(length=120), nullable=False),
        sa.Column("program_version", sa.Integer(), nullable=False),
        sa.Column("question_control_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("model_record_id", sa.String(length=180), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_provenance_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("production_promotion_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("production_release_proof_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("video_manifest_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("decoder_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("field_activation_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("capabilities", JSONB, nullable=False),
        sa.Column("authorization_fingerprint", sa.String(length=64), nullable=False),
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
            name="fk_audit_video_auth_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "redaction_receipt_id"],
            ["audit_redaction_receipts.tenant_id", "audit_redaction_receipts.id"],
            ondelete="CASCADE",
            name="fk_audit_video_auth_redaction",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "video_verification_event_id"],
            ["audit_video_verification_events.tenant_id", "audit_video_verification_events.id"],
            ondelete="RESTRICT",
            name="fk_audit_video_auth_verification",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "program_key", "program_version"],
            [
                "audit_program_versions.tenant_id",
                "audit_program_versions.program_key",
                "audit_program_versions.version",
            ],
            ondelete="RESTRICT",
            name="fk_audit_video_auth_program",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_video_inference_auth"),
        sa.UniqueConstraint(
            "tenant_id",
            "authorization_fingerprint",
            name="uq_audit_video_authorization_fingerprint",
        ),
        sa.CheckConstraint("program_version > 0", name="ck_audit_video_auth_program_version"),
        sa.CheckConstraint(
            "question_control_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_control_fingerprint",
        ),
        sa.CheckConstraint(
            "artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_artifact_sha",
        ),
        sa.CheckConstraint(
            "artifact_provenance_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_artifact_provenance",
        ),
        sa.CheckConstraint(
            "production_promotion_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_promotion_fingerprint",
        ),
        sa.CheckConstraint(
            "production_release_proof_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_release_proof",
        ),
        sa.CheckConstraint(
            "video_manifest_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_manifest_fingerprint",
        ),
        sa.CheckConstraint(
            "decoder_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_decoder_fingerprint",
        ),
        sa.CheckConstraint(
            (
                "field_activation_fingerprint IS NULL OR "
                "field_activation_fingerprint ~ '^[0-9a-f]{64}$'"
            ),
            name="ck_audit_video_auth_field_activation",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(capabilities) = 'array' AND jsonb_array_length(capabilities) > 0",
            name="ck_audit_video_auth_capabilities",
        ),
        sa.CheckConstraint(
            "authorization_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_video_auth_fingerprint",
        ),
        sa.CheckConstraint("expires_at > issued_at", name="ck_audit_video_auth_expiry"),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= issued_at",
            name="ck_audit_video_auth_consumed_at",
        ),
    )
    op.create_index(
        "ix_audit_video_auth_run_item",
        "audit_video_inference_authorizations",
        ["tenant_id", "audit_run_id", "item_key", "issued_at"],
    )
    op.create_index(
        "ix_audit_video_auth_verification",
        "audit_video_inference_authorizations",
        ["tenant_id", "video_verification_event_id"],
    )
    _tenant_policy("audit_video_inference_authorizations")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE audit_video_inference_authorizations "
        f"TO {RUNTIME_ROLE}"
    )
    op.execute(
        "REVOKE DELETE ON TABLE audit_video_inference_authorizations "
        f"FROM {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.drop_table("audit_video_inference_authorizations")
    op.execute(
        "DROP TRIGGER IF EXISTS audit_video_verification_events_append_only "
        "ON audit_video_verification_events"
    )
    op.drop_table("audit_video_verification_events")

    op.drop_constraint(
        "ck_audit_redaction_media_coverage",
        "audit_redaction_receipts",
        type_="check",
    )
    op.execute(
        "ALTER TABLE audit_redaction_receipts ADD CONSTRAINT "
        "ck_audit_redaction_frame_count CHECK (frame_count > 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE audit_redaction_receipts ADD CONSTRAINT "
        "ck_audit_redaction_complete_coverage "
        "CHECK (processed_frame_count = frame_count) NOT VALID"
    )
