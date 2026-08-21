"""Add authoritative Audit location-manager accountability.

Revision ID: 0049_audit_location_accountability
Revises: 0048_audit_assurance_routing
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0049_audit_location_accountability"
down_revision: str = "0048_audit_assurance_routing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.create_table(
        "audit_location_manager_assignments",
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("location_id", sa.String(length=120), nullable=False),
        sa.Column("manager_membership_id", UUID, nullable=False),
        sa.Column("source_ref", sa.String(length=500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["field_locations.tenant_id", "field_locations.location_id"],
            ondelete="CASCADE",
            name="fk_audit_location_manager_location",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manager_membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            ondelete="RESTRICT",
            name="fk_audit_location_manager_membership",
        ),
        sa.CheckConstraint("version > 0", name="ck_audit_location_manager_version"),
        sa.CheckConstraint(
            "length(trim(source_ref)) > 0",
            name="ck_audit_location_manager_source_ref",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "location_id",
            name="pk_audit_location_manager_assignments",
        ),
    )
    op.create_index(
        "ix_audit_location_manager_membership",
        "audit_location_manager_assignments",
        ["tenant_id", "manager_membership_id"],
    )

    op.execute("ALTER TABLE audit_location_manager_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_location_manager_assignments FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY audit_location_manager_assignments_tenant_isolation
        ON audit_location_manager_assignments
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"""
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE audit_location_manager_assignments TO "
        + RUNTIME_ROLE
    )
    op.execute("REVOKE DELETE ON TABLE audit_location_manager_assignments FROM " + RUNTIME_ROLE)


def downgrade() -> None:
    op.drop_table("audit_location_manager_assignments")
