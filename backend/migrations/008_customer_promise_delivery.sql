-- EAY Customer Promise & Delivery Experience repository authority.
-- This stores customer-visible promise/evidence/recovery records, not OMS order truth or raw customer PII.
BEGIN;

CREATE TABLE IF NOT EXISTS customer_promise_schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customer_promises (
  tenant_id text NOT NULL,
  promise_id text NOT NULL,
  external_order_ref text NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  supersedes_version integer,
  source_system text NOT NULL,
  source_record_ref text NOT NULL,
  committed_at timestamptz NOT NULL,
  promised_start_at timestamptz NOT NULL,
  promised_end_at timestamptz NOT NULL,
  service_level text NOT NULL,
  customer_fee_minor_units bigint,
  currency char(3),
  instruction_reference text,
  instruction_fingerprint text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, promise_id, version),
  UNIQUE (tenant_id, promise_id, version, external_order_ref),
  CHECK (promised_end_at > promised_start_at),
  CHECK (customer_fee_minor_units IS NULL OR customer_fee_minor_units >= 0),
  CHECK ((customer_fee_minor_units IS NULL) = (currency IS NULL)),
  CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
  CHECK ((instruction_reference IS NULL) = (instruction_fingerprint IS NULL)),
  CHECK (instruction_fingerprint IS NULL OR instruction_fingerprint ~ '^[0-9a-f]{64}$'),
  CHECK ((version = 1 AND supersedes_version IS NULL) OR (version > 1 AND supersedes_version = version - 1))
);
CREATE INDEX IF NOT EXISTS customer_promises_order_idx
  ON customer_promises (tenant_id, external_order_ref, committed_at DESC, version DESC);

CREATE TABLE IF NOT EXISTS customer_delivery_events (
  tenant_id text NOT NULL,
  event_id uuid NOT NULL,
  external_order_ref text NOT NULL,
  event_type text NOT NULL CHECK (event_type IN (
    'order_accepted','courier_assigned','picked_up','arrived','delivered','failed_attempt','cancelled','customer_contacted'
  )),
  source_system text NOT NULL,
  source_event_ref text NOT NULL,
  occurred_at timestamptz NOT NULL,
  idempotency_key text NOT NULL,
  payload_fingerprint text NOT NULL CHECK (payload_fingerprint ~ '^[0-9a-f]{64}$'),
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, event_id),
  UNIQUE (tenant_id, idempotency_key),
  UNIQUE (tenant_id, source_system, source_event_ref)
);
CREATE INDEX IF NOT EXISTS customer_delivery_events_order_idx
  ON customer_delivery_events (tenant_id, external_order_ref, occurred_at);

CREATE TABLE IF NOT EXISTS customer_promise_evaluations (
  tenant_id text NOT NULL,
  evaluation_id uuid NOT NULL,
  promise_id text NOT NULL,
  promise_version integer NOT NULL,
  external_order_ref text NOT NULL,
  evaluator_version text NOT NULL,
  outcome text NOT NULL CHECK (outcome IN ('on_time','early','late','failed','cancelled','in_progress')),
  timing_delta_minutes integer,
  fee_delta_minor_units bigint,
  instruction_breach boolean,
  breach_types text[] NOT NULL DEFAULT '{}',
  fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  evaluated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, evaluation_id),
  UNIQUE (tenant_id, fingerprint),
  FOREIGN KEY (tenant_id, promise_id, promise_version, external_order_ref)
    REFERENCES customer_promises(tenant_id, promise_id, version, external_order_ref) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS customer_promise_evaluations_order_idx
  ON customer_promise_evaluations (tenant_id, external_order_ref, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS customer_cause_assertions (
  tenant_id text NOT NULL,
  assertion_id uuid NOT NULL,
  evaluation_id uuid NOT NULL,
  external_order_ref text NOT NULL,
  cause_code text NOT NULL,
  assertion_type text NOT NULL CHECK (assertion_type IN ('verified_evidence','hypothesis')),
  evidence_reference text,
  confidence numeric(6,5),
  asserted_by text NOT NULL,
  asserted_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, assertion_id),
  FOREIGN KEY (tenant_id, evaluation_id)
    REFERENCES customer_promise_evaluations(tenant_id, evaluation_id) ON DELETE RESTRICT,
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  CHECK (
    (assertion_type='verified_evidence' AND evidence_reference IS NOT NULL AND confidence IS NULL)
    OR assertion_type='hypothesis'
  )
);
CREATE INDEX IF NOT EXISTS customer_cause_assertions_order_idx
  ON customer_cause_assertions (tenant_id, external_order_ref, asserted_at DESC);

CREATE TABLE IF NOT EXISTS customer_recovery_requests (
  tenant_id text NOT NULL,
  recovery_id uuid NOT NULL,
  evaluation_id uuid NOT NULL,
  external_order_ref text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('customer_message','fee_refund','credit','reorder','manual_review')),
  amount_minor_units bigint,
  currency char(3),
  reason_code text NOT NULL,
  proposed_by text NOT NULL,
  proposed_at timestamptz NOT NULL,
  requires_human_approval boolean NOT NULL DEFAULT true,
  PRIMARY KEY (tenant_id, recovery_id),
  FOREIGN KEY (tenant_id, evaluation_id)
    REFERENCES customer_promise_evaluations(tenant_id, evaluation_id) ON DELETE RESTRICT,
  CHECK (amount_minor_units IS NULL OR amount_minor_units >= 0),
  CHECK ((amount_minor_units IS NULL) = (currency IS NULL)),
  CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
  CHECK (
    (kind IN ('fee_refund','credit') AND amount_minor_units IS NOT NULL AND requires_human_approval IS TRUE)
    OR (kind NOT IN ('fee_refund','credit') AND amount_minor_units IS NULL)
  )
);
CREATE INDEX IF NOT EXISTS customer_recovery_requests_order_idx
  ON customer_recovery_requests (tenant_id, external_order_ref, proposed_at DESC);

CREATE TABLE IF NOT EXISTS customer_recovery_decisions (
  tenant_id text NOT NULL,
  decision_id uuid NOT NULL,
  recovery_id uuid NOT NULL,
  decision text NOT NULL CHECK (decision IN ('approved','rejected')),
  decided_by text NOT NULL,
  decided_at timestamptz NOT NULL,
  reason text,
  PRIMARY KEY (tenant_id, decision_id),
  UNIQUE (tenant_id, recovery_id),
  FOREIGN KEY (tenant_id, recovery_id)
    REFERENCES customer_recovery_requests(tenant_id, recovery_id) ON DELETE RESTRICT,
  CHECK (decision='approved' OR length(trim(coalesce(reason,''))) > 0)
);

CREATE OR REPLACE FUNCTION customer_promise_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'customer_promises','customer_delivery_events','customer_promise_evaluations',
    'customer_cause_assertions','customer_recovery_requests','customer_recovery_decisions'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', table_name || '_immutable', table_name);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION customer_promise_immutable_row()',
      table_name || '_immutable', table_name
    );
  END LOOP;
END $$;

-- Repository test harness uses a session-user binding so a runtime identity cannot select another tenant.
-- Production identity remains the canonical Platform Core responsibility; this is not a second login framework.
CREATE TABLE IF NOT EXISTS customer_promise_tenant_bindings (
  role_name name PRIMARY KEY,
  tenant_id text NOT NULL
);
REVOKE ALL ON customer_promise_tenant_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION customer_promise_current_tenant() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
  SELECT tenant_id FROM public.customer_promise_tenant_bindings WHERE role_name=session_user
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'customer_promises','customer_delivery_events','customer_promise_evaluations',
    'customer_cause_assertions','customer_recovery_requests','customer_recovery_decisions'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=customer_promise_current_tenant()) WITH CHECK (tenant_id=customer_promise_current_tenant())',
      table_name || '_tenant', table_name
    );
  END LOOP;
END $$;

INSERT INTO customer_promise_schema_migrations(version,name)
VALUES (8,'customer promise delivery evidence recovery and tenant RLS')
ON CONFLICT (version) DO NOTHING;
COMMIT;
