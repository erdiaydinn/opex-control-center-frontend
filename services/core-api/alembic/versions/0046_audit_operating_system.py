"""Add tenant-safe EAY Audit operating-system authority.

Revision ID: 0046_audit_operating_system
Revises: 0045_academy_content_locale_expansion
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0046_audit_operating_system"
down_revision: str = "0045_academy_content_locale_expansion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RUNTIME_ROLE = "opex_runtime"

AUDIT_AUDITOR_PERMISSIONS = (
    "module:audit:view",
    "feature:audit:audits",
    "feature:audit:capture",
    "feature:audit:actions",
    "action:audit:startAudit",
    "action:audit:submitEvidence",
    "action:audit:decideItem",
    "action:audit:createAction",
    "action:audit:updateAction",
    "action:audit:submitVerification",
)
AUDIT_MANAGER_PERMISSIONS = AUDIT_AUDITOR_PERMISSIONS + (
    "feature:audit:commandCenter",
    "feature:audit:scheduling",
    "feature:audit:analytics",
    "feature:audit:assurance",
    "feature:audit:locations",
    "feature:audit:reports",
    "feature:audit:jarvis",
    "action:audit:verifyAction",
    "action:audit:reviewDisagreement",
    "action:audit:manageScheduling",
    "action:audit:exportResults",
)
AUDIT_STANDARDS_PERMISSIONS = AUDIT_MANAGER_PERMISSIONS + (
    "module:audit:admin",
    "feature:audit:standards",
    "action:audit:manageStandards",
    "action:audit:manageLocations",
)
AUDIT_EXECUTIVE_PERMISSIONS = (
    "module:audit:view",
    "feature:audit:commandCenter",
    "feature:audit:audits",
    "feature:audit:actions",
    "feature:audit:analytics",
    "feature:audit:reports",
    "feature:audit:jarvis",
    "action:audit:exportResults",
)
ROLE_POLICIES = {
    "audit_auditor": ("Audit Auditor", AUDIT_AUDITOR_PERMISSIONS),
    "audit_manager": ("Audit Manager", AUDIT_MANAGER_PERMISSIONS),
    "audit_standards": ("Audit Standards", AUDIT_STANDARDS_PERMISSIONS),
    "audit_executive": ("Audit Executive", AUDIT_EXECUTIVE_PERMISSIONS),
}


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    op.create_table(
        "audit_program_versions",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("program_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name_i18n", JSONB, nullable=False),
        sa.Column("field_template_id", sa.String(length=120), nullable=False),
        sa.Column("field_template_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scoring_policy", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "field_template_id", "field_template_version"],
            ["field_templates.tenant_id", "field_templates.template_id", "field_templates.version"],
            ondelete="RESTRICT",
            name="fk_audit_program_field_template",
        ),
        sa.CheckConstraint("version > 0", name="ck_audit_program_version"),
        sa.CheckConstraint(
            "status IN ('draft','active','retired')", name="ck_audit_program_status"
        ),
        sa.CheckConstraint(
            "status <> 'active' OR effective_from IS NOT NULL",
            name="ck_audit_program_active_effective",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "program_key", "version", name="pk_audit_program_versions"
        ),
    )
    op.create_index(
        "ix_audit_program_status_effective",
        "audit_program_versions",
        ["tenant_id", "program_key", "status", "effective_from"],
    )

    op.create_table(
        "audit_runs",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("program_key", sa.String(length=120), nullable=False),
        sa.Column("program_version", sa.Integer(), nullable=False),
        sa.Column("field_mission_id", UUID, nullable=True),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("auditor_subject", sa.String(length=255), nullable=False),
        sa.Column("manager_subject", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="in_progress"),
        sa.Column("source_mode", sa.String(length=30), nullable=False, server_default="checklist"),
        sa.Column("progress_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("final_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("score_basis_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "program_key", "program_version"],
            [
                "audit_program_versions.tenant_id",
                "audit_program_versions.program_key",
                "audit_program_versions.version",
            ],
            ondelete="RESTRICT",
            name="fk_audit_run_program",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["field_locations.tenant_id", "field_locations.location_id"],
            ondelete="RESTRICT",
            name="fk_audit_run_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "field_mission_id"],
            ["field_missions.tenant_id", "field_missions.id"],
            ondelete="SET NULL",
            name="fk_audit_run_field_mission",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress','submitted','completed','cancelled')",
            name="ck_audit_run_status",
        ),
        sa.CheckConstraint(
            "source_mode IN ('checklist','photo','video','guided_video','mixed')",
            name="ck_audit_run_source_mode",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_audit_run_progress",
        ),
        sa.CheckConstraint(
            "final_score IS NULL OR (final_score >= 0 AND final_score <= 100)",
            name="ck_audit_run_score",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="ck_audit_run_completed_at",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_runs"),
    )
    op.create_index(
        "ix_audit_runs_status_location",
        "audit_runs",
        ["tenant_id", "status", "location_id", "started_at"],
    )

    op.create_table(
        "audit_redaction_receipts",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_run_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("device_id", sa.String(length=180), nullable=True),
        sa.Column("media_kind", sa.String(length=12), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("redacted_evidence_ref", sa.String(length=500), nullable=False),
        sa.Column("privacy_policy_version", sa.String(length=80), nullable=False),
        sa.Column("detector_model_ref", sa.String(length=300), nullable=False),
        sa.Column("frame_count", sa.BigInteger(), nullable=False),
        sa.Column("processed_frame_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "audit_run_id"],
            ["audit_runs.tenant_id", "audit_runs.id"],
            ondelete="RESTRICT",
            name="fk_audit_redaction_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["field_locations.tenant_id", "field_locations.location_id"],
            ondelete="RESTRICT",
            name="fk_audit_redaction_location",
        ),
        sa.CheckConstraint("media_kind IN ('image','video')", name="ck_audit_redaction_kind"),
        sa.CheckConstraint("frame_count > 0", name="ck_audit_redaction_frame_count"),
        sa.CheckConstraint(
            "processed_frame_count = frame_count",
            name="ck_audit_redaction_complete_coverage",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_redaction_receipts"),
        sa.UniqueConstraint(
            "tenant_id",
            "audit_run_id",
            "source_fingerprint",
            name="uq_audit_redaction_source",
        ),
    )

    op.create_table(
        "audit_item_decision_events",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_run_id", UUID, nullable=False),
        sa.Column("item_key", sa.String(length=180), nullable=False),
        sa.Column("decision_source", sa.String(length=30), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("model_or_rule_ref", sa.String(length=300), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("actor_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "audit_run_id"],
            ["audit_runs.tenant_id", "audit_runs.id"],
            ondelete="RESTRICT",
            name="fk_audit_decision_run",
        ),
        sa.CheckConstraint(
            "decision_source IN ('AI','AUDITOR','MANAGER','OPERATIONS_STANDARDS')",
            name="ck_audit_decision_source",
        ),
        sa.CheckConstraint(
            "decision IN"
            " ('PASS','FAIL','NOT_APPLICABLE','REVIEW_REQUIRED','INSUFFICIENT_EVIDENCE')",
            name="ck_audit_decision_value",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_audit_decision_confidence",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_item_decision_events"),
    )
    op.create_index(
        "ix_audit_decision_run_item",
        "audit_item_decision_events",
        ["tenant_id", "audit_run_id", "item_key", "created_at"],
    )

    op.create_table(
        "audit_assurance_reviews",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_run_id", UUID, nullable=False),
        sa.Column("item_key", sa.String(length=180), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("reviewer_subject", sa.String(length=255), nullable=False),
        sa.Column("disposition", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "audit_run_id"],
            ["audit_runs.tenant_id", "audit_runs.id"],
            ondelete="RESTRICT",
            name="fk_audit_assurance_run",
        ),
        sa.CheckConstraint(
            "state IN ('MANAGER_REVIEW','OPERATIONS_STANDARDS_REVIEW','RESOLVED')",
            name="ck_audit_assurance_state",
        ),
        sa.CheckConstraint(
            "disposition IN"
            " ('AI_CONFIRMED','AUDITOR_CONFIRMED','STANDARD_CHANGED','MODEL_REVIEW_REQUIRED','NO_CHANGE')",
            name="ck_audit_assurance_disposition",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0", name="ck_audit_assurance_reason"
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_assurance_reviews"),
    )
    op.create_index(
        "ix_audit_assurance_run_item",
        "audit_assurance_reviews",
        ["tenant_id", "audit_run_id", "item_key", "reviewed_at"],
    )

    op.create_table(
        "audit_actions",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audit_run_id", UUID, nullable=False),
        sa.Column("item_key", sa.String(length=180), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_class", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("assignee_subject", sa.String(length=255), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closure_evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("verification_receipt_ref", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "audit_run_id"],
            ["audit_runs.tenant_id", "audit_runs.id"],
            ondelete="RESTRICT",
            name="fk_audit_action_run",
        ),
        sa.CheckConstraint(
            "risk_class IN"
            " ('life_safety','food_safety','legal','operational','brand','quality','other')",
            name="ck_audit_action_risk_class",
        ),
        sa.CheckConstraint(
            "priority IN ('critical','high','medium','low')",
            name="ck_audit_action_priority",
        ),
        sa.CheckConstraint(
            "status IN"
            " ('open','in_progress','submitted_for_verification','ai_verified','human_verified','rejected','closed')",
            name="ck_audit_action_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_audit_action_version"),
        sa.CheckConstraint(
            "status NOT IN ('ai_verified','human_verified','closed') OR"
            " (closure_evidence_ref IS NOT NULL AND verification_receipt_ref IS NOT NULL)",
            name="ck_audit_action_verified_closure",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_actions"),
    )
    op.create_index(
        "ix_audit_actions_status_due",
        "audit_actions",
        ["tenant_id", "status", "due_at"],
    )

    for table_name in (
        "audit_program_versions",
        "audit_runs",
        "audit_redaction_receipts",
        "audit_item_decision_events",
        "audit_assurance_reviews",
        "audit_actions",
    ):
        _tenant_policy(table_name)

    op.execute(
        "CREATE FUNCTION prevent_audit_append_only_mutation() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN RAISE EXCEPTION 'audit evidence and assurance history is append-only'; END; $$"
    )
    for table_name in (
        "audit_redaction_receipts",
        "audit_item_decision_events",
        "audit_assurance_reviews",
    ):
        op.execute(
            f"CREATE TRIGGER {table_name}_append_only BEFORE UPDATE OR DELETE ON {table_name}"
            " FOR EACH ROW EXECUTE FUNCTION prevent_audit_append_only_mutation()"
        )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE audit_program_versions, audit_runs, audit_actions TO "
        + RUNTIME_ROLE
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE audit_redaction_receipts, audit_item_decision_events,"
        " audit_assurance_reviews TO " + RUNTIME_ROLE
    )

    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM roles WHERE key='{escaped}' AND is_system IS"
            f" FALSE) THEN RAISE EXCEPTION 'Canonical Audit role collision: {escaped}'; END IF;"
            " END $$"
        )

    all_scope = '\'{"type":"all"}\'::jsonb'
    for role_key, (role_name, permissions) in ROLE_POLICIES.items():
        escaped_key = role_key.replace("'", "''")
        escaped_name = role_name.replace("'", "''")
        permission_array = _sql_array(tuple(permissions))
        op.execute(
            "INSERT INTO roles (tenant_id,key,name,is_system) SELECT"
            f" id,'{escaped_key}','{escaped_name}',TRUE FROM tenants ON CONFLICT (tenant_id,key) DO"
            " UPDATE SET name=EXCLUDED.name WHERE roles.is_system IS TRUE"
        )
        op.execute(
            "INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) SELECT"
            f" r.tenant_id,r.id,p.permission_key,{all_scope} FROM roles r CROSS JOIN"
            f" unnest({permission_array}) p(permission_key) WHERE r.key='{escaped_key}' AND"
            " r.is_system IS TRUE ON CONFLICT (tenant_id,role_id,permission_key) DO UPDATE SET"
            " scope=EXCLUDED.scope"
        )

    super_admin_keys = tuple(
        sorted(
            set(AUDIT_STANDARDS_PERMISSIONS)
            | set(AUDIT_EXECUTIVE_PERMISSIONS)
        )
    )
    op.execute(
        "INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) SELECT"
        f" r.tenant_id,r.id,p.permission_key,{all_scope} FROM roles r CROSS JOIN"
        f" unnest({_sql_array(super_admin_keys)}) p(permission_key) WHERE r.key='super_admin' AND"
        " r.is_system IS TRUE ON CONFLICT (tenant_id,role_id,permission_key) DO UPDATE SET"
        " scope=EXCLUDED.scope"
    )


def downgrade() -> None:
    created_keys = tuple(
        sorted(
            set(AUDIT_STANDARDS_PERMISSIONS)
            | set(AUDIT_EXECUTIVE_PERMISSIONS)
        )
    )
    op.execute(
        "DELETE FROM role_permissions rp USING roles r WHERE rp.tenant_id=r.tenant_id AND"
        " rp.role_id=r.id AND r.key='super_admin' AND r.is_system IS TRUE AND"
        f" rp.permission_key=ANY({_sql_array(created_keys)})"
    )
    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            "DELETE FROM role_permissions rp USING roles r WHERE rp.tenant_id=r.tenant_id AND"
            f" rp.role_id=r.id AND r.key='{escaped}' AND r.is_system IS TRUE"
        )
        op.execute(
            f"DELETE FROM roles r WHERE r.key='{escaped}' AND r.is_system IS TRUE AND NOT EXISTS"
            " (SELECT 1 FROM membership_roles mr WHERE mr.tenant_id=r.tenant_id AND"
            " mr.role_id=r.id)"
        )

    for table_name in (
        "audit_assurance_reviews",
        "audit_item_decision_events",
        "audit_redaction_receipts",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_append_only_mutation()")

    for table_name in (
        "audit_actions",
        "audit_assurance_reviews",
        "audit_item_decision_events",
        "audit_redaction_receipts",
        "audit_runs",
        "audit_program_versions",
    ):
        op.drop_table(table_name)
