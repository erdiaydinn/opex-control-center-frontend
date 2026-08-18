"""Master 29: AI recommendations are immutable advice, never accounting truth.
Revision ID: 0038_budget_ai_recommendation_authority
Revises: 0037_budget_planning_authority
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0038_budget_ai_recommendation_authority"
down_revision: str | None = "0037_budget_planning_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
RUNTIME = "opex_runtime"


def upgrade() -> None:
    op.execute("""CREATE TABLE budget_ai_recommendation(
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
      budget_line_id uuid NOT NULL, fiscal_period_id uuid NOT NULL, cost_center_id uuid NOT NULL,
      model_version varchar(160) NOT NULL, input_fingerprint char(64) NOT NULL,
      recommendation jsonb NOT NULL, provenance jsonb NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'PROPOSED', created_by varchar(255) NOT NULL,
      decided_by varchar(255), created_at timestamptz NOT NULL DEFAULT now(), decided_at timestamptz,
      FOREIGN KEY(tenant_id,budget_line_id,fiscal_period_id,cost_center_id) REFERENCES budget_line(tenant_id,id,fiscal_period_id,cost_center_id) ON DELETE RESTRICT,
      CHECK(status IN ('PROPOSED','ACCEPTED','REJECTED')), CHECK(input_fingerprint ~ '^[0-9a-f]{64}$'),
      UNIQUE(tenant_id,budget_line_id,model_version,input_fingerprint), UNIQUE(tenant_id,id))""")
    op.execute("ALTER TABLE budget_ai_recommendation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE budget_ai_recommendation FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY budget_ai_recommendation_scope ON budget_ai_recommendation USING (budget_tenant_allows(tenant_id) AND budget_scope_allows(cost_center_id)) WITH CHECK (budget_tenant_allows(tenant_id) AND budget_scope_allows(cost_center_id))")
    op.execute("""CREATE OR REPLACE FUNCTION budget_ai_recommendation_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='UPDATE' THEN
        IF NEW.recommendation<>OLD.recommendation OR NEW.provenance<>OLD.provenance OR NEW.input_fingerprint<>OLD.input_fingerprint OR NEW.model_version<>OLD.model_version THEN RAISE EXCEPTION 'AI recommendation evidence is immutable'; END IF;
        IF OLD.status<>'PROPOSED' OR NEW.status NOT IN ('ACCEPTED','REJECTED') OR NEW.decided_by IS NULL OR NEW.decided_by=OLD.created_by THEN RAISE EXCEPTION 'independent recommendation decision required'; END IF;
      END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER trg_budget_ai_recommendation_guard BEFORE UPDATE ON budget_ai_recommendation FOR EACH ROW EXECUTE FUNCTION budget_ai_recommendation_guard()")
    op.execute(f"GRANT SELECT,INSERT ON budget_ai_recommendation TO {RUNTIME}")
    op.execute(f"GRANT UPDATE(status,decided_by,decided_at) ON budget_ai_recommendation TO {RUNTIME}")
    op.execute(f"REVOKE DELETE ON budget_ai_recommendation FROM {RUNTIME}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_budget_ai_recommendation_guard ON budget_ai_recommendation")
    op.execute("DROP FUNCTION IF EXISTS budget_ai_recommendation_guard()")
    op.execute("DROP TABLE IF EXISTS budget_ai_recommendation")
