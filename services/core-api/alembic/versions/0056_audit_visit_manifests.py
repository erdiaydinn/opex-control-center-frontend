"""Add governed Audit visit manifests and run binding.

Revision ID: 0056_audit_visit_manifests
Revises: 0055_merge_audit_parent_heads
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0056_audit_visit_manifests"
down_revision: str = "0055_merge_audit_parent_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RUNTIME_ROLE = "opex_runtime"


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
    op.create_table(
        "audit_visit_manifests",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("program_key", sa.String(length=120), nullable=True),
        sa.Column("program_version", sa.Integer(), nullable=True),
        sa.Column("visit_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("score_mode", sa.String(length=24), nullable=False),
        sa.Column("official_compliance_eligible", sa.Boolean(), nullable=False),
        sa.Column("scope_manifest", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("people_topics", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scope_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["field_locations.tenant_id", "field_locations.location_id"],
            ondelete="RESTRICT",
            name="fk_audit_visit_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "program_key", "program_version"],
            [
                "audit_program_versions.tenant_id",
                "audit_program_versions.program_key",
                "audit_program_versions.version",
            ],
            ondelete="RESTRICT",
            name="fk_audit_visit_program",
        ),
        sa.CheckConstraint(
            (
                "visit_type IN ('FULL_AUDIT','QUICK_AUDIT','FOCUS_AUDIT',"
                "'CUSTOM_AUDIT','PEOPLE_VISIT','SPECIAL_VISIT')"
            ),
            name="ck_audit_visit_type",
        ),
        sa.CheckConstraint(
            "score_mode IN ('OFFICIAL_COMPLIANCE','FOCUS_SCORE','NO_SCORE')",
            name="ck_audit_visit_score_mode",
        ),
        sa.CheckConstraint(
            "status IN ('active','completed','cancelled')",
            name="ck_audit_visit_status",
        ),
        sa.CheckConstraint(
            "(program_key IS NULL) = (program_version IS NULL)",
            name="ck_audit_visit_program_pair",
        ),
        sa.CheckConstraint(
            "visit_type = 'PEOPLE_VISIT' OR program_key IS NOT NULL",
            name="ck_audit_scored_visit_program",
        ),
        sa.CheckConstraint(
            (
                "visit_type <> 'PEOPLE_VISIT' OR "
                "(program_key IS NULL AND score_mode = 'NO_SCORE' "
                "AND official_compliance_eligible IS FALSE)"
            ),
            name="ck_audit_people_visit_no_score",
        ),
        sa.CheckConstraint(
            (
                "visit_type <> 'FULL_AUDIT' OR "
                "(score_mode = 'OFFICIAL_COMPLIANCE' "
                "AND official_compliance_eligible IS TRUE)"
            ),
            name="ck_audit_full_visit_official_score",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="ck_audit_visit_completed_at",
        ),
        sa.CheckConstraint(
            "scope_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_audit_visit_scope_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_visit_manifests"),
    )
    op.create_index(
        "ix_audit_visit_location_created",
        "audit_visit_manifests",
        ["tenant_id", "location_id", "created_at"],
    )
    _tenant_policy("audit_visit_manifests")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON TABLE audit_visit_manifests TO {RUNTIME_ROLE}"
    )

    op.create_table(
        "audit_visit_notes",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("visit_manifest_id", UUID, nullable=False),
        sa.Column("note_type", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "visit_manifest_id"],
            ["audit_visit_manifests.tenant_id", "audit_visit_manifests.id"],
            ondelete="RESTRICT",
            name="fk_audit_visit_note_manifest",
        ),
        sa.CheckConstraint(
            (
                "note_type IN ('HUMAN_CONVERSATION','OPERATION_OBSERVATION',"
                "'POSITIVE_PRACTICE','FOLLOW_UP','OTHER')"
            ),
            name="ck_audit_visit_note_type",
        ),
        sa.CheckConstraint("length(trim(note)) > 0", name="ck_audit_visit_note_nonblank"),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_visit_notes"),
    )
    op.create_index(
        "ix_audit_visit_notes_manifest_created",
        "audit_visit_notes",
        ["tenant_id", "visit_manifest_id", "created_at"],
    )
    _tenant_policy("audit_visit_notes")
    op.execute(f"GRANT SELECT, INSERT ON TABLE audit_visit_notes TO {RUNTIME_ROLE}")

    op.add_column("audit_runs", sa.Column("visit_manifest_id", UUID, nullable=True))
    op.add_column(
        "audit_runs",
        sa.Column(
            "visit_score_mode",
            sa.String(length=24),
            nullable=False,
            server_default="OFFICIAL_COMPLIANCE",
        ),
    )
    op.add_column(
        "audit_runs",
        sa.Column(
            "official_compliance_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )
    op.create_check_constraint(
        "ck_audit_run_visit_score_mode",
        "audit_runs",
        "visit_score_mode IN ('OFFICIAL_COMPLIANCE','FOCUS_SCORE')",
    )
    op.create_check_constraint(
        "ck_audit_run_official_score_binding",
        "audit_runs",
        "official_compliance_eligible IS FALSE OR visit_score_mode = 'OFFICIAL_COMPLIANCE'",
    )
    op.create_foreign_key(
        "fk_audit_run_visit_manifest",
        "audit_runs",
        "audit_visit_manifests",
        ["tenant_id", "visit_manifest_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_audit_run_visit_manifest",
        "audit_runs",
        ["tenant_id", "visit_manifest_id"],
        unique=True,
        postgresql_where=sa.text("visit_manifest_id IS NOT NULL"),
    )
    op.create_index(
        "ix_audit_runs_official_compliance",
        "audit_runs",
        ["tenant_id", "official_compliance_eligible", "location_id", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_runs_official_compliance", table_name="audit_runs")
    op.drop_index("uq_audit_run_visit_manifest", table_name="audit_runs")
    op.drop_constraint("fk_audit_run_visit_manifest", "audit_runs", type_="foreignkey")
    op.drop_constraint("ck_audit_run_official_score_binding", "audit_runs", type_="check")
    op.drop_constraint("ck_audit_run_visit_score_mode", "audit_runs", type_="check")
    op.drop_column("audit_runs", "official_compliance_eligible")
    op.drop_column("audit_runs", "visit_score_mode")
    op.drop_column("audit_runs", "visit_manifest_id")
    op.drop_index("ix_audit_visit_notes_manifest_created", table_name="audit_visit_notes")
    op.drop_table("audit_visit_notes")
    op.drop_index("ix_audit_visit_location_created", table_name="audit_visit_manifests")
    op.drop_table("audit_visit_manifests")
