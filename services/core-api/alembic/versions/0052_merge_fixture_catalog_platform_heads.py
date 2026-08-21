"""Merge Planogram Fixture Catalog and cumulative platform migration heads.

Revision ID: 0052_merge_fixture_catalog_platform_heads
Revises: 0046_planogram_fixture_catalog_authority, 0051_workforce_hiring_product_role
Create Date: 2026-08-21

This revision is intentionally schema-neutral. Both parent branches already own
their DDL and must remain independently reversible; this node only restores a
single cumulative Alembic head for exact-head acceptance.
"""

from collections.abc import Sequence

revision: str = "0052_merge_fixture_catalog_platform_heads"
down_revision: tuple[str, str] = (
    "0046_planogram_fixture_catalog_authority",
    "0051_workforce_hiring_product_role",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
