-- Workforce/Hiring V44: governed recruitment orchestration.
-- Adds versioned pipelines, append-only stage/scorecard/offer history,
-- one-time candidate offer decision capabilities, and cross-department
-- onboarding task authority. All rows are tenant scoped and FORCE RLS.

CREATE TABLE IF NOT EXISTS recruitment.pipeline_templates (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  template_id uuid NOT NULL,
  template_key text NOT NULL CHECK (btrim(template_key) <> ''),
  version integer NOT NULL CHECK (version > 0),
  name text NOT NULL CHECK (btrim(name) <> ''),
  stages jsonb NOT NULL CHECK (jsonb_typeof(stages) = 'array' AND jsonb_array_length(stages) >= 2),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  PRIMARY KEY (tenant_id, template_id),
  UNIQUE (tenant_id, template_key, version)
);

CREATE TABLE IF NOT EXISTS recruitment.pipeline_assignments (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  template_id uuid NOT NULL,
  current_stage text NOT NULL CHECK (btrim(current_stage) <> ''),
  stage_entered_at timestamptz NOT NULL,
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  assigned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  assigned_by text NOT NULL CHECK (btrim(assigned_by) <> ''),
  PRIMARY KEY (tenant_id, request_id, candidate_id),
  FOREIGN KEY (tenant_id, template_id)
    REFERENCES recruitment.pipeline_templates(tenant_id, template_id)
);

CREATE TABLE IF NOT EXISTS recruitment.pipeline_stage_events (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  event_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  template_id uuid NOT NULL,
  from_stage text,
  to_stage text NOT NULL CHECK (btrim(to_stage) <> ''),
  reason text NOT NULL DEFAULT '',
  actor text NOT NULL CHECK (btrim(actor) <> ''),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  prior_stage_entered_at timestamptz,
  elapsed_seconds bigint CHECK (elapsed_seconds IS NULL OR elapsed_seconds >= 0),
  sla_seconds bigint CHECK (sla_seconds IS NULL OR sla_seconds >= 0),
  sla_breached boolean NOT NULL DEFAULT false,
  PRIMARY KEY (tenant_id, event_id)
);
CREATE INDEX IF NOT EXISTS pipeline_stage_event_subject_idx
  ON recruitment.pipeline_stage_events(tenant_id, request_id, candidate_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS recruitment.interview_scorecards (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  scorecard_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  stage text NOT NULL CHECK (btrim(stage) <> ''),
  interviewer_id text NOT NULL CHECK (btrim(interviewer_id) <> ''),
  competencies jsonb NOT NULL CHECK (jsonb_typeof(competencies) = 'object'),
  overall_score numeric(5,2) NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
  recommendation text NOT NULL CHECK (recommendation IN ('STRONG_HIRE','HIRE','HOLD','NO_HIRE','STRONG_NO_HIRE')),
  conflict_declared boolean NOT NULL,
  submitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, scorecard_id),
  UNIQUE (tenant_id, request_id, candidate_id, stage, interviewer_id)
);

CREATE TABLE IF NOT EXISTS recruitment.offer_packages (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  offer_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  version integer NOT NULL CHECK (version > 0),
  package_sha256 bytea NOT NULL CHECK (octet_length(package_sha256) = 32),
  package jsonb NOT NULL CHECK (jsonb_typeof(package) = 'object'),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  PRIMARY KEY (tenant_id, offer_id),
  UNIQUE (tenant_id, request_id, candidate_id, version)
);

CREATE TABLE IF NOT EXISTS recruitment.offer_decision_capabilities (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  capability_id uuid NOT NULL,
  offer_id uuid NOT NULL,
  token_sha256 bytea NOT NULL CHECK (octet_length(token_sha256) = 32),
  expires_at timestamptz NOT NULL,
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  issued_by text NOT NULL CHECK (btrim(issued_by) <> ''),
  consumed_at timestamptz,
  consumed_decision text CHECK (consumed_decision IS NULL OR consumed_decision IN ('ACCEPTED','DECLINED')),
  PRIMARY KEY (tenant_id, capability_id),
  UNIQUE (tenant_id, token_sha256),
  FOREIGN KEY (tenant_id, offer_id)
    REFERENCES recruitment.offer_packages(tenant_id, offer_id)
);
CREATE INDEX IF NOT EXISTS offer_decision_capability_expiry_idx
  ON recruitment.offer_decision_capabilities(tenant_id, expires_at)
  WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS recruitment.offer_events (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  event_id uuid NOT NULL,
  offer_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  decision text NOT NULL CHECK (decision IN ('ISSUED','ACCEPTED','DECLINED','WITHDRAWN','EXPIRED')),
  actor_type text NOT NULL CHECK (actor_type IN ('HR','CANDIDATE_CAPABILITY','SYSTEM')),
  actor_ref text NOT NULL CHECK (btrim(actor_ref) <> ''),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  PRIMARY KEY (tenant_id, event_id)
);
CREATE INDEX IF NOT EXISTS offer_event_offer_idx
  ON recruitment.offer_events(tenant_id, offer_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS recruitment.onboarding_tasks (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  task_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  offer_id uuid NOT NULL,
  task_key text NOT NULL CHECK (btrim(task_key) <> ''),
  title text NOT NULL CHECK (btrim(title) <> ''),
  owner_role text NOT NULL CHECK (btrim(owner_role) <> ''),
  required boolean NOT NULL DEFAULT true,
  due_at timestamptz,
  dependencies jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(dependencies) = 'array'),
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','IN_PROGRESS','BLOCKED','COMPLETED','WAIVED')),
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  completed_at timestamptz,
  completed_by text,
  completion_note text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, task_id),
  UNIQUE (tenant_id, request_id, candidate_id, offer_id, task_key)
);
CREATE INDEX IF NOT EXISTS onboarding_task_candidate_idx
  ON recruitment.onboarding_tasks(tenant_id, request_id, candidate_id, status, due_at);

CREATE TABLE IF NOT EXISTS recruitment.candidate_notes (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  note_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  note_type text NOT NULL CHECK (note_type IN ('INTERVIEW','PROCESS','RISK','FOLLOW_UP')),
  visibility text NOT NULL CHECK (visibility IN ('RECRUITMENT_TEAM','HR_ONLY')),
  body text NOT NULL CHECK (btrim(body) <> '' AND length(body) <= 4000),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  PRIMARY KEY (tenant_id, note_id)
);

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'pipeline_templates','pipeline_assignments','pipeline_stage_events',
    'interview_scorecards','offer_packages','offer_decision_capabilities',
    'offer_events','onboarding_tasks','candidate_notes'
  ] LOOP
    EXECUTE format('ALTER TABLE recruitment.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE recruitment.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON recruitment.%I', table_name || '_tenant_policy', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON recruitment.%I USING (tenant_id = public.workforce_current_tenant()) WITH CHECK (tenant_id = public.workforce_current_tenant())',
      table_name || '_tenant_policy', table_name
    );
    EXECUTE format('REVOKE ALL ON TABLE recruitment.%I FROM PUBLIC', table_name);
  END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.reject_orchestration_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='recruitment orchestration record is append-only';
END;
$$;

DROP TRIGGER IF EXISTS pipeline_template_no_mutation ON recruitment.pipeline_templates;
CREATE TRIGGER pipeline_template_no_mutation BEFORE UPDATE OR DELETE ON recruitment.pipeline_templates
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_orchestration_immutable();
DROP TRIGGER IF EXISTS pipeline_stage_event_no_mutation ON recruitment.pipeline_stage_events;
CREATE TRIGGER pipeline_stage_event_no_mutation BEFORE UPDATE OR DELETE ON recruitment.pipeline_stage_events
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_orchestration_immutable();
DROP TRIGGER IF EXISTS interview_scorecard_no_mutation ON recruitment.interview_scorecards;
CREATE TRIGGER interview_scorecard_no_mutation BEFORE UPDATE OR DELETE ON recruitment.interview_scorecards
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_orchestration_immutable();
DROP TRIGGER IF EXISTS offer_package_no_mutation ON recruitment.offer_packages;
CREATE TRIGGER offer_package_no_mutation BEFORE UPDATE OR DELETE ON recruitment.offer_packages
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_orchestration_immutable();
DROP TRIGGER IF EXISTS offer_event_no_mutation ON recruitment.offer_events;
CREATE TRIGGER offer_event_no_mutation BEFORE UPDATE OR DELETE ON recruitment.offer_events
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_orchestration_immutable();
DROP TRIGGER IF EXISTS candidate_note_no_mutation ON recruitment.candidate_notes;
CREATE TRIGGER candidate_note_no_mutation BEFORE UPDATE OR DELETE ON recruitment.candidate_notes
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_orchestration_immutable();

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='workforce_runtime') THEN
    GRANT USAGE ON SCHEMA recruitment TO workforce_runtime;
    GRANT SELECT,INSERT ON recruitment.pipeline_templates,
      recruitment.pipeline_stage_events,recruitment.interview_scorecards,
      recruitment.offer_packages,recruitment.offer_events,recruitment.candidate_notes
      TO workforce_runtime;
    GRANT SELECT,INSERT,UPDATE ON recruitment.pipeline_assignments,
      recruitment.offer_decision_capabilities,recruitment.onboarding_tasks
      TO workforce_runtime;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (44, 'governed recruitment orchestration')
ON CONFLICT (version) DO NOTHING;
