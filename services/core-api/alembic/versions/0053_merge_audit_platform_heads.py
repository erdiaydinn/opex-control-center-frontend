"""Merge Audit vision authority with the rolling platform migration head.

Revision ID: 0053_merge_audit_platform_heads
Revises: 0048_product_role_provisioning, 0052_audit_vision_inference_authority
Create Date: 2026-08-20
"""

from collections.abc import Sequence

revision: str = "0053_merge_audit_platform_heads"
down_revision: tuple[str, str] = (
    "0048_product_role_provisioning",
    "0052_audit_vision_inference_authority",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge-only revision; both parent migrations carry the schema changes."""


def downgrade() -> None:
    """Split only the Alembic topology; parent schemas remain unchanged."""
