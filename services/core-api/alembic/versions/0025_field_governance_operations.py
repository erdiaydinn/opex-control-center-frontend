"""Add Field recurrence, exemption and governed export evidence.

Revision ID: 0025_field_governance_operations
Revises: 0024_field_evidence_object_upload
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025_field_governance_operations"
down_revision: str = "0024_field_evidence_object_upload"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RUNTIME_ROLE = "opex_runtime"

NEW_PERMISSIONS = (
    "action:field_intelligence:manageRecurrence",
    "action:field_intelligence:exemptTarget",
    "action:field_intelligence:approveExport",
)


def _tenant_policy(table_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)'''
    )


def _append_only(table_name: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table_name}_append_only BEFORE UPDATE OR DELETE ON {table_name} "
        "FOR EACH ROW EXECUTE FUNCTION prevent_field_evidence_mutation()"
    )


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    op.create_table(
        "field_recurrence_rules",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=False),
        sa.Column("interval_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("rule_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["field_missions.tenant_id", "field_missions.id"],
            ondelete="RESTRICT",
            name="fk_field_recurrence_mission",
        ),
        sa.CheckConstraint("revision > 0", name="ck_field_recurrence_revision"),
        sa.CheckConstraint(
            "cadence IN ('daily','weekly','monthly')", name="ck_field_recurrence_cadence"
        ),
        sa.CheckConstraint("interval_count BETWEEN 1 AND 52", name="ck_field_recurrence_interval"),
        sa.CheckConstraint("window_minutes BETWEEN 5 AND 10080", name="ck_field_recurrence_window"),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_field_recurrence_status"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from",
            name="ck_field_recurrence_effective_window",
        ),
        sa.CheckConstraint(
            "rule_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_recurrence_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_recurrence_rules"),
        sa.UniqueConstraint(
            "tenant_id", "mission_id", "revision", name="uq_field_recurrence_revision"
        ),
        sa.UniqueConstraint(
            "tenant_id", "rule_fingerprint", name="uq_field_recurrence_fingerprint"
        ),
    )

    op.create_table(
        "field_target_exemptions",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("reason_code", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_ref_hash", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=False),
        sa.Column("exemption_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
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
            name="fk_field_exemption_target",
        ),
        sa.CheckConstraint(
            "evidence_ref_hash IS NULL OR evidence_ref_hash ~ '^[0-9a-f]{64}$'",
            name="ck_field_exemption_evidence_ref_hash",
        ),
        sa.CheckConstraint(
            "exemption_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_exemption_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_target_exemptions"),
        sa.UniqueConstraint(
            "tenant_id", "mission_id", "location_id", name="uq_field_target_exemption"
        ),
    )

    op.create_table(
        "field_export_requests",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mission_id", UUID, nullable=True),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("scope_snapshot", JSONB, nullable=False),
        sa.Column("scope_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mission_id"],
            ["field_missions.tenant_id", "field_missions.id"],
            ondelete="RESTRICT",
            name="fk_field_export_mission",
        ),
        sa.CheckConstraint("format IN ('csv','xlsx','json')", name="ck_field_export_format"),
        sa.CheckConstraint(
            "scope_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_export_scope_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_export_requests"),
    )

    op.create_table(
        "field_export_decisions",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("export_request_id", UUID, nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=255), nullable=False),
        sa.Column("decision_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "export_request_id"],
            ["field_export_requests.tenant_id", "field_export_requests.id"],
            ondelete="RESTRICT",
            name="fk_field_export_decision_request",
        ),
        sa.CheckConstraint("decision IN ('approve','reject')", name="ck_field_export_decision"),
        sa.CheckConstraint(
            "decision='approve' OR length(trim(coalesce(reason,''))) > 0",
            name="ck_field_export_reject_reason",
        ),
        sa.CheckConstraint(
            "decision_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_export_decision_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_export_decisions"),
        sa.UniqueConstraint(
            "tenant_id", "export_request_id", name="uq_field_export_single_decision"
        ),
    )

    for table_name in (
        "field_recurrence_rules",
        "field_target_exemptions",
        "field_export_requests",
        "field_export_decisions",
    ):
        _tenant_policy(table_name)
        _append_only(table_name)
        op.execute(f"GRANT SELECT, INSERT ON TABLE {table_name} TO {RUNTIME_ROLE}")

    all_scope = '\'{"type":"all"}\'::jsonb'
    permissions = _sql_array(NEW_PERMISSIONS)
    op.execute(
        f"INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) "
        f"SELECT r.tenant_id,r.id,p.permission_key,{all_scope} "
        f"FROM roles r CROSS JOIN unnest({permissions}) p(permission_key) "
        "WHERE r.key='field_manager' AND r.is_system IS TRUE "
        "ON CONFLICT (tenant_id,role_id,permission_key) DO UPDATE SET scope=EXCLUDED.scope"
    )
    op.execute(
        f"INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) "
        f"SELECT r.tenant_id,r.id,p.permission_key,{all_scope} "
        f"FROM roles r CROSS JOIN unnest({permissions}) p(permission_key) "
        "WHERE r.key='super_admin' AND r.is_system IS TRUE "
        "ON CONFLICT (tenant_id,role_id,permission_key) DO UPDATE SET scope=EXCLUDED.scope"
    )


def downgrade() -> None:
    permissions = _sql_array(NEW_PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions rp USING roles r "
        f"WHERE rp.tenant_id=r.tenant_id AND rp.role_id=r.id "
        f"AND r.key IN ('field_manager','super_admin') AND r.is_system IS TRUE "
        f"AND rp.permission_key=ANY({permissions})"
    )
    for table_name in (
        "field_export_decisions",
        "field_export_requests",
        "field_target_exemptions",
        "field_recurrence_rules",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name}")
        op.drop_table(table_name)
