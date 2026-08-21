"""Strengthen Audit server privacy verification event authority.

Revision ID: 0051_audit_server_privacy_authority
Revises: 0050_audit_evidence_binding_integrity
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051_audit_server_privacy_authority"
down_revision: str = "0050_audit_evidence_binding_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SERVER_AUTHORITY_VERSION = "server_privacy_v2"


def upgrade() -> None:
    op.drop_constraint(
        "ck_audit_privacy_verification_status",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_rejection_reason",
        "audit_redaction_verification_events",
        type_="check",
    )

    op.add_column(
        "audit_redaction_verification_events",
        sa.Column(
            "verification_authority_version",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_redaction_verification_events",
        sa.Column("observed_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "audit_redaction_verification_events",
        sa.Column("observed_byte_size", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "audit_redaction_verification_events",
        sa.Column("scanner_model_ref", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "audit_redaction_verification_events",
        sa.Column(
            "scanner_model_fingerprint",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_redaction_verification_events",
        sa.Column("detected_face_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "audit_redaction_verification_events",
        sa.Column(
            "detected_sensitive_region_count",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_audit_privacy_verification_status",
        "audit_redaction_verification_events",
        "verification_status IN ('verified','rejected','blocked','tampered')",
    )
    op.create_check_constraint(
        "ck_audit_privacy_nonverified_reason",
        "audit_redaction_verification_events",
        "verification_status = 'verified' OR "
        "length(trim(COALESCE(reason,''))) > 0",
    )
    op.create_check_constraint(
        "ck_audit_privacy_authority_version",
        "audit_redaction_verification_events",
        "verification_authority_version IS NULL OR "
        f"verification_authority_version = '{SERVER_AUTHORITY_VERSION}'",
    )
    op.create_check_constraint(
        "ck_audit_privacy_observation_integrity",
        "audit_redaction_verification_events",
        "(observed_sha256 IS NULL AND observed_byte_size IS NULL) OR "
        "(observed_sha256 ~ '^[0-9a-f]{64}$' AND observed_byte_size >= 0)",
    )
    op.create_check_constraint(
        "ck_audit_privacy_scanner_integrity",
        "audit_redaction_verification_events",
        "(scanner_model_ref IS NULL AND scanner_model_fingerprint IS NULL "
        "AND detected_face_count IS NULL "
        "AND detected_sensitive_region_count IS NULL) OR "
        "(length(trim(scanner_model_ref)) > 0 "
        "AND scanner_model_fingerprint ~ '^[0-9a-f]{64}$' "
        "AND detected_face_count >= 0 "
        "AND detected_sensitive_region_count >= 0)",
    )
    op.create_check_constraint(
        "ck_audit_privacy_server_authority_complete",
        "audit_redaction_verification_events",
        f"verification_authority_version <> '{SERVER_AUTHORITY_VERSION}' OR "
        "(observed_sha256 IS NOT NULL AND observed_byte_size IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_audit_privacy_verified_has_scanner",
        "audit_redaction_verification_events",
        "verification_status <> 'verified' OR "
        "verification_authority_version IS NULL OR "
        "(observed_sha256 IS NOT NULL AND observed_byte_size IS NOT NULL "
        "AND scanner_model_ref IS NOT NULL "
        "AND scanner_model_fingerprint IS NOT NULL "
        "AND detected_face_count = 0 "
        "AND detected_sensitive_region_count = 0)",
    )
    op.create_check_constraint(
        "ck_audit_privacy_rejected_has_scanner",
        "audit_redaction_verification_events",
        "verification_status <> 'rejected' OR "
        "verification_authority_version IS NULL OR "
        "(scanner_model_ref IS NOT NULL "
        "AND scanner_model_fingerprint IS NOT NULL "
        "AND (detected_face_count > 0 "
        "OR detected_sensitive_region_count > 0))",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_audit_privacy_rejected_has_scanner",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_verified_has_scanner",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_server_authority_complete",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_scanner_integrity",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_observation_integrity",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_authority_version",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_nonverified_reason",
        "audit_redaction_verification_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_privacy_verification_status",
        "audit_redaction_verification_events",
        type_="check",
    )

    for column_name in (
        "detected_sensitive_region_count",
        "detected_face_count",
        "scanner_model_fingerprint",
        "scanner_model_ref",
        "observed_byte_size",
        "observed_sha256",
        "verification_authority_version",
    ):
        op.drop_column("audit_redaction_verification_events", column_name)

    op.create_check_constraint(
        "ck_audit_privacy_verification_status",
        "audit_redaction_verification_events",
        "verification_status IN ('verified','rejected')",
    )
    op.create_check_constraint(
        "ck_audit_privacy_rejection_reason",
        "audit_redaction_verification_events",
        "verification_status <> 'rejected' OR "
        "length(trim(COALESCE(reason,''))) > 0",
    )
