"""Bind Academy scenarios to immutable content versions.

Revision ID: 0047_academy_scenario_content_binding
Revises: 0046_academy_experience_runtime
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0047_academy_scenario_content_binding"
down_revision: str | None = "0046_academy_experience_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE academy_scenarios "
        "ADD COLUMN content_version_id uuid"
    )
    op.execute(
        """
        ALTER TABLE academy_scenarios
        ADD CONSTRAINT fk_academy_scenario_content_version
        FOREIGN KEY (tenant_id, content_version_id)
        REFERENCES academy_content_versions(tenant_id, id)
        ON DELETE RESTRICT
        """
    )
    op.execute(
        "CREATE INDEX ix_academy_scenario_content_version "
        "ON academy_scenarios(tenant_id, content_version_id, status)"
    )
    # The table is new in the immediately preceding migration, so no production
    # rows should exist on this canonical draft line. Fail closed if that invariant
    # is violated rather than assigning an arbitrary content version.
    op.execute(
        """
        DO $guard$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM academy_scenarios WHERE content_version_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Scenario content binding requires explicit content_version_id for every row';
            END IF;
        END
        $guard$
        """
    )
    op.execute(
        "ALTER TABLE academy_scenarios "
        "ALTER COLUMN content_version_id SET NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE academy_scenarios "
        "DROP CONSTRAINT fk_academy_scenario_content_version"
    )
    op.execute("DROP INDEX IF EXISTS ix_academy_scenario_content_version")
    op.execute(
        "ALTER TABLE academy_scenarios "
        "DROP COLUMN content_version_id"
    )
