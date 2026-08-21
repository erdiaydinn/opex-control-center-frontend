-- EAY Field Intelligence authoritative PostgreSQL foundation.
-- Runtime roles must never own these objects. Tenant authority is derived from session_user binding.
BEGIN;

CREATE TABLE IF NOT EXISTS field_schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS field_missions (
  tenant_id text NOT NULL,
  mission_id text NOT NULL,
  template_id text NOT NULL,
  template_version integer NOT NULL CHECK (template_version > 0),
  status text NOT NULL CHECK (status IN ('draft','active','closed','cancelled')),
  priority text NOT NULL CHECK (priority IN ('normal','high','critical')),
  target_fingerprint text NOT NULL CHECK (target_fingerprint ~ '^[0-9a-f]{64}$'),
  assigned_at timestamptz NOT NULL,
  deadline_at timestamptz NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, mission_id),
  CHECK (deadline_at > assigned_at)
);

CREATE TABLE IF NOT EXISTS field_mission_targets (
  tenant_id text NOT NULL,
  mission_id text NOT NULL,
  location_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('unseen','seen','started','partial','submitted','rework','verified','overdue','exempt')),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, mission_id, location_id),
  FOREIGN KEY (tenant_id, mission_id) REFERENCES field_missions(tenant_id, mission_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS field_mission_targets_status_idx
  ON field_mission_targets (tenant_id, mission_id, status, updated_at);

CREATE TABLE IF NOT EXISTS field_offline_events (
  tenant_id text NOT NULL,
  mission_id text NOT NULL,
  location_id text NOT NULL,
  actor_id text NOT NULL,
  device_id text NOT NULL,
  device_sequence bigint NOT NULL CHECK (device_sequence > 0),
  idempotency_key text NOT NULL,
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  captured_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, device_id, device_sequence),
  UNIQUE (tenant_id, idempotency_key),
  FOREIGN KEY (tenant_id, mission_id, location_id)
    REFERENCES field_mission_targets(tenant_id, mission_id, location_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS field_evidence_envelopes (
  tenant_id text NOT NULL,
  mission_id text NOT NULL,
  location_id text NOT NULL,
  fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  actor_id text NOT NULL,
  device_id text,
  submitted_at timestamptz NOT NULL,
  payload jsonb NOT NULL,
  PRIMARY KEY (tenant_id, mission_id, location_id, fingerprint),
  FOREIGN KEY (tenant_id, mission_id, location_id)
    REFERENCES field_mission_targets(tenant_id, mission_id, location_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS field_verifications (
  tenant_id text NOT NULL,
  mission_id text NOT NULL,
  location_id text NOT NULL,
  envelope_fingerprint text NOT NULL CHECK (envelope_fingerprint ~ '^[0-9a-f]{64}$'),
  reviewer_id text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('accept','rework','reject')),
  reason text,
  reviewed_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, mission_id, location_id, envelope_fingerprint, reviewed_at),
  FOREIGN KEY (tenant_id, mission_id, location_id, envelope_fingerprint)
    REFERENCES field_evidence_envelopes(tenant_id, mission_id, location_id, fingerprint) ON DELETE RESTRICT,
  CHECK (decision='accept' OR length(trim(coalesce(reason,''))) > 0)
);

CREATE TABLE IF NOT EXISTS field_notification_events (
  tenant_id text NOT NULL,
  event_id uuid NOT NULL,
  mission_id text NOT NULL,
  location_id text NOT NULL,
  step_id text NOT NULL,
  recipient_subject text NOT NULL,
  channel text NOT NULL CHECK (channel IN ('in_app','push','email')),
  status text NOT NULL CHECK (status IN ('pending','sent','failed','dead')),
  idempotency_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  PRIMARY KEY (tenant_id, event_id),
  UNIQUE (tenant_id, idempotency_key),
  FOREIGN KEY (tenant_id, mission_id, location_id)
    REFERENCES field_mission_targets(tenant_id, mission_id, location_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS field_audit (
  tenant_id text NOT NULL,
  sequence bigint GENERATED ALWAYS AS IDENTITY,
  event_id uuid NOT NULL,
  mission_id text,
  location_id text,
  actor_subject text NOT NULL,
  action text NOT NULL,
  record jsonb NOT NULL,
  previous_hash text NOT NULL,
  hash text NOT NULL CHECK (hash ~ '^[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, sequence),
  UNIQUE (tenant_id, event_id),
  UNIQUE (tenant_id, hash)
);

CREATE OR REPLACE FUNCTION field_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$;

DROP TRIGGER IF EXISTS field_offline_events_immutable ON field_offline_events;
CREATE TRIGGER field_offline_events_immutable BEFORE UPDATE OR DELETE ON field_offline_events
FOR EACH ROW EXECUTE FUNCTION field_immutable_row();
DROP TRIGGER IF EXISTS field_evidence_immutable ON field_evidence_envelopes;
CREATE TRIGGER field_evidence_immutable BEFORE UPDATE OR DELETE ON field_evidence_envelopes
FOR EACH ROW EXECUTE FUNCTION field_immutable_row();
DROP TRIGGER IF EXISTS field_verifications_immutable ON field_verifications;
CREATE TRIGGER field_verifications_immutable BEFORE UPDATE OR DELETE ON field_verifications
FOR EACH ROW EXECUTE FUNCTION field_immutable_row();
DROP TRIGGER IF EXISTS field_audit_immutable ON field_audit;
CREATE TRIGGER field_audit_immutable BEFORE UPDATE OR DELETE ON field_audit
FOR EACH ROW EXECUTE FUNCTION field_immutable_row();

CREATE TABLE IF NOT EXISTS field_tenant_bindings (
  role_name name PRIMARY KEY,
  tenant_id text NOT NULL
);
REVOKE ALL ON field_tenant_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION field_current_tenant() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
  SELECT tenant_id FROM public.field_tenant_bindings WHERE role_name=session_user
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'field_missions','field_mission_targets','field_offline_events','field_evidence_envelopes',
    'field_verifications','field_notification_events','field_audit'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=field_current_tenant()) WITH CHECK (tenant_id=field_current_tenant())',
      table_name || '_tenant', table_name
    );
  END LOOP;
END $$;

INSERT INTO field_schema_migrations(version,name) VALUES (6,'field intelligence authority evidence and offline replay RLS')
ON CONFLICT (version) DO NOTHING;
COMMIT;
