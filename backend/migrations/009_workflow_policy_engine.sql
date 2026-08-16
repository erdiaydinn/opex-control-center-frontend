-- EAY Configurable Workflow / Policy Engine persistence authority.
-- Stores versioned rule definitions, governance events, event fingerprints and action intents.
-- Raw event facts are intentionally not persisted here.
BEGIN;

CREATE TABLE IF NOT EXISTS workflow_policy_schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_policy_definitions (
  tenant_id text NOT NULL,
  workflow_id text NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  supersedes_version integer,
  source_module text NOT NULL,
  event_type text NOT NULL,
  scope_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(scope_json)='object'),
  effective_from timestamptz NOT NULL,
  effective_to timestamptz,
  content_fingerprint text NOT NULL CHECK (content_fingerprint ~ '^[0-9a-f]{64}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, workflow_id, version),
  CHECK ((version = 1 AND supersedes_version IS NULL) OR (version > 1 AND supersedes_version = version - 1)),
  CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX IF NOT EXISTS workflow_policy_definitions_event_idx
  ON workflow_policy_definitions (tenant_id, source_module, event_type, effective_from DESC, version DESC);

CREATE TABLE IF NOT EXISTS workflow_policy_rules (
  tenant_id text NOT NULL,
  workflow_id text NOT NULL,
  workflow_version integer NOT NULL,
  rule_id text NOT NULL,
  priority integer NOT NULL DEFAULT 100 CHECK (priority >= 0 AND priority <= 10000),
  match_mode text NOT NULL CHECK (match_mode IN ('all','any')),
  exclusive_group text,
  stop_processing boolean NOT NULL DEFAULT false,
  conditions_json jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(conditions_json)='array'),
  actions_json jsonb NOT NULL CHECK (jsonb_typeof(actions_json)='array' AND jsonb_array_length(actions_json) > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, workflow_id, workflow_version, rule_id),
  FOREIGN KEY (tenant_id, workflow_id, workflow_version)
    REFERENCES workflow_policy_definitions(tenant_id, workflow_id, version) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS workflow_policy_governance_events (
  tenant_id text NOT NULL,
  governance_event_id uuid NOT NULL,
  workflow_id text NOT NULL,
  workflow_version integer NOT NULL,
  from_status text NOT NULL CHECK (from_status IN ('draft','approved','effective','superseded','disabled')),
  to_status text NOT NULL CHECK (to_status IN ('draft','approved','effective','superseded','disabled')),
  actor_id text NOT NULL,
  occurred_at timestamptz NOT NULL,
  reason text,
  PRIMARY KEY (tenant_id, governance_event_id),
  FOREIGN KEY (tenant_id, workflow_id, workflow_version)
    REFERENCES workflow_policy_definitions(tenant_id, workflow_id, version) ON DELETE RESTRICT,
  CHECK (
    (from_status='draft' AND to_status IN ('approved','disabled'))
    OR (from_status='approved' AND to_status IN ('effective','disabled'))
    OR (from_status='effective' AND to_status IN ('superseded','disabled'))
  ),
  CHECK (to_status <> 'disabled' OR length(trim(coalesce(reason,''))) > 0)
);
CREATE INDEX IF NOT EXISTS workflow_policy_governance_latest_idx
  ON workflow_policy_governance_events (tenant_id, workflow_id, workflow_version, occurred_at DESC);

CREATE OR REPLACE VIEW workflow_policy_current_status
WITH (security_invoker=true) AS
WITH latest AS (
  SELECT DISTINCT ON (tenant_id, workflow_id, workflow_version)
    tenant_id,
    workflow_id,
    workflow_version,
    to_status AS status,
    actor_id,
    occurred_at
  FROM workflow_policy_governance_events
  ORDER BY tenant_id, workflow_id, workflow_version, occurred_at DESC, governance_event_id DESC
)
SELECT
  d.tenant_id,
  d.workflow_id,
  d.version AS workflow_version,
  coalesce(l.status, 'draft') AS status,
  l.actor_id AS last_actor_id,
  l.occurred_at AS status_changed_at
FROM workflow_policy_definitions d
LEFT JOIN latest l
  ON l.tenant_id=d.tenant_id
 AND l.workflow_id=d.workflow_id
 AND l.workflow_version=d.version;

CREATE TABLE IF NOT EXISTS workflow_policy_event_receipts (
  tenant_id text NOT NULL,
  receipt_id uuid NOT NULL,
  event_id text NOT NULL,
  idempotency_key text NOT NULL,
  source_module text NOT NULL,
  event_type text NOT NULL,
  subject_ref text NOT NULL,
  scope_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(scope_json)='object'),
  facts_fingerprint text NOT NULL CHECK (facts_fingerprint ~ '^[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, receipt_id),
  UNIQUE (tenant_id, event_id),
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS workflow_policy_event_receipts_event_idx
  ON workflow_policy_event_receipts (tenant_id, source_module, event_type, occurred_at DESC);

CREATE TABLE IF NOT EXISTS workflow_policy_evaluations (
  tenant_id text NOT NULL,
  evaluation_id uuid NOT NULL,
  workflow_id text NOT NULL,
  workflow_version integer NOT NULL,
  event_id text NOT NULL,
  dry_run boolean NOT NULL DEFAULT false,
  matched_rule_ids text[] NOT NULL DEFAULT '{}',
  decision_fingerprint text NOT NULL CHECK (decision_fingerprint ~ '^[0-9a-f]{64}$'),
  evaluated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, evaluation_id),
  UNIQUE (tenant_id, workflow_id, workflow_version, event_id, dry_run, decision_fingerprint),
  FOREIGN KEY (tenant_id, workflow_id, workflow_version)
    REFERENCES workflow_policy_definitions(tenant_id, workflow_id, version) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, event_id)
    REFERENCES workflow_policy_event_receipts(tenant_id, event_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS workflow_policy_action_intents (
  tenant_id text NOT NULL,
  intent_id text NOT NULL CHECK (intent_id ~ '^[0-9a-f]{64}$'),
  evaluation_id uuid NOT NULL,
  action_key text NOT NULL,
  action_type text NOT NULL CHECK (action_type IN ('notify','create_task','request_approval','propose_domain_action','schedule_recheck')),
  effect text NOT NULL CHECK (effect IN ('informational','operational','financial','employment','security')),
  execution_mode text NOT NULL CHECK (execution_mode IN ('automatic','requires_approval','proposal_only')),
  parameters_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(parameters_json)='object'),
  approval_required boolean NOT NULL,
  dry_run boolean NOT NULL DEFAULT false,
  dedupe_key text NOT NULL CHECK (dedupe_key ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, intent_id),
  UNIQUE (tenant_id, dedupe_key),
  FOREIGN KEY (tenant_id, evaluation_id)
    REFERENCES workflow_policy_evaluations(tenant_id, evaluation_id) ON DELETE RESTRICT,
  CHECK (effect NOT IN ('financial','employment','security') OR execution_mode <> 'automatic'),
  CHECK (action_type <> 'propose_domain_action' OR execution_mode <> 'automatic'),
  CHECK (effect NOT IN ('financial','employment','security') OR approval_required IS TRUE),
  CHECK (NOT (parameters_json ?| ARRAY['password','secret','access_token','refresh_token','id_token','authorization','phone','email','address','door_code','national_id','tc_kimlik','command','script','sql_query','endpoint_url','webhook_url']))
);

CREATE TABLE IF NOT EXISTS workflow_policy_action_decisions (
  tenant_id text NOT NULL,
  decision_id uuid NOT NULL,
  intent_id text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('approved','rejected')),
  decided_by text NOT NULL,
  decided_at timestamptz NOT NULL,
  reason text,
  PRIMARY KEY (tenant_id, decision_id),
  UNIQUE (tenant_id, intent_id),
  FOREIGN KEY (tenant_id, intent_id)
    REFERENCES workflow_policy_action_intents(tenant_id, intent_id) ON DELETE RESTRICT,
  CHECK (decision='approved' OR length(trim(coalesce(reason,''))) > 0)
);

CREATE OR REPLACE FUNCTION workflow_policy_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END $$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'workflow_policy_definitions',
    'workflow_policy_rules',
    'workflow_policy_governance_events',
    'workflow_policy_event_receipts',
    'workflow_policy_evaluations',
    'workflow_policy_action_intents',
    'workflow_policy_action_decisions'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', table_name || '_immutable', table_name);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION workflow_policy_immutable_row()',
      table_name || '_immutable', table_name
    );
  END LOOP;
END $$;

-- Repository/CI identity binding only. Production tenant identity remains Platform Core authority.
CREATE TABLE IF NOT EXISTS workflow_policy_tenant_bindings (
  role_name name PRIMARY KEY,
  tenant_id text NOT NULL
);
REVOKE ALL ON workflow_policy_tenant_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION workflow_policy_current_tenant() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
  SELECT tenant_id FROM public.workflow_policy_tenant_bindings WHERE role_name=session_user
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'workflow_policy_definitions',
    'workflow_policy_rules',
    'workflow_policy_governance_events',
    'workflow_policy_event_receipts',
    'workflow_policy_evaluations',
    'workflow_policy_action_intents',
    'workflow_policy_action_decisions'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=workflow_policy_current_tenant()) WITH CHECK (tenant_id=workflow_policy_current_tenant())',
      table_name || '_tenant', table_name
    );
  END LOOP;
END $$;

INSERT INTO workflow_policy_schema_migrations(version,name)
VALUES (9,'configurable workflow policy engine definitions governance receipts intents approvals and tenant RLS')
ON CONFLICT (version) DO NOTHING;
COMMIT;
