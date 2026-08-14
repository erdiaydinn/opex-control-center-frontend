"""Merge Jarvis query authority with cumulative platform migrations.

Revision ID: 0017_merge_jarvis_platform_heads
Revises: 0010_ai_tenant_query_context, 0016_academy_audit_idempotency
Create Date: 2026-08-14
"""

from collections.abc import Sequence

revision: str = "0017_merge_jarvis_platform_heads"
down_revision: tuple[str, str] = (
    "0010_ai_tenant_query_context",
    "0016_academy_audit_idempotency",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge-only revision; both parent migrations carry the schema changes."""


def downgrade() -> None:
    """Split only the Alembic topology; parent schemas remain unchanged."""
