"""Add governed Field-to-module promotion evidence chain.

Revision ID: 0023_field_governed_promotion
Revises: 0022_field_evidence_integrity
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023_field_governed_promotion"
down_revision: str = "0022_field_evidence_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
RUNTIME_ROLE = "opex_runtime"

FIELD_PROMOTION_PERMISSIONS = (
    "feature:field_intelligence:promotions",
    "action:field_intelligence:proposePromotion",
    "action:field_intelligence:approvePromotion",
    "action:field_intelligence:viewPromotions",
)
CONSUMER_PROMOTION_PERMISSIONS = (
    "action:inventory:acceptFieldEvidence",
    "action:planogram:acceptFieldEvidence",
    "action:budget:acceptFieldEvidence",
)


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


def _sql_array(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"ARRAY[{quoted}]::varchar[]"


def upgrade() -> None:
    op.create_table(
        "field_promotion_requests",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("evidence_id", UUID, nullable=False),
        sa.Column("review_id", UUID, nullable=False),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("consumer_module", sa.String(length=40), nullable=False),
        sa.Column("adapter_key", sa.String(length=120), nullable=False),
        sa.Column("adapter_version", sa.Integer(), nullable=False),
        sa.Column("source_evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("candidate_payload", JSONB, nullable=False),
        sa.Column("candidate_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("proposal_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["field_evidence.tenant_id", "field_evidence.id"],
            ondelete="RESTRICT",
            name="fk_field_promotion_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["field_reviews.tenant_id", "field_reviews.id"],
            ondelete="RESTRICT",
            name="fk_field_promotion_review",
        ),
        sa.CheckConstraint(
            "consumer_module IN ('inventory','planogram','budget')",
            name="ck_field_promotion_consumer_module",
        ),
        sa.CheckConstraint("adapter_version > 0", name="ck_field_promotion_adapter_version"),
        sa.CheckConstraint(
            "source_evidence_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_promotion_source_fingerprint",
        ),
        sa.CheckConstraint(
            "candidate_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_promotion_candidate_fingerprint",
        ),
        sa.CheckConstraint(
            "proposal_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_promotion_proposal_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_promotion_requests"),
        sa.UniqueConstraint(
            "tenant_id", "proposal_fingerprint", name="uq_field_promotion_proposal_fingerprint"
        ),
    )
    op.create_index(
        "ix_field_promotion_source",
        "field_promotion_requests",
        ["tenant_id", "evidence_id", "consumer_module", "requested_at"],
    )

    op.create_table(
        "field_promotion_decisions",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("promotion_id", UUID, nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("decided_by", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decision_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "promotion_id"],
            ["field_promotion_requests.tenant_id", "field_promotion_requests.id"],
            ondelete="RESTRICT",
            name="fk_field_promotion_decision_request",
        ),
        sa.CheckConstraint("decision IN ('approve','reject')", name="ck_field_promotion_decision"),
        sa.CheckConstraint(
            "decision = 'approve' OR length(trim(coalesce(reason,''))) > 0",
            name="ck_field_promotion_reject_reason",
        ),
        sa.CheckConstraint(
            "decision_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_promotion_decision_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_promotion_decisions"),
        sa.UniqueConstraint("tenant_id", "promotion_id", name="uq_field_promotion_single_decision"),
    )

    op.create_table(
        "field_promotion_consumer_receipts",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("promotion_id", UUID, nullable=False),
        sa.Column("consumer_module", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("accepted_by", sa.String(length=255), nullable=False),
        sa.Column("destination_candidate_ref_hash", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("receipt_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "promotion_id"],
            ["field_promotion_requests.tenant_id", "field_promotion_requests.id"],
            ondelete="RESTRICT",
            name="fk_field_promotion_consumer_request",
        ),
        sa.CheckConstraint(
            "consumer_module IN ('inventory','planogram','budget')",
            name="ck_field_promotion_receipt_consumer",
        ),
        sa.CheckConstraint(
            "decision IN ('accept','reject')", name="ck_field_promotion_consumer_decision"
        ),
        sa.CheckConstraint(
            "(decision = 'accept' AND destination_candidate_ref_hash ~ '^[0-9a-f]{64}$') OR"
            " (decision = 'reject' AND destination_candidate_ref_hash IS NULL AND"
            " length(trim(coalesce(reason,''))) > 0)",
            name="ck_field_promotion_consumer_receipt_semantics",
        ),
        sa.CheckConstraint(
            "receipt_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_field_promotion_receipt_fingerprint",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_promotion_consumer_receipts"),
        sa.UniqueConstraint(
            "tenant_id", "promotion_id", name="uq_field_promotion_single_consumer_receipt"
        ),
    )

    for table_name in (
        "field_promotion_requests",
        "field_promotion_decisions",
        "field_promotion_consumer_receipts",
    ):
        _tenant_policy(table_name)
        _append_only(table_name)
        op.execute(f"GRANT SELECT, INSERT ON TABLE {table_name} TO {RUNTIME_ROLE}")

    all_scope = '\'{"type":"all"}\'::jsonb'
    field_permissions = _sql_array(FIELD_PROMOTION_PERMISSIONS)
    consumer_permissions = _sql_array(CONSUMER_PROMOTION_PERMISSIONS)

    op.execute(
        "INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) "
        f"SELECT r.tenant_id,r.id,p.permission_key,{all_scope} "
        f"FROM roles r CROSS JOIN unnest({field_permissions}) p(permission_key) "
        "WHERE r.key='field_manager' AND r.is_system IS TRUE "
        "ON CONFLICT (tenant_id,role_id,permission_key) DO UPDATE SET scope=EXCLUDED.scope"
    )
    op.execute(
        "INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) "
        f"SELECT r.tenant_id,r.id,p.permission_key,{all_scope} "
        f"FROM roles r CROSS JOIN unnest({consumer_permissions}) p(permission_key) "
        "WHERE r.key='super_admin' AND r.is_system IS TRUE "
        "ON CONFLICT (tenant_id,role_id,permission_key) DO UPDATE SET scope=EXCLUDED.scope"
    )
    op.execute(
        "INSERT INTO role_permissions (tenant_id,role_id,permission_key,scope) SELECT"
        f" r.tenant_id,r.id,p.permission_key,{all_scope} FROM roles r CROSS JOIN"
        f" unnest({_sql_array(FIELD_PROMOTION_PERMISSIONS + CONSUMER_PROMOTION_PERMISSIONS)})"
        " p(permission_key) WHERE r.key='super_admin' AND r.is_system IS TRUE ON CONFLICT"
        " (tenant_id,role_id,permission_key) DO UPDATE SET scope=EXCLUDED.scope"
    )


def downgrade() -> None:
    permissions = FIELD_PROMOTION_PERMISSIONS + CONSUMER_PROMOTION_PERMISSIONS
    op.execute(
        "DELETE FROM role_permissions rp USING roles r "
        "WHERE rp.tenant_id=r.tenant_id AND rp.role_id=r.id "
        "AND r.key IN ('field_manager','super_admin') AND r.is_system IS TRUE "
        f"AND rp.permission_key=ANY({_sql_array(permissions)})"
    )
    for table_name in (
        "field_promotion_consumer_receipts",
        "field_promotion_decisions",
        "field_promotion_requests",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table_name}_append_only ON {table_name}")
        op.drop_table(table_name)
