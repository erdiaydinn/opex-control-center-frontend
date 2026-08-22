"""Merge Planogram Fixture Catalog and Audit inference authority heads.

Revision ID: 0060_merge_planogram_audit_heads
Revises: 0052_merge_fixture_catalog_platform_heads, 0059_audit_inference_lease_immutability
Create Date: 2026-08-21

This revision is intentionally schema-neutral. Both parent branches already own
their DDL; this node only restores one cumulative Alembic head after the latest
category-leadership parent composition.
"""

from collections.abc import Sequence

revision: str = "0060_merge_planogram_audit_heads"
down_revision: tuple[str, str] = (
    "0052_merge_fixture_catalog_platform_heads",
    "0059_audit_inference_lease_immutability",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
