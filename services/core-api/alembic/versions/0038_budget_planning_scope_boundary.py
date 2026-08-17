"""Harden Budget planning structural scope at the database boundary.

Revision ID: 0038_budget_planning_scope_boundary
Revises: 0037_budget_planning_authority
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038_budget_planning_scope_boundary"
down_revision: str = "0037_budget_planning_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Budget Plan/Fiscal Period are tenant-only RLS tables. Application routes
    # already require unrestricted cost-center scope for structural planning
    # operations, but the database must fail closed if a future endpoint bypasses
    # that dependency. The canonical runtime DB role is deliberately named in
    # 0014_budget_rls_controls; migrator/DBA maintenance is not reinterpreted as
    # end-user authority by this trigger.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_planning_all_scope_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF current_user = 'opex_runtime'
             AND current_setting('app.budget_cost_center_ids', true) IS DISTINCT FROM '__all__'
          THEN
            RAISE EXCEPTION 'Budget planning structural mutation requires all-cost-center authority';
          END IF;

          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END $$;
        """
    )

    for table, events in (
        ("budget_plan", "INSERT OR UPDATE"),
        ("fiscal_period", "INSERT OR UPDATE OR DELETE"),
        ("budget_line", "INSERT OR UPDATE OR DELETE"),
        ("cost_center", "INSERT OR UPDATE OR DELETE"),
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_budget_00_planning_all_scope_{table}
            BEFORE {events} ON {table}
            FOR EACH ROW EXECUTE FUNCTION budget_planning_all_scope_guard()
            """
        )


def downgrade() -> None:
    for table in ("cost_center", "budget_line", "fiscal_period", "budget_plan"):
        op.execute(
            f"DROP TRIGGER IF EXISTS trg_budget_00_planning_all_scope_{table} ON {table}"
        )
    op.execute("DROP FUNCTION IF EXISTS budget_planning_all_scope_guard()")
