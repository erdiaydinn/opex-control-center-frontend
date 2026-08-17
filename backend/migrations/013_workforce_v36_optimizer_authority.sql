-- Workforce V36 / roadmap 14/60: constraint-aware optimizer proposals.
--
-- Proposals bind an immutable DPI snapshot. They are append-only evidence and
-- can never execute staffing automatically. Human approval is a separate later
-- workflow; this table is not a roster/shift mutation surface.

CREATE TABLE IF NOT EXISTS workforce_optimizer_proposals (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  model_version text NOT NULL,
  dpi_snapshot_fingerprint char(64) NOT NULL,
  dpi_root_cause text NOT NULL,
  dpi_manpower_shortage boolean NOT NULL,
  input_fingerprint char(64) NOT NULL,
  proposal_fingerprint char(64) NOT NULL,
  recommendation_type text NOT NULL,
  selected_candidate_ids jsonb NOT NULL,
  selected_actions jsonb NOT NULL,
  target_gap_man_hours numeric(24,10) NOT NULL,
  covered_gap_man_hours numeric(24,10) NOT NULL,
  remaining_gap_man_hours numeric(24,10) NOT NULL,
  incremental_cost_minor_units bigint NOT NULL,
  feasible boolean NOT NULL,
  automatic_execution_permitted boolean NOT NULL DEFAULT FALSE,
  human_approval_required boolean NOT NULL,
  explanation jsonb NOT NULL,
  candidate_pool_fingerprint char(64) NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, proposal_fingerprint),
  CHECK (length(trim(location_id)) > 0),
  CHECK (length(trim(model_version)) > 0),
  CHECK (dpi_snapshot_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (proposal_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (candidate_pool_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (dpi_root_cause IN (
    'skill_mix_constraint',
    'manpower_capacity_shortage',
    'execution_or_process',
    'no_pressure_signal'
  )),
  CHECK (recommendation_type IN (
    'no_staffing_change',
    'skill_targeted_capacity_proposal',
    'capacity_gap_proposal'
  )),
  CHECK (target_gap_man_hours >= 0),
  CHECK (covered_gap_man_hours >= 0),
  CHECK (remaining_gap_man_hours >= 0),
  CHECK (incremental_cost_minor_units >= 0),
  CHECK (automatic_execution_permitted = FALSE),
  CHECK (jsonb_typeof(selected_candidate_ids) = 'array'),
  CHECK (jsonb_typeof(selected_actions) = 'array'),
  CHECK (jsonb_typeof(explanation) = 'array'),
  CHECK (length(trim(created_by)) > 0)
);

CREATE INDEX IF NOT EXISTS workforce_optimizer_proposal_location_idx
  ON workforce_optimizer_proposals(tenant_id, location_id, created_at DESC);

ALTER TABLE workforce_optimizer_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_optimizer_proposals FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_optimizer_proposal_tenant ON workforce_optimizer_proposals;
CREATE POLICY workforce_optimizer_proposal_tenant ON workforce_optimizer_proposals
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

CREATE OR REPLACE FUNCTION workforce_optimizer_proposal_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workforce optimizer proposals are append-only';
END $$;

DROP TRIGGER IF EXISTS workforce_optimizer_proposal_no_mutation
  ON workforce_optimizer_proposals;
CREATE TRIGGER workforce_optimizer_proposal_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_optimizer_proposals
  FOR EACH ROW EXECUTE FUNCTION workforce_optimizer_proposal_immutable();

INSERT INTO workforce_schema_migrations(version, name)
VALUES (36, 'constraint-aware optimizer proposals')
ON CONFLICT (version) DO NOTHING;
