"""Merge Audit Intelligence and latest parent migration heads.

Revision ID: 0055_merge_audit_parent_heads
Revises: 0054_merge_audit_academy_heads, 0051_workforce_hiring_product_role
Create Date: 2026-08-20
"""

from collections.abc import Sequence

revision: str = "0055_merge_audit_parent_heads"
down_revision: tuple[str, str] = (
    "0054_merge_audit_academy_heads",
    "0051_workforce_hiring_product_role",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge-only revision; parent revisions carry all schema changes."""


def downgrade() -> None:
    """Split only Alembic topology; parent schemas remain unchanged."""
