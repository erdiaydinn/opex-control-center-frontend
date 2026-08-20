"""Merge Audit Intelligence and Academy localization migration heads.

Revision ID: 0054_merge_audit_academy_heads
Revises: 0049_academy_localization_governance, 0053_merge_audit_platform_heads
Create Date: 2026-08-20
"""

from collections.abc import Sequence

revision: str = "0054_merge_audit_academy_heads"
down_revision: tuple[str, str] = (
    "0049_academy_localization_governance",
    "0053_merge_audit_platform_heads",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge-only revision; both parent migrations carry the schema changes."""


def downgrade() -> None:
    """Split only the Alembic topology; parent schemas remain unchanged."""
