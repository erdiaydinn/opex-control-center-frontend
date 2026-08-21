-- Workforce V38 / roadmap 16/60: learning from manager overrides.
--
-- Human override evidence may produce immutable learning drafts. Drafts cannot
-- self-promote or auto-modify production optimizer behavior. Approved learning
-- versions require a separate privileged authority and optimizer usage is
-- recorded in append-only receipts.

CREATE TABLE IF NOT EXISTS workforce_manager_overrides (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  optimizer_proposal_fingerprint char(64) NOT NULL,
  decision text NOT NULL,
  reason_code text NOT NULL,
  reason_note text,
  observed_action_type text NOT NULL,
  pre_kpi_context_ref text NOT NULL,
  actor_subject text NOT NULL,
  source_ref text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CHECK (length(trim(location_id)) > 0),
  CHECK (optimizer_proposal_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (decision IN ('accepted','rejected','modified')),
  CHECK (length(trim(reason_code)) > 0),
  CHECK (length(trim(observed_action_type)) > 0),
  CHECK (length(trim(pre_kpi_context_ref)) > 0),
  CHECK (length(trim(actor_subject)) > 0),
  CHECK (length(trim(source_ref)) > 0)
);

CREATE INDEX IF NOT EXISTS workforce_manager_override_location_idx
  ON workforce_manager_overrides(tenant_id, location_id, created_at DESC);
CREATE INDEX IF NOT EXISTS workforce_manager_override_proposal_idx
  ON workforce_manager_overrides(tenant_id, optimizer_proposal_fingerprint);

CREATE TABLE IF NOT EXISTS workforce_override_outcomes (
  tenant_id text NOT NULL,
  id text NOT NULL,
  override_id text NOT NULL,
  worked boolean NOT NULL,
  post_kpi_context_ref text NOT NULL,
  kpi_deltas jsonb NOT NULL,
  source_ref text NOT NULL,
  recorded_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, override_id),
  CHECK (length(trim(override_id)) > 0),
  CHECK (length(trim(post_kpi_context_ref)) > 0),
  CHECK (jsonb_typeof(kpi_deltas) = 'object'),
  CHECK (length(trim(source_ref)) > 0),
  CHECK (length(trim(recorded_by)) > 0)
);

CREATE TABLE IF NOT EXISTS workforce_override_learning_drafts (
  tenant_id text NOT NULL,
  id text NOT NULL,
  model_family text NOT NULL,
  sample_count integer NOT NULL,
  completed_outcome_count integer NOT NULL,
  reason_counts jsonb NOT NULL,
  frequent_override_reasons jsonb NOT NULL,
  action_success_rates jsonb NOT NULL,
  suggested_cost_multipliers jsonb NOT NULL,
  input_fingerprint char(64) NOT NULL,
  draft_fingerprint char(64) NOT NULL,
  automatic_apply_permitted boolean NOT NULL DEFAULT FALSE,
  human_approval_required boolean NOT NULL DEFAULT TRUE,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, draft_fingerprint),
  CHECK (length(trim(model_family)) > 0),
  CHECK (sample_count >= 0),
  CHECK (completed_outcome_count >= 0),
  CHECK (jsonb_typeof(reason_counts) = 'object'),
  CHECK (jsonb_typeof(frequent_override_reasons) = 'array'),
  CHECK (jsonb_typeof(action_success_rates) = 'object'),
  CHECK (jsonb_typeof(suggested_cost_multipliers) = 'object'),
  CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (draft_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (automatic_apply_permitted = FALSE),
  CHECK (human_approval_required = TRUE),
  CHECK (length(trim(created_by)) > 0)
);

CREATE TABLE IF NOT EXISTS workforce_override_learning_versions (
  tenant_id text NOT NULL,
  version text NOT NULL,
  draft_fingerprint char(64) NOT NULL,
  action_cost_multipliers jsonb NOT NULL,
  source_ref text NOT NULL,
  approved_by text NOT NULL,
  effective_from timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'approved',
  authority_fingerprint char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, version),
  UNIQUE (tenant_id, authority_fingerprint),
  CHECK (length(trim(version)) > 0),
  CHECK (draft_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (jsonb_typeof(action_cost_multipliers) = 'object'),
  CHECK (length(trim(source_ref)) > 0),
  CHECK (length(trim(approved_by)) > 0),
  CHECK (status IN ('approved','retired')),
  CHECK (authority_fingerprint ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS workforce_optimizer_learning_receipts (
  tenant_id text NOT NULL,
  id text NOT NULL,
  location_id text NOT NULL,
  optimizer_proposal_fingerprint char(64) NOT NULL,
  learning_version text NOT NULL,
  learning_authority_fingerprint char(64) NOT NULL,
  raw_candidate_pool_fingerprint char(64) NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, optimizer_proposal_fingerprint, learning_version),
  CHECK (length(trim(location_id)) > 0),
  CHECK (optimizer_proposal_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (length(trim(learning_version)) > 0),
  CHECK (learning_authority_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (raw_candidate_pool_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK (length(trim(created_by)) > 0)
);

ALTER TABLE workforce_manager_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_manager_overrides FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_manager_override_tenant ON workforce_manager_overrides;
CREATE POLICY workforce_manager_override_tenant ON workforce_manager_overrides
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_override_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_override_outcomes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_override_outcome_tenant ON workforce_override_outcomes;
CREATE POLICY workforce_override_outcome_tenant ON workforce_override_outcomes
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_override_learning_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_override_learning_drafts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_override_learning_draft_tenant ON workforce_override_learning_drafts;
CREATE POLICY workforce_override_learning_draft_tenant ON workforce_override_learning_drafts
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_override_learning_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_override_learning_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_override_learning_version_tenant ON workforce_override_learning_versions;
CREATE POLICY workforce_override_learning_version_tenant ON workforce_override_learning_versions
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_optimizer_learning_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_optimizer_learning_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_optimizer_learning_receipt_tenant ON workforce_optimizer_learning_receipts;
CREATE POLICY workforce_optimizer_learning_receipt_tenant ON workforce_optimizer_learning_receipts
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

CREATE OR REPLACE FUNCTION workforce_override_learning_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workforce override learning evidence is append-only';
END $$;

DROP TRIGGER IF EXISTS workforce_manager_override_no_mutation ON workforce_manager_overrides;
CREATE TRIGGER workforce_manager_override_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_manager_overrides
  FOR EACH ROW EXECUTE FUNCTION workforce_override_learning_immutable();
DROP TRIGGER IF EXISTS workforce_override_outcome_no_mutation ON workforce_override_outcomes;
CREATE TRIGGER workforce_override_outcome_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_override_outcomes
  FOR EACH ROW EXECUTE FUNCTION workforce_override_learning_immutable();
DROP TRIGGER IF EXISTS workforce_override_learning_draft_no_mutation ON workforce_override_learning_drafts;
CREATE TRIGGER workforce_override_learning_draft_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_override_learning_drafts
  FOR EACH ROW EXECUTE FUNCTION workforce_override_learning_immutable();
DROP TRIGGER IF EXISTS workforce_override_learning_version_no_mutation ON workforce_override_learning_versions;
CREATE TRIGGER workforce_override_learning_version_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_override_learning_versions
  FOR EACH ROW EXECUTE FUNCTION workforce_override_learning_immutable();
DROP TRIGGER IF EXISTS workforce_optimizer_learning_receipt_no_mutation ON workforce_optimizer_learning_receipts;
CREATE TRIGGER workforce_optimizer_learning_receipt_no_mutation
  BEFORE UPDATE OR DELETE ON workforce_optimizer_learning_receipts
  FOR EACH ROW EXECUTE FUNCTION workforce_override_learning_immutable();

INSERT INTO workforce_schema_migrations(version, name)
VALUES (38, 'manager override learning evidence and approved policy versions')
ON CONFLICT (version) DO NOTHING;
