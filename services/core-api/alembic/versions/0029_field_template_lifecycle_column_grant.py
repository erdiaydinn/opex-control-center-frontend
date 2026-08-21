"""Narrow Field template runtime mutation to the lifecycle status column only.

Revision ID: 0029_field_template_lifecycle_column_grant
Revises: 0028_field_promotion_consumer_separation
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_field_template_lifecycle_column_grant"
down_revision: str = "0028_field_promotion_consumer_separation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.execute(f"REVOKE UPDATE ON TABLE field_templates FROM {RUNTIME_ROLE}")
    op.execute(f"GRANT UPDATE (status) ON TABLE field_templates TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (status) ON TABLE field_templates FROM {RUNTIME_ROLE}")
    op.execute(f"GRANT UPDATE ON TABLE field_templates TO {RUNTIME_ROLE}")
