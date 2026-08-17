"""Grant the runtime role only the UPDATE needed for governed template retirement.

Revision ID: 0027_field_template_lifecycle_runtime_grant
Revises: 0026_field_template_retired_status
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_field_template_lifecycle_runtime_grant"
down_revision: str = "0026_field_template_retired_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    # Field template rows are tenant FORCE-RLS protected. Runtime UPDATE exists
    # solely so the canonical lifecycle route can transition draft/active to
    # retired; callers cannot update tenant identity or bypass route authority.
    op.execute(f"GRANT UPDATE ON TABLE field_templates TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE ON TABLE field_templates FROM {RUNTIME_ROLE}")
