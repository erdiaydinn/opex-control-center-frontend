"""Bind Planogram compliance observations to same-tenant governed Field promotions.

Revision ID: 0034_planogram_compliance_promotion_fk
Revises: 0033_planogram_attestation_preservation
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0034_planogram_compliance_promotion_fk"
down_revision: str = "0033_planogram_attestation_preservation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_planogram_compliance_field_promotion",
        "planogram_compliance_observations",
        "field_promotion_requests",
        ["tenant_id", "field_promotion_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_planogram_compliance_field_promotion",
        "planogram_compliance_observations",
        type_="foreignkey",
    )
