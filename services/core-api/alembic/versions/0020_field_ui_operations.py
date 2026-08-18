"""Add Field UI evidence replay identity and notification intent authority.

Revision ID: 0020_field_ui_operations
Revises: 0019_field_intelligence_foundation
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020_field_ui_operations"
down_revision: str = "0019_field_intelligence_foundation"
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


def upgrade() -> None:
    op.add_column(
        "field_evidence",
        sa.Column("client_submission_id", sa.String(length=160), nullable=True),
    )
    op.create_unique_constraint(
        "uq_field_evidence_client_submission",
        "field_evidence",
        ["tenant_id", "mission_id", "location_id", "client_submission_id"],
    )

    op.create_table(
        "field_notification_intents",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mission_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=120), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
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
            name="fk_field_notification_target",
        ),
        sa.CheckConstraint("kind IN ('reminder','escalation')", name="ck_field_notification_kind"),
        sa.CheckConstraint("status = 'queued'", name="ck_field_notification_status"),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_field_notification_intents"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_field_notification_intent_idempotency"
        ),
    )
    op.create_index(
        "ix_field_notification_mission_created",
        "field_notification_intents",
        ["tenant_id", "mission_id", "created_at"],
    )
    _tenant_policy("field_notification_intents")

    # Notification intent is append-only evidence. Dispatch belongs to the shared
    # notification platform; this table must never be mutated into a fake "sent" truth.
    op.execute(
        "CREATE TRIGGER field_notification_intents_append_only "
        "BEFORE UPDATE OR DELETE ON field_notification_intents "
        "FOR EACH ROW EXECUTE FUNCTION prevent_field_evidence_mutation()"
    )

    op.execute("GRANT SELECT, INSERT ON TABLE field_notification_intents TO " + RUNTIME_ROLE)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS field_notification_intents_append_only ON"
        " field_notification_intents"
    )
    op.drop_table("field_notification_intents")
    op.drop_constraint(
        "uq_field_evidence_client_submission",
        "field_evidence",
        type_="unique",
    )
    op.drop_column("field_evidence", "client_submission_id")
