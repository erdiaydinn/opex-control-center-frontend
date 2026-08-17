"""Allow Field template versions to enter immutable lifecycle retirement state.

Revision ID: 0026_field_template_retired_status
Revises: 0025_field_governance_operations
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_field_template_retired_status"
down_revision: str = "0025_field_governance_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_field_template_status", "field_templates", type_="check")
    op.create_check_constraint(
        "ck_field_template_status",
        "field_templates",
        "status IN ('draft','active','retired')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE field_templates SET status='draft' WHERE status='retired'"
    )
    op.drop_constraint("ck_field_template_status", "field_templates", type_="check")
    op.create_check_constraint(
        "ck_field_template_status",
        "field_templates",
        "status IN ('draft','active')",
    )
