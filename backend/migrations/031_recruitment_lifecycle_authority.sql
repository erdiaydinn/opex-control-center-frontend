-- Hiring V47: four-eyes offer approval, candidate communication outbox,
-- consent-bound talent pool, and governed cross-functional offboarding.

CREATE TABLE IF NOT EXISTS recruitment.offer_approval_workflows (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  offer_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  required_approvals integer NOT NULL DEFAULT 2 CHECK (required_approvals BETWEEN 2 AND 5),
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
  requested_by text NOT NULL CHECK (btrim(requested_by) <> ''),
  requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  decided_at timestamptz,
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  PRIMARY KEY (tenant_id, offer_id),
  FOREIGN KEY (tenant_id, offer_id)
    REFERENCES recruitment.offer_packages(tenant_id, offer_id)
);
CREATE INDEX IF NOT EXISTS offer_approval_pending_idx
  ON recruitment.offer_approval_workflows(tenant_id, status, requested_at);

CREATE TABLE IF NOT EXISTS recruitment.offer_approval_events (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  approval_id uuid NOT NULL,
  offer_id uuid NOT NULL,
  approver_id text NOT NULL CHECK (btrim(approver_id) <> ''),
  decision text NOT NULL CHECK (decision IN ('APPROVED','REJECTED')),
  reason text NOT NULL DEFAULT '' CHECK (length(reason) <= 2000),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, approval_id),
  UNIQUE (tenant_id, offer_id, approver_id),
  FOREIGN KEY (tenant_id, offer_id)
    REFERENCES recruitment.offer_packages(tenant_id, offer_id)
);
CREATE INDEX IF NOT EXISTS offer_approval_event_idx
  ON recruitment.offer_approval_events(tenant_id, offer_id, occurred_at);

CREATE TABLE IF NOT EXISTS recruitment.candidate_communication_outbox (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  message_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  message_type text NOT NULL CHECK (message_type IN (
    'INTERVIEW_INVITE','INTERVIEW_REMINDER','OFFER_READY','OFFER_REMINDER',
    'ONBOARDING_REMINDER','PROCESS_UPDATE','TALENT_POOL_REENGAGE'
  )),
  channel text NOT NULL CHECK (channel IN ('EMAIL','SMS','IN_APP')),
  locale text NOT NULL DEFAULT 'tr-TR' CHECK (btrim(locale) <> '' AND length(locale) <= 20),
  template_key text NOT NULL CHECK (btrim(template_key) <> '' AND length(template_key) <= 120),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
  idempotency_key text NOT NULL CHECK (btrim(idempotency_key) <> '' AND length(idempotency_key) <= 160),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','CLAIMED','SENT','FAILED','CANCELLED')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 20),
  claimed_at timestamptz,
  claimed_by text,
  delivered_at timestamptz,
  failure_code text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  PRIMARY KEY (tenant_id, message_id),
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS candidate_communication_delivery_idx
  ON recruitment.candidate_communication_outbox(tenant_id, status, available_at, created_at)
  WHERE status IN ('QUEUED','FAILED');
CREATE INDEX IF NOT EXISTS candidate_communication_candidate_idx
  ON recruitment.candidate_communication_outbox(tenant_id, request_id, candidate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS recruitment.talent_pool_memberships (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  membership_id uuid NOT NULL,
  subject_key uuid NOT NULL,
  source_request_id text NOT NULL CHECK (btrim(source_request_id) <> ''),
  source_candidate_id text NOT NULL CHECK (btrim(source_candidate_id) <> ''),
  pool_key text NOT NULL CHECK (btrim(pool_key) <> '' AND length(pool_key) <= 80),
  tags jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(tags) = 'array'),
  consent_basis text NOT NULL CHECK (consent_basis IN ('EXPLICIT_CANDIDATE_CONSENT','LEGITIMATE_INTEREST_REVIEWED')),
  consent_record_ref text NOT NULL CHECK (btrim(consent_record_ref) <> '' AND length(consent_record_ref) <= 240),
  consent_expires_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','WITHDRAWN','EXPIRED','PLACED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  withdrawn_at timestamptz,
  withdrawn_by text,
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  PRIMARY KEY (tenant_id, membership_id),
  UNIQUE (tenant_id, subject_key, pool_key)
);
CREATE INDEX IF NOT EXISTS talent_pool_active_idx
  ON recruitment.talent_pool_memberships(tenant_id, pool_key, status, consent_expires_at);

CREATE TABLE IF NOT EXISTS recruitment.offboarding_cases (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  case_id uuid NOT NULL,
  employee_id text NOT NULL CHECK (btrim(employee_id) <> '' AND length(employee_id) <= 80),
  effective_at timestamptz NOT NULL,
  reason_code text NOT NULL CHECK (reason_code IN ('RESIGNATION','TERMINATION','TRANSFER','CONTRACT_END','OTHER')),
  note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
  status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','READY_TO_CLOSE','CLOSED','CANCELLED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  closed_at timestamptz,
  closed_by text,
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  PRIMARY KEY (tenant_id, case_id)
);
CREATE INDEX IF NOT EXISTS offboarding_employee_idx
  ON recruitment.offboarding_cases(tenant_id, employee_id, status, effective_at DESC);

CREATE TABLE IF NOT EXISTS recruitment.offboarding_tasks (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  task_id uuid NOT NULL,
  case_id uuid NOT NULL,
  task_key text NOT NULL CHECK (btrim(task_key) <> '' AND length(task_key) <= 100),
  title text NOT NULL CHECK (btrim(title) <> '' AND length(title) <= 180),
  owner_role text NOT NULL CHECK (owner_role IN ('HR','IT','ADMIN','PAYROLL','ACADEMY','OPERATIONS')),
  required boolean NOT NULL DEFAULT true,
  dependencies jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(dependencies) = 'array'),
  due_at timestamptz,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','IN_PROGRESS','BLOCKED','COMPLETED','WAIVED')),
  completion_note text,
  completed_at timestamptz,
  completed_by text,
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  PRIMARY KEY (tenant_id, task_id),
  UNIQUE (tenant_id, case_id, task_key),
  FOREIGN KEY (tenant_id, case_id)
    REFERENCES recruitment.offboarding_cases(tenant_id, case_id)
);
CREATE INDEX IF NOT EXISTS offboarding_task_case_idx
  ON recruitment.offboarding_tasks(tenant_id, case_id, status, due_at);

CREATE TABLE IF NOT EXISTS recruitment.offboarding_events (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  event_id uuid NOT NULL,
  case_id uuid NOT NULL,
  event_type text NOT NULL CHECK (event_type IN ('CREATED','TASK_UPDATED','READY_TO_CLOSE','CLOSED','CANCELLED')),
  actor_ref text NOT NULL CHECK (btrim(actor_ref) <> ''),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  PRIMARY KEY (tenant_id, event_id),
  FOREIGN KEY (tenant_id, case_id)
    REFERENCES recruitment.offboarding_cases(tenant_id, case_id)
);
CREATE INDEX IF NOT EXISTS offboarding_event_case_idx
  ON recruitment.offboarding_events(tenant_id, case_id, occurred_at DESC);

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'offer_approval_workflows','offer_approval_events','candidate_communication_outbox',
    'talent_pool_memberships','offboarding_cases','offboarding_tasks','offboarding_events'
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

CREATE OR REPLACE FUNCTION recruitment.reject_lifecycle_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='recruitment lifecycle event is append-only';
END;
$$;

DROP TRIGGER IF EXISTS offer_approval_event_no_mutation ON recruitment.offer_approval_events;
CREATE TRIGGER offer_approval_event_no_mutation BEFORE UPDATE OR DELETE ON recruitment.offer_approval_events
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_lifecycle_immutable();
DROP TRIGGER IF EXISTS offboarding_event_no_mutation ON recruitment.offboarding_events;
CREATE TRIGGER offboarding_event_no_mutation BEFORE UPDATE OR DELETE ON recruitment.offboarding_events
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_lifecycle_immutable();

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='workforce_runtime') THEN
    GRANT USAGE ON SCHEMA recruitment TO workforce_runtime;
    GRANT SELECT,INSERT,UPDATE ON recruitment.offer_approval_workflows,
      recruitment.candidate_communication_outbox,recruitment.talent_pool_memberships,
      recruitment.offboarding_cases,recruitment.offboarding_tasks TO workforce_runtime;
    GRANT SELECT,INSERT ON recruitment.offer_approval_events,recruitment.offboarding_events TO workforce_runtime;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (47, 'governed hiring lifecycle authority')
ON CONFLICT (version) DO NOTHING;
