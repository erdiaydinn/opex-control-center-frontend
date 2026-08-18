"""Master Roadmap 28: Budget planning authority.

Revision ID: 0037_budget_planning_authority
Revises: 0036_planogram_product_roles
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0037_budget_planning_authority"
down_revision: str | None = "0036_planogram_product_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.execute("ALTER TABLE budget_plan ADD COLUMN activation_snapshot_sha256 char(64)")
    op.execute("""
    CREATE TABLE budget_plan_snapshot(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
      plan_id uuid NOT NULL, snapshot_sha256 char(64) NOT NULL, payload jsonb NOT NULL,
      activated_by varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,plan_id) REFERENCES budget_plan(tenant_id,id) ON DELETE RESTRICT,
      UNIQUE(tenant_id,plan_id), UNIQUE(tenant_id,id),
      CHECK(snapshot_sha256 ~ '^[0-9a-f]{64}$'))
    """)
    op.execute("""
    ALTER TABLE forecast ADD CONSTRAINT fk_budget_forecast_exact_scope
      FOREIGN KEY(tenant_id,budget_line_id,fiscal_period_id,cost_center_id)
      REFERENCES budget_line(tenant_id,id,fiscal_period_id,cost_center_id) ON DELETE RESTRICT
    """)
    op.execute("""
    CREATE TABLE budget_scenario(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
      plan_id uuid NOT NULL, parent_scenario_id uuid, name varchar(200) NOT NULL,
      scenario_type varchar(30) NOT NULL, version integer NOT NULL DEFAULT 1,
      as_of date NOT NULL, status varchar(20) NOT NULL DEFAULT 'DRAFT',
      fingerprint_sha256 char(64), created_by varchar(255) NOT NULL,
      published_by varchar(255), created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz,
      FOREIGN KEY(tenant_id,plan_id) REFERENCES budget_plan(tenant_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(tenant_id,parent_scenario_id) REFERENCES budget_scenario(tenant_id,id) ON DELETE RESTRICT,
      CHECK(scenario_type IN ('DRIVER_PLAN','ROLLING_FORECAST','WHAT_IF')),
      CHECK(status IN ('DRAFT','PUBLISHED','RETIRED')), CHECK(version>0),
      CHECK(fingerprint_sha256 IS NULL OR fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
      UNIQUE(tenant_id,id), UNIQUE(tenant_id,plan_id,name,version))
    """)
    op.execute("""
    CREATE TABLE budget_scenario_assumption(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, scenario_id uuid NOT NULL,
      assumption_key varchar(160) NOT NULL, assumption_value jsonb NOT NULL, unit varchar(40),
      source varchar(255) NOT NULL, effective_on date, created_by varchar(255) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,scenario_id) REFERENCES budget_scenario(tenant_id,id) ON DELETE CASCADE,
      UNIQUE(tenant_id,scenario_id,assumption_key), UNIQUE(tenant_id,id))
    """)
    op.execute("""
    CREATE TABLE budget_scenario_line(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, scenario_id uuid NOT NULL,
      budget_line_id uuid NOT NULL, fiscal_period_id uuid NOT NULL, cost_center_id uuid NOT NULL,
      driver_key varchar(160) NOT NULL, quantity numeric(18,4) NOT NULL, rate numeric(18,4) NOT NULL,
      calculated_base_amount numeric(18,2) NOT NULL, unit varchar(40), formula varchar(500) NOT NULL DEFAULT 'quantity * rate',
      provenance jsonb NOT NULL DEFAULT '{}'::jsonb, created_by varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,scenario_id) REFERENCES budget_scenario(tenant_id,id) ON DELETE CASCADE,
      FOREIGN KEY(tenant_id,budget_line_id,fiscal_period_id,cost_center_id)
        REFERENCES budget_line(tenant_id,id,fiscal_period_id,cost_center_id) ON DELETE RESTRICT,
      CHECK(quantity>=0), CHECK(rate>=0), CHECK(calculated_base_amount>=0),
      UNIQUE(tenant_id,scenario_id,budget_line_id,driver_key), UNIQUE(tenant_id,id))
    """)
    op.execute("""
    CREATE TABLE budget_allocation_rule(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, scenario_id uuid NOT NULL,
      source_budget_line_id uuid NOT NULL, target_budget_line_id uuid NOT NULL,
      target_fiscal_period_id uuid NOT NULL, target_cost_center_id uuid NOT NULL,
      weight numeric(9,6) NOT NULL, basis varchar(160) NOT NULL,
      provenance jsonb NOT NULL DEFAULT '{}'::jsonb, created_by varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(tenant_id,scenario_id) REFERENCES budget_scenario(tenant_id,id) ON DELETE CASCADE,
      FOREIGN KEY(tenant_id,source_budget_line_id) REFERENCES budget_line(tenant_id,id) ON DELETE RESTRICT,
      FOREIGN KEY(tenant_id,target_budget_line_id,target_fiscal_period_id,target_cost_center_id)
        REFERENCES budget_line(tenant_id,id,fiscal_period_id,cost_center_id) ON DELETE RESTRICT,
      CHECK(weight>0 AND weight<=1), UNIQUE(tenant_id,id))
    """)
    op.execute("""
    CREATE OR REPLACE FUNCTION budget_capture_activation_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE doc jsonb; fp text;
    BEGIN
      IF OLD.status='DRAFT' AND NEW.status='ACTIVE' THEN
        IF NEW.activated_by IS NULL OR NEW.activated_by=OLD.created_by THEN RAISE EXCEPTION 'independent activation actor required'; END IF;
        doc:=jsonb_build_object(
          'plan',jsonb_build_object('id',OLD.id,'name',OLD.name,'fiscal_year',OLD.fiscal_year,'base_currency',OLD.base_currency),
          'periods',COALESCE((SELECT jsonb_agg(jsonb_build_object('id',p.id,'code',p.code,'starts_on',p.starts_on,'ends_on',p.ends_on) ORDER BY p.code,p.id) FROM fiscal_period p WHERE p.tenant_id=OLD.tenant_id AND p.plan_id=OLD.id),'[]'::jsonb),
          'lines',COALESCE((SELECT jsonb_agg(jsonb_build_object('id',l.id,'period',l.fiscal_period_id,'center',l.cost_center_id,'category',l.category,'amount',l.budget_base_amount) ORDER BY l.fiscal_period_id,l.cost_center_id,l.category,l.id) FROM budget_line l WHERE l.tenant_id=OLD.tenant_id AND l.plan_id=OLD.id),'[]'::jsonb));
        fp:=encode(digest(convert_to(doc::text,'UTF8'),'sha256'),'hex'); NEW.activation_snapshot_sha256:=fp;
        INSERT INTO budget_plan_snapshot(tenant_id,plan_id,snapshot_sha256,payload,activated_by) VALUES(OLD.tenant_id,OLD.id,fp,doc,NEW.activated_by);
      END IF; RETURN NEW;
    END $$
    """)
    op.execute("CREATE TRIGGER trg_budget_capture_activation BEFORE UPDATE ON budget_plan FOR EACH ROW EXECUTE FUNCTION budget_capture_activation_snapshot()")
    op.execute("""
    CREATE OR REPLACE FUNCTION budget_active_content_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE pid uuid; tid uuid; st varchar(20);
    BEGIN
      pid:=CASE WHEN TG_OP='DELETE' THEN OLD.plan_id ELSE NEW.plan_id END; tid:=CASE WHEN TG_OP='DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END;
      SELECT status INTO st FROM budget_plan WHERE tenant_id=tid AND id=pid;
      IF st='ACTIVE' THEN
        IF TG_TABLE_NAME='fiscal_period' AND TG_OP='UPDATE' AND OLD.status='OPEN' AND NEW.status='CLOSED'
           AND NEW.plan_id=OLD.plan_id AND NEW.code=OLD.code AND NEW.starts_on=OLD.starts_on AND NEW.ends_on=OLD.ends_on THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'active budget planning content is immutable';
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
    END $$
    """)
    op.execute("CREATE TRIGGER trg_budget_line_active_guard BEFORE INSERT OR UPDATE OR DELETE ON budget_line FOR EACH ROW EXECUTE FUNCTION budget_active_content_guard()")
    op.execute("CREATE TRIGGER trg_fiscal_period_active_guard BEFORE INSERT OR UPDATE OR DELETE ON fiscal_period FOR EACH ROW EXECUTE FUNCTION budget_active_content_guard()")
    op.execute("""
    CREATE OR REPLACE FUNCTION budget_scenario_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE st varchar(20); tid uuid; sid uuid;
    BEGIN tid:=CASE WHEN TG_OP='DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END; sid:=CASE WHEN TG_OP='DELETE' THEN OLD.scenario_id ELSE NEW.scenario_id END;
      SELECT status INTO st FROM budget_scenario WHERE tenant_id=tid AND id=sid; IF st<>'DRAFT' THEN RAISE EXCEPTION 'published scenario content is immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$
    """)
    for table in ('budget_scenario_assumption','budget_scenario_line','budget_allocation_rule'):
        op.execute(f"CREATE TRIGGER trg_{table}_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION budget_scenario_child_guard()")
    op.execute("""
    CREATE OR REPLACE FUNCTION budget_scenario_publish_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE doc jsonb;
    BEGIN
      IF OLD.status='DRAFT' AND NEW.status='PUBLISHED' THEN
        IF NEW.published_by IS NULL OR NEW.published_by=OLD.created_by THEN RAISE EXCEPTION 'independent scenario publisher required'; END IF;
        doc:=jsonb_build_object('scenario',jsonb_build_object('id',OLD.id,'plan',OLD.plan_id,'type',OLD.scenario_type,'version',OLD.version,'as_of',OLD.as_of),
          'assumptions',COALESCE((SELECT jsonb_agg(jsonb_build_object('key',a.assumption_key,'value',a.assumption_value,'unit',a.unit,'source',a.source) ORDER BY a.assumption_key,a.id) FROM budget_scenario_assumption a WHERE a.tenant_id=OLD.tenant_id AND a.scenario_id=OLD.id),'[]'::jsonb),
          'lines',COALESCE((SELECT jsonb_agg(jsonb_build_object('line',l.budget_line_id,'period',l.fiscal_period_id,'center',l.cost_center_id,'driver',l.driver_key,'quantity',l.quantity,'rate',l.rate,'amount',l.calculated_base_amount,'provenance',l.provenance) ORDER BY l.fiscal_period_id,l.cost_center_id,l.driver_key,l.id) FROM budget_scenario_line l WHERE l.tenant_id=OLD.tenant_id AND l.scenario_id=OLD.id),'[]'::jsonb),
          'allocations',COALESCE((SELECT jsonb_agg(jsonb_build_object('source',r.source_budget_line_id,'target',r.target_budget_line_id,'period',r.target_fiscal_period_id,'center',r.target_cost_center_id,'weight',r.weight,'basis',r.basis) ORDER BY r.source_budget_line_id,r.target_budget_line_id,r.id) FROM budget_allocation_rule r WHERE r.tenant_id=OLD.tenant_id AND r.scenario_id=OLD.id),'[]'::jsonb));
        NEW.fingerprint_sha256:=encode(digest(convert_to(doc::text,'UTF8'),'sha256'),'hex'); NEW.published_at:=COALESCE(NEW.published_at,now());
      ELSIF OLD.status<>NEW.status AND NOT(OLD.status='PUBLISHED' AND NEW.status='RETIRED') THEN RAISE EXCEPTION 'invalid scenario lifecycle'; END IF; RETURN NEW; END $$
    """)
    op.execute("CREATE TRIGGER trg_budget_scenario_publish BEFORE UPDATE ON budget_scenario FOR EACH ROW EXECUTE FUNCTION budget_scenario_publish_guard()")
    for table in ('budget_plan_snapshot','budget_scenario','budget_scenario_assumption'):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_policy ON {table} USING (budget_tenant_allows(tenant_id)) WITH CHECK (budget_tenant_allows(tenant_id))")
    for table,column in (('budget_scenario_line','cost_center_id'),('budget_allocation_rule','target_cost_center_id')):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_scope_policy ON {table} USING (budget_tenant_allows(tenant_id) AND budget_scope_allows({column})) WITH CHECK (budget_tenant_allows(tenant_id) AND budget_scope_allows({column}))")
    op.execute(f"GRANT SELECT ON budget_plan_snapshot TO {RUNTIME_ROLE}")
    op.execute(f"REVOKE INSERT,UPDATE,DELETE ON budget_plan_snapshot FROM {RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT,INSERT,UPDATE ON budget_scenario,budget_scenario_assumption,budget_scenario_line,budget_allocation_rule TO {RUNTIME_ROLE}")
    op.execute(f"REVOKE DELETE ON budget_scenario,budget_scenario_assumption,budget_scenario_line,budget_allocation_rule FROM {RUNTIME_ROLE}")
    op.execute(f"REVOKE UPDATE ON budget_line,fiscal_period,budget_plan FROM {RUNTIME_ROLE}")
    op.execute(f"GRANT UPDATE(status,closed_by,closed_at) ON fiscal_period TO {RUNTIME_ROLE}")
    op.execute(f"GRANT UPDATE(status,activated_by,activated_at) ON budget_plan TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_budget_scenario_publish ON budget_scenario")
    op.execute("DROP FUNCTION IF EXISTS budget_scenario_publish_guard()")
    for table in ('budget_scenario_assumption','budget_scenario_line','budget_allocation_rule'):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_guard ON {table}")
    op.execute("DROP FUNCTION IF EXISTS budget_scenario_child_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_fiscal_period_active_guard ON fiscal_period")
    op.execute("DROP TRIGGER IF EXISTS trg_budget_line_active_guard ON budget_line")
    op.execute("DROP FUNCTION IF EXISTS budget_active_content_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_budget_capture_activation ON budget_plan")
    op.execute("DROP FUNCTION IF EXISTS budget_capture_activation_snapshot()")
    op.execute("ALTER TABLE forecast DROP CONSTRAINT IF EXISTS fk_budget_forecast_exact_scope")
    op.execute("DROP TABLE IF EXISTS budget_allocation_rule")
    op.execute("DROP TABLE IF EXISTS budget_scenario_line")
    op.execute("DROP TABLE IF EXISTS budget_scenario_assumption")
    op.execute("DROP TABLE IF EXISTS budget_scenario")
    op.execute("DROP TABLE IF EXISTS budget_plan_snapshot")
    op.execute("ALTER TABLE budget_plan DROP COLUMN IF EXISTS activation_snapshot_sha256")
