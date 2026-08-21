"""Master 28 hardening: global planning scope and published scenario immutability.

Revision ID: 0040_budget_planning_hardening
Revises: 0039_budget_finance_controls
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0040_budget_planning_hardening"
down_revision: str | None = "0039_budget_finance_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
RUNTIME = "opex_runtime"


def upgrade() -> None:
    for table in ("budget_plan_snapshot", "budget_scenario", "budget_scenario_assumption"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f"CREATE POLICY {table}_global_planning_scope ON {table} USING (budget_tenant_allows(tenant_id) AND current_setting('app.budget_cost_center_ids',true)='__all__') WITH CHECK (budget_tenant_allows(tenant_id) AND current_setting('app.budget_cost_center_ids',true)='__all__')")
    op.execute("DROP POLICY IF EXISTS budget_allocation_rule_scope_policy ON budget_allocation_rule")
    op.execute("CREATE POLICY budget_allocation_rule_global_scope ON budget_allocation_rule USING (budget_tenant_allows(tenant_id) AND current_setting('app.budget_cost_center_ids',true)='__all__') WITH CHECK (budget_tenant_allows(tenant_id) AND current_setting('app.budget_cost_center_ids',true)='__all__')")
    op.execute("""
    CREATE OR REPLACE FUNCTION budget_scenario_publish_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE doc jsonb;
    BEGIN
      IF OLD.status IN ('PUBLISHED','RETIRED') THEN
        IF NEW.tenant_id<>OLD.tenant_id OR NEW.plan_id<>OLD.plan_id OR NEW.parent_scenario_id IS DISTINCT FROM OLD.parent_scenario_id OR NEW.name<>OLD.name OR NEW.scenario_type<>OLD.scenario_type OR NEW.version<>OLD.version OR NEW.as_of<>OLD.as_of OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at OR NEW.fingerprint_sha256 IS DISTINCT FROM OLD.fingerprint_sha256 THEN
          RAISE EXCEPTION 'published scenario root is immutable';
        END IF;
      END IF;
      IF OLD.status='DRAFT' AND NEW.status='PUBLISHED' THEN
        IF NEW.published_by IS NULL OR NEW.published_by=OLD.created_by THEN RAISE EXCEPTION 'independent scenario publisher required'; END IF;
        doc:=jsonb_build_object('scenario',jsonb_build_object('id',OLD.id,'plan',OLD.plan_id,'type',OLD.scenario_type,'version',OLD.version,'as_of',OLD.as_of),
          'assumptions',COALESCE((SELECT jsonb_agg(jsonb_build_object('key',a.assumption_key,'value',a.assumption_value,'unit',a.unit,'source',a.source) ORDER BY a.assumption_key,a.id) FROM budget_scenario_assumption a WHERE a.tenant_id=OLD.tenant_id AND a.scenario_id=OLD.id),'[]'::jsonb),
          'lines',COALESCE((SELECT jsonb_agg(jsonb_build_object('line',l.budget_line_id,'period',l.fiscal_period_id,'center',l.cost_center_id,'driver',l.driver_key,'quantity',l.quantity,'rate',l.rate,'amount',l.calculated_base_amount,'provenance',l.provenance) ORDER BY l.fiscal_period_id,l.cost_center_id,l.driver_key,l.id) FROM budget_scenario_line l WHERE l.tenant_id=OLD.tenant_id AND l.scenario_id=OLD.id),'[]'::jsonb),
          'allocations',COALESCE((SELECT jsonb_agg(jsonb_build_object('source',r.source_budget_line_id,'target',r.target_budget_line_id,'period',r.target_fiscal_period_id,'center',r.target_cost_center_id,'weight',r.weight,'basis',r.basis) ORDER BY r.source_budget_line_id,r.target_budget_line_id,r.id) FROM budget_allocation_rule r WHERE r.tenant_id=OLD.tenant_id AND r.scenario_id=OLD.id),'[]'::jsonb));
        NEW.fingerprint_sha256:=encode(digest(convert_to(doc::text,'UTF8'),'sha256'),'hex'); NEW.published_at:=COALESCE(NEW.published_at,now());
      ELSIF OLD.status<>NEW.status AND NOT(OLD.status='PUBLISHED' AND NEW.status='RETIRED') THEN
        RAISE EXCEPTION 'invalid scenario lifecycle';
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute(f"REVOKE UPDATE ON budget_scenario FROM {RUNTIME}")
    op.execute(f"GRANT UPDATE(status,published_by,published_at) ON budget_scenario TO {RUNTIME}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE ON budget_scenario FROM {RUNTIME}")
    op.execute(f"GRANT UPDATE ON budget_scenario TO {RUNTIME}")
    op.execute("DROP POLICY IF EXISTS budget_allocation_rule_global_scope ON budget_allocation_rule")
    op.execute("CREATE POLICY budget_allocation_rule_scope_policy ON budget_allocation_rule USING (budget_tenant_allows(tenant_id) AND budget_scope_allows(target_cost_center_id)) WITH CHECK (budget_tenant_allows(tenant_id) AND budget_scope_allows(target_cost_center_id))")
    for table in ("budget_plan_snapshot", "budget_scenario", "budget_scenario_assumption"):
        op.execute(f"DROP POLICY IF EXISTS {table}_global_planning_scope ON {table}")
        op.execute(f"CREATE POLICY {table}_tenant_policy ON {table} USING (budget_tenant_allows(tenant_id)) WITH CHECK (budget_tenant_allows(tenant_id))")
