"""Add tenant-safe Field Intelligence product authority.

Revision ID: 0019_field_intelligence_foundation
Revises: 0018_academy_product_roles
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019_field_intelligence_foundation"
down_revision: str = "0018_academy_product_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RUNTIME_ROLE = "opex_runtime"

FIELD_WORKER_PERMISSIONS = (
    "module:field_intelligence:view",
    "feature:field_intelligence:missions",
    "feature:field_intelligence:capture",
    "action:field_intelligence:submitEvidence",
)
FIELD_MANAGER_PERMISSIONS = FIELD_WORKER_PERMISSIONS + (
    "module:field_intelligence:admin",
    "feature:field_intelligence:commandCenter",
    "feature:field_intelligence:missionBuilder",
    "feature:field_intelligence:evidenceReview",
    "feature:field_intelligence:targeting",
    "feature:field_intelligence:templates",
    "feature:field_intelligence:analytics",
    "action:field_intelligence:createMission",
    "action:field_intelligence:activateMission",
    "action:field_intelligence:cancelMission",
    "action:field_intelligence:sendReminder",
    "action:field_intelligence:reviewEvidence",
    "action:field_intelligence:manageTemplates",
    "action:field_intelligence:manageLocations",
    "action:field_intelligence:exportResults",
    "action:field_intelligence:viewEvidence",
)
ROLE_POLICIES = {
    "field_worker": ("Field Worker", FIELD_WORKER_PERMISSIONS),
    "field_manager": ("Field Manager", FIELD_MANAGER_PERMISSIONS),
}


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(f"""CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    op.create_table(
        "field_locations",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("district", sa.String(length=120), nullable=True),
        sa.Column(
            "groups", postgresql.ARRAY(sa.String(length=120)), nullable=False, server_default="{}"
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_ref", sa.String(length=300), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("tenant_id", "location_id", name="pk_field_locations"),
    )
    op.create_index(
        "ix_field_locations_geo",
        "field_locations",
        ["tenant_id", "country", "region", "city", "district"],
    )

    op.create_table(
        "field_templates",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("template_id", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("name_i18n", JSONB, nullable=False),
        sa.Column("schema", JSONB, nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("version > 0", name="ck_field_template_version"),
        sa.CheckConstraint(
            "status IN ('draft','active','retired')", name="ck_field_template_status"
        ),
        sa.PrimaryKeyConstraint("tenant_id", "template_id", "version", name="pk_field_templates"),
    )

    op.create_table(
        "field_missions",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", sa.String(length=120), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("title_i18n", JSONB, nullable=False),
        sa.Column(
            "instructions_i18n", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("selector", JSONB, nullable=False),
        sa.Column("target_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
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
            name="fk_field_mission_template",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','closed','cancelled')", name="ck_field_mission_status"
        ),
        sa.CheckConstraint(
            "priority IN ('normal','high','critical')", name="ck_field_mission_priority"
        ),
        sa.CheckConstraint("target_count > 0", name="ck_field_mission_target_count"),
        sa.CheckConstraint("deadline_at > assigned_at", name="ck_field_mission_deadline"),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_missions"),
    )
    op.create_index(
        "ix_field_missions_status_deadline",
        "field_missions",
        ["tenant_id", "status", "deadline_at"],
    )

    op.create_table(
        "field_mission_targets",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unseen"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["field_missions.tenant_id", "field_missions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["field_locations.tenant_id", "field_locations.location_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN"
            " ('unseen','seen','started','partial','submitted','rework',"
            "'verified','overdue','exempt')",
            name="ck_field_target_status",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "mission_id", "location_id", name="pk_field_mission_targets"
        ),
    )
    op.create_index(
        "ix_field_target_status", "field_mission_targets", ["tenant_id", "mission_id", "status"]
    )

    op.create_table(
        "field_evidence",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=False),
        sa.Column("device_id", sa.String(length=180), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id", "location_id"],
            [
                "field_mission_targets.tenant_id",
                "field_mission_targets.mission_id",
                "field_mission_targets.location_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_evidence"),
        sa.UniqueConstraint(
            "tenant_id",
            "mission_id",
            "location_id",
            "fingerprint",
            name="uq_field_evidence_fingerprint",
        ),
    )

    op.create_table(
        "field_reviews",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("evidence_id", UUID, nullable=False),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("reviewer_subject", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["field_evidence.tenant_id", "field_evidence.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "decision IN ('accept','rework','reject')", name="ck_field_review_decision"
        ),
        sa.CheckConstraint(
            "decision = 'accept' OR length(trim(coalesce(reason,''))) > 0",
            name="ck_field_review_reason",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_reviews"),
    )

    for table_name in (
        "field_locations",
        "field_templates",
        "field_missions",
        "field_mission_targets",
        "field_evidence",
        "field_reviews",
    ):
        _tenant_policy(table_name)

    op.execute(
        "CREATE FUNCTION prevent_field_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN RAISE EXCEPTION 'field evidence is append-only'; END; $$"
    )
    op.execute(
        "CREATE TRIGGER field_evidence_append_only BEFORE UPDATE OR DELETE ON field_evidence FOR"
        " EACH ROW EXECUTE FUNCTION prevent_field_evidence_mutation()"
    )
    op.execute(
        "CREATE TRIGGER field_reviews_append_only BEFORE UPDATE OR DELETE ON field_reviews FOR EACH"
        " ROW EXECUTE FUNCTION prevent_field_evidence_mutation()"
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE field_locations, field_templates,"
        " field_missions, field_mission_targets TO " + RUNTIME_ROLE
    )
    op.execute("GRANT SELECT, INSERT ON TABLE field_evidence, field_reviews TO " + RUNTIME_ROLE)

    for role_key in ROLE_POLICIES:
        escaped = role_key.replace("'", "''")
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM roles WHERE key='{escaped}' AND is_system IS"
            f" FALSE) THEN RAISE EXCEPTION 'Canonical Field role collision: {escaped}'; END IF;"
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

    super_admin_keys = tuple(sorted(set(FIELD_MANAGER_PERMISSIONS)))
    op.execute(
        "INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) SELECT"
        f" r.tenant_id,r.id,p.permission_key,{all_scope} FROM roles r CROSS JOIN"
        f" unnest({_sql_array(super_admin_keys)}) p(permission_key) WHERE r.key='super_admin' AND"
        " r.is_system IS TRUE ON CONFLICT (tenant_id,role_id,permission_key) DO UPDATE SET"
        " scope=EXCLUDED.scope"
    )


def downgrade() -> None:
    created_keys = tuple(sorted(set(FIELD_MANAGER_PERMISSIONS)))
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
    op.execute("DROP TRIGGER IF EXISTS field_reviews_append_only ON field_reviews")
    op.execute("DROP TRIGGER IF EXISTS field_evidence_append_only ON field_evidence")
    op.execute("DROP FUNCTION IF EXISTS prevent_field_evidence_mutation()")
    for table_name in (
        "field_reviews",
        "field_evidence",
        "field_mission_targets",
        "field_missions",
        "field_templates",
        "field_locations",
    ):
        op.drop_table(table_name)
