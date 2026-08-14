"""Budget tenant and cost-center row security.

Revision ID: 0014_budget_rls_controls
Revises: 0013_budget_evidence_foundation
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_budget_rls_controls"
down_revision: str | None = "0013_budget_evidence_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
TENANT_ONLY = ("budget_plan", "fiscal_period", "import_batch", "import_row", "budget_command")
SCOPED = (
    ("cost_center", "id"),
    ("budget_line", "cost_center_id"),
    ("purchase_request", "cost_center_id"),
    ("approval", "cost_center_id"),
    ("purchase_order", "cost_center_id"),
    ("invoice", "cost_center_id"),
    ("commitment", "cost_center_id"),
    ("actual", "cost_center_id"),
    ("forecast", "cost_center_id"),
    ("reconciliation_issue", "cost_center_id"),
    ("financial_event", "cost_center_id"),
)
ALL_TABLES = TENANT_ONLY + tuple(table for table, _ in SCOPED)


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_tenant_allows(row_tenant uuid)
        RETURNS boolean LANGUAGE sql STABLE AS $$
          SELECT row_tenant::text = current_setting('app.tenant_id', true)
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_scope_allows(center uuid)
        RETURNS boolean LANGUAGE sql STABLE AS $$
          SELECT current_setting('app.budget_cost_center_ids', true) = '__all__'
             OR center::text = ANY(
                  string_to_array(current_setting('app.budget_cost_center_ids', true), ',')
                )
        $$
        """
    )
    for table in TENANT_ONLY:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            "USING (budget_tenant_allows(tenant_id)) "
            "WITH CHECK (budget_tenant_allows(tenant_id))"
        )
    for table, column in SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_scope_policy ON {table} "
            f"USING (budget_tenant_allows(tenant_id) AND budget_scope_allows({column})) "
            f"WITH CHECK (budget_tenant_allows(tenant_id) AND budget_scope_allows({column}))"
        )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}")
    op.execute("GRANT SELECT,INSERT,UPDATE ON TABLE " + ",".join(ALL_TABLES) + f" TO {RUNTIME_ROLE}")
    op.execute("REVOKE DELETE ON TABLE " + ",".join(ALL_TABLES) + f" FROM {RUNTIME_ROLE}")
    op.execute(f"REVOKE UPDATE ON TABLE approval,actual,financial_event FROM {RUNTIME_ROLE}")


def downgrade() -> None:
    for table, _ in SCOPED:
        op.execute(f"DROP POLICY IF EXISTS {table}_scope_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in TENANT_ONLY:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS budget_scope_allows(uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_tenant_allows(uuid)")
