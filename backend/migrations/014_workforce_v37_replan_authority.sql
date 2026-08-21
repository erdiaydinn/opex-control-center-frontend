-- Workforce V37 / roadmap 15/60: intraday replan + what-if simulator.
--
-- Scenario assumptions are approved/versioned tenant authority. Browser callers
-- may submit hypothetical shocks, but cannot author KPI sensitivities, cost
-- coefficients, current demand/capacity/DPI truth, or an executable plan.

CREATE TABLE IF NOT EXISTS workforce_replan_model_versions (
  tenant_id text NOT NULL,
  model_version text NOT NULL,
  kpi_sensitivities jsonb NOT NULL,
  incremental_cost_minor_units_per_man_hour numeric(24,10) NOT NULL,
  source_ref text NOT NULL,
  approved_by text NOT NULL,
  effective_from timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'approved',
  authority_fingerprint char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, model_version),
  UNIQUE (tenant_id, authority_fingerprint),
  CHECK (length(trim(model_version)) > 0),
  CHECK (jsonb_typeof(kpi_sensitivities) = 'array'),
  CHECK (incremental_cost_minor_units_per_man_hour >= 0),
  CHECK (length(trim(source_ref)) > 0),
  CHECK (length(trim(approved_by)) > 0),
  CHECK (status IN ('approved','retired')),
  CHECK (authority_fingerprint ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS workforce_replan_scenarios (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  model_version text NOT NULL,
  input_fingerprint char(64) NOT NULL,
  scenario_fingerprint char(64) NOT NULL,
  baseline_demand_snapshot_fingerprint char(64) NOT NULL,
  baseline_capacity_snapshot_fingerprint char(64) NOT NULL,
  baseline_dpi_snapshot_fingerprint char(64) NOT NULL,
  baseline_optimizer_proposal_fingerprint char(64) NOT NULL,
  baseline_required_man_hours numeric(24,10) NOT NULL,
  baseline_effective_man_hours numeric(24,10) NOT NULL,
  scenario_required_man_hours numeric(24,10) NOT NULL,
  scenario_effective_man_hours numeric(24,10) NOT NULL,
  baseline_gap_man_hours numeric(24,10) NOT NULL,
  scenario_gap_man_hours numeric(24,10) NOT NULL,
  gap_delta_man_hours numeric(24,10) NOT NULL,
  baseline_dpi numeric(24,10) NOT NULL,
  scenario_dpi numeric(24,10) NOT NULL,
  dpi_delta numeric(24,10) NOT NULL,
  predicted_kpi_deltas jsonb NOT NULL,
  estimated_scenario_cost_minor_units bigint NOT NULL,
  cost_delta_minor_units bigint NOT NULL,
  shocks jsonb NOT NULL,
  assumptions jsonb NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, scenario_fingerprint),
  CHECK (length(trim(location_id)) > 0),
  CHECK (length(trim(model_version)) > 0),
  CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (scenario_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (baseline_demand_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (baseline_capacity_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (baseline_dpi_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (baseline_optimizer_proposal_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (baseline_required_man_hours >= 0),
  CHECK (baseline_effective_man_hours >= 0),
  CHECK (scenario_required_man_hours >= 0),
  CHECK (scenario_effective_man_hours >= 0),
  CHECK (baseline_gap_man_hours >= 0),
  CHECK (scenario_gap_man_hours >= 0),
  CHECK (jsonb_typeof(predicted_kpi_deltas) = 'object'),
  CHECK (estimated_scenario_cost_minor_units >= 0),
  CHECK (jsonb_typeof(shocks) = 'array'),
  CHECK (jsonb_typeof(assumptions) = 'object'),
  CHECK (length(trim(created_by)) > 0)
);

CREATE TABLE IF NOT EXISTS workforce_replan_proposals (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  scenario_fingerprint char(64) NOT NULL,
  recommendation text NOT NULL,
  replan_required boolean NOT NULL,
  automatic_apply_permitted boolean NOT NULL DEFAULT FALSE,
  human_approval_required boolean NOT NULL,
  proposal_fingerprint char(64) NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, proposal_fingerprint),
  UNIQUE (tenant_id, scenario_fingerprint),
  CHECK (length(trim(location_id)) > 0),
  CHECK (scenario_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (length(trim(recommendation)) > 0),
  CHECK (automatic_apply_permitted = FALSE),
  CHECK (proposal_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (length(trim(created_by)) > 0)
);

CREATE INDEX IF NOT EXISTS workforce_replan_scenario_location_idx
  ON workforce_replan_scenarios(tenant_id, location_id, created_at DESC);
CREATE INDEX IF NOT EXISTS workforce_replan_proposal_location_idx
  ON workforce_replan_proposals(tenant_id, location_id, created_at DESC);

ALTER TABLE workforce_replan_model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_replan_model_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_replan_model_tenant ON workforce_replan_model_versions;
CREATE POLICY workforce_replan_model_tenant ON workforce_replan_model_versions
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_replan_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_replan_scenarios FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_replan_scenario_tenant ON workforce_replan_scenarios;
CREATE POLICY workforce_replan_scenario_tenant ON workforce_replan_scenarios
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_replan_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_replan_proposals FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_replan_proposal_tenant ON workforce_replan_proposals;
CREATE POLICY workforce_replan_proposal_tenant ON workforce_replan_proposals
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

CREATE OR REPLACE FUNCTION workforce_replan_authority_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workforce replan authority is append-only';
END $$;

DROP TRIGGER IF EXISTS workforce_replan_model_no_mutation ON workforce_replan_model_versions;
CREATE TRIGGER workforce_replan_model_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_replan_model_versions
  FOR EACH ROW EXECUTE FUNCTION workforce_replan_authority_immutable();
DROP TRIGGER IF EXISTS workforce_replan_scenario_no_mutation ON workforce_replan_scenarios;
CREATE TRIGGER workforce_replan_scenario_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_replan_scenarios
  FOR EACH ROW EXECUTE FUNCTION workforce_replan_authority_immutable();
DROP TRIGGER IF EXISTS workforce_replan_proposal_no_mutation ON workforce_replan_proposals;
CREATE TRIGGER workforce_replan_proposal_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_replan_proposals
  FOR EACH ROW EXECUTE FUNCTION workforce_replan_authority_immutable();

INSERT INTO workforce_schema_migrations(version, name)
VALUES (37, 'intraday replan scenarios and non-executing proposals')
ON CONFLICT (version) DO NOTHING;
