-- Item 25: full offline scheduled Audit with occurrence/idempotency authority.
BEGIN;

CREATE TABLE IF NOT EXISTS audit_schedules (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  schedule_id uuid NOT NULL DEFAULT gen_random_uuid(),
  schedule_key text NOT NULL CHECK (btrim(schedule_key) <> ''),
  template_key text NOT NULL CHECK (btrim(template_key) <> ''),
  template_revision integer NOT NULL CHECK (template_revision > 0),
  template_hash text NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
  location_id text NOT NULL CHECK (btrim(location_id) <> ''),
  assignee_subject text NOT NULL CHECK (btrim(assignee_subject) <> ''),
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, schedule_id),
  UNIQUE (tenant_id, schedule_key),
  FOREIGN KEY (tenant_id, template_key, template_revision, template_hash)
    REFERENCES audit_template_revisions(tenant_id, template_key, revision, content_hash)
    ON DELETE RESTRICT,
  CHECK (window_end > window_start)
);

CREATE TABLE IF NOT EXISTS audit_occurrences (
  tenant_id text NOT NULL,
  occurrence_id uuid NOT NULL,
  schedule_id uuid NOT NULL,
  scheduled_for timestamptz NOT NULL,
  template_key text NOT NULL,
  template_revision integer NOT NULL CHECK (template_revision > 0),
  template_hash text NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
  location_id text NOT NULL CHECK (btrim(location_id) <> ''),
  assignee_subject text NOT NULL CHECK (btrim(assignee_subject) <> ''),
  occurrence_hash text NOT NULL CHECK (occurrence_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, occurrence_id),
  UNIQUE (tenant_id, schedule_id, scheduled_for),
  UNIQUE (tenant_id, occurrence_hash),
  FOREIGN KEY (tenant_id, schedule_id)
    REFERENCES audit_schedules(tenant_id, schedule_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_offline_packages (
  tenant_id text NOT NULL,
  package_id uuid NOT NULL,
  occurrence_id uuid NOT NULL,
  schedule_id uuid NOT NULL,
  template_key text NOT NULL,
  template_revision integer NOT NULL CHECK (template_revision > 0),
  template_hash text NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
  location_id text NOT NULL CHECK (btrim(location_id) <> ''),
  assignee_subject text NOT NULL CHECK (btrim(assignee_subject) <> ''),
  device_id text NOT NULL CHECK (btrim(device_id) <> ''),
  package_version text NOT NULL CHECK (btrim(package_version) <> ''),
  client_schema_version text NOT NULL CHECK (btrim(client_schema_version) <> ''),
  policy_version text NOT NULL CHECK (btrim(policy_version) <> ''),
  issued_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  package_hash text NOT NULL CHECK (package_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (tenant_id, package_id),
  UNIQUE (tenant_id, occurrence_id, package_id),
  UNIQUE (tenant_id, package_hash),
  FOREIGN KEY (tenant_id, occurrence_id)
    REFERENCES audit_occurrences(tenant_id, occurrence_id) ON DELETE RESTRICT,
  CHECK (expires_at > issued_at)
);

CREATE TABLE IF NOT EXISTS audit_offline_mutations (
  tenant_id text NOT NULL,
  mutation_id uuid NOT NULL,
  occurrence_id uuid NOT NULL,
  package_hash text NOT NULL CHECK (package_hash ~ '^[0-9a-f]{64}$'),
  device_id text NOT NULL CHECK (btrim(device_id) <> ''),
  sequence bigint NOT NULL CHECK (sequence > 0),
  nonce text NOT NULL CHECK (btrim(nonce) <> ''),
  idempotency_key text NOT NULL CHECK (btrim(idempotency_key) <> ''),
  mutation_type text NOT NULL CHECK (btrim(mutation_type) <> ''),
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object'),
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  captured_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, mutation_id),
  UNIQUE (tenant_id, occurrence_id, idempotency_key),
  UNIQUE (tenant_id, occurrence_id, device_id, sequence),
  UNIQUE (tenant_id, occurrence_id, nonce),
  FOREIGN KEY (tenant_id, occurrence_id)
    REFERENCES audit_occurrences(tenant_id, occurrence_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_occurrence_runs (
  tenant_id text NOT NULL,
  occurrence_id uuid NOT NULL,
  audit_run_id uuid NOT NULL,
  linked_by text NOT NULL CHECK (btrim(linked_by) <> ''),
  linked_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, occurrence_id),
  UNIQUE (tenant_id, audit_run_id),
  FOREIGN KEY (tenant_id, occurrence_id)
    REFERENCES audit_occurrences(tenant_id, occurrence_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, audit_run_id)
    REFERENCES audit_run_snapshots(tenant_id, audit_run_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_offline_sync_receipts (
  tenant_id text NOT NULL,
  receipt_id uuid NOT NULL DEFAULT gen_random_uuid(),
  occurrence_id uuid NOT NULL,
  audit_run_id uuid,
  accepted_count integer NOT NULL CHECK (accepted_count >= 0),
  replay_count integer NOT NULL CHECK (replay_count >= 0),
  highest_sequence bigint NOT NULL CHECK (highest_sequence >= 0),
  receipt_hash text NOT NULL CHECK (receipt_hash ~ '^[0-9a-f]{64}$'),
  synced_by text NOT NULL CHECK (btrim(synced_by) <> ''),
  synced_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, receipt_id),
  UNIQUE (tenant_id, receipt_hash),
  FOREIGN KEY (tenant_id, occurrence_id)
    REFERENCES audit_occurrences(tenant_id, occurrence_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, audit_run_id)
    REFERENCES audit_run_snapshots(tenant_id, audit_run_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS audit_occurrence_schedule_idx
  ON audit_occurrences(tenant_id, schedule_id, scheduled_for);
CREATE INDEX IF NOT EXISTS audit_offline_mutation_order_idx
  ON audit_offline_mutations(tenant_id, occurrence_id, sequence);
CREATE INDEX IF NOT EXISTS audit_offline_receipt_occurrence_idx
  ON audit_offline_sync_receipts(tenant_id, occurrence_id, synced_at DESC);

CREATE OR REPLACE FUNCTION audit_schedule_insert_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE template_status text;
BEGIN
  SELECT status INTO template_status
  FROM audit_template_revisions
  WHERE tenant_id=NEW.tenant_id
    AND template_key=NEW.template_key
    AND revision=NEW.template_revision
    AND content_hash=NEW.template_hash;
  IF template_status IS DISTINCT FROM 'published' THEN
    RAISE EXCEPTION 'audit schedule must pin an exact published template revision';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS audit_schedule_insert_guard_trigger ON audit_schedules;
CREATE TRIGGER audit_schedule_insert_guard_trigger
BEFORE INSERT ON audit_schedules
FOR EACH ROW EXECUTE FUNCTION audit_schedule_insert_guard();

CREATE OR REPLACE FUNCTION audit_occurrence_insert_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE schedule_row audit_schedules%ROWTYPE;
BEGIN
  SELECT * INTO schedule_row FROM audit_schedules
  WHERE tenant_id=NEW.tenant_id AND schedule_id=NEW.schedule_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'audit occurrence schedule not found'; END IF;
  IF NEW.scheduled_for < schedule_row.window_start OR NEW.scheduled_for > schedule_row.window_end THEN
    RAISE EXCEPTION 'audit occurrence is outside schedule window';
  END IF;
  IF NEW.template_key IS DISTINCT FROM schedule_row.template_key
     OR NEW.template_revision IS DISTINCT FROM schedule_row.template_revision
     OR NEW.template_hash IS DISTINCT FROM schedule_row.template_hash
     OR NEW.location_id IS DISTINCT FROM schedule_row.location_id
     OR NEW.assignee_subject IS DISTINCT FROM schedule_row.assignee_subject THEN
    RAISE EXCEPTION 'audit occurrence must preserve frozen schedule assignment/template';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS audit_occurrence_insert_guard_trigger ON audit_occurrences;
CREATE TRIGGER audit_occurrence_insert_guard_trigger
BEFORE INSERT ON audit_occurrences
FOR EACH ROW EXECUTE FUNCTION audit_occurrence_insert_guard();

CREATE OR REPLACE FUNCTION audit_offline_package_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE occurrence_row audit_occurrences%ROWTYPE;
BEGIN
  SELECT * INTO occurrence_row FROM audit_occurrences
  WHERE tenant_id=NEW.tenant_id AND occurrence_id=NEW.occurrence_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'offline package occurrence not found'; END IF;
  IF NEW.schedule_id IS DISTINCT FROM occurrence_row.schedule_id
     OR NEW.template_key IS DISTINCT FROM occurrence_row.template_key
     OR NEW.template_revision IS DISTINCT FROM occurrence_row.template_revision
     OR NEW.template_hash IS DISTINCT FROM occurrence_row.template_hash
     OR NEW.location_id IS DISTINCT FROM occurrence_row.location_id
     OR NEW.assignee_subject IS DISTINCT FROM occurrence_row.assignee_subject THEN
    RAISE EXCEPTION 'offline package must preserve frozen occurrence authority';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS audit_offline_package_guard_trigger ON audit_offline_packages;
CREATE TRIGGER audit_offline_package_guard_trigger
BEFORE INSERT ON audit_offline_packages
FOR EACH ROW EXECUTE FUNCTION audit_offline_package_guard();

CREATE OR REPLACE FUNCTION audit_offline_mutation_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE package_row audit_offline_packages%ROWTYPE;
BEGIN
  SELECT * INTO package_row FROM audit_offline_packages
  WHERE tenant_id=NEW.tenant_id
    AND occurrence_id=NEW.occurrence_id
    AND package_hash=NEW.package_hash;
  IF NOT FOUND THEN RAISE EXCEPTION 'offline mutation package binding not found'; END IF;
  IF NEW.device_id IS DISTINCT FROM package_row.device_id THEN
    RAISE EXCEPTION 'offline mutation device does not match package';
  END IF;
  IF NEW.captured_at < package_row.issued_at OR NEW.captured_at > package_row.expires_at THEN
    RAISE EXCEPTION 'offline mutation capture time is outside package validity';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS audit_offline_mutation_guard_trigger ON audit_offline_mutations;
CREATE TRIGGER audit_offline_mutation_guard_trigger
BEFORE INSERT ON audit_offline_mutations
FOR EACH ROW EXECUTE FUNCTION audit_offline_mutation_guard();

CREATE OR REPLACE FUNCTION audit_ingest_offline_mutation(
  p_mutation_id uuid,
  p_occurrence_id uuid,
  p_package_hash text,
  p_device_id text,
  p_sequence bigint,
  p_nonce text,
  p_idempotency_key text,
  p_mutation_type text,
  p_payload jsonb,
  p_payload_hash text,
  p_captured_at timestamptz
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE
  v_tenant_id text := public.audit_current_tenant();
  existing public.audit_offline_mutations%ROWTYPE;
  expected_sequence bigint;
BEGIN
  IF v_tenant_id IS NULL OR btrim(v_tenant_id)='' THEN
    RAISE EXCEPTION 'trusted audit tenant binding is required';
  END IF;
  IF p_occurrence_id IS NULL OR p_mutation_id IS NULL THEN
    RAISE EXCEPTION 'occurrence and mutation identity are required';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(v_tenant_id || ':' || p_occurrence_id::text, 0));

  SELECT * INTO existing
  FROM public.audit_offline_mutations
  WHERE tenant_id=v_tenant_id
    AND occurrence_id=p_occurrence_id
    AND idempotency_key=p_idempotency_key;
  IF FOUND THEN
    IF existing.payload_hash IS DISTINCT FROM p_payload_hash
       OR existing.nonce IS DISTINCT FROM p_nonce
       OR existing.sequence IS DISTINCT FROM p_sequence
       OR existing.device_id IS DISTINCT FROM p_device_id
       OR existing.package_hash IS DISTINCT FROM p_package_hash
       OR existing.mutation_type IS DISTINCT FROM p_mutation_type
       OR existing.payload IS DISTINCT FROM p_payload
       OR existing.captured_at IS DISTINCT FROM p_captured_at THEN
      RAISE EXCEPTION 'idempotency replay changed governed mutation content';
    END IF;
    RETURN false;
  END IF;

  SELECT COALESCE(max(sequence),0)+1 INTO expected_sequence
  FROM public.audit_offline_mutations
  WHERE tenant_id=v_tenant_id AND occurrence_id=p_occurrence_id;
  IF p_sequence IS DISTINCT FROM expected_sequence THEN
    RAISE EXCEPTION 'offline mutation sequence conflict: expected %, got %', expected_sequence, p_sequence;
  END IF;

  INSERT INTO public.audit_offline_mutations(
    tenant_id,mutation_id,occurrence_id,package_hash,device_id,sequence,nonce,
    idempotency_key,mutation_type,payload,payload_hash,captured_at
  ) VALUES (
    v_tenant_id,p_mutation_id,p_occurrence_id,p_package_hash,p_device_id,p_sequence,p_nonce,
    p_idempotency_key,p_mutation_type,p_payload,p_payload_hash,p_captured_at
  );
  RETURN true;
END $$;

REVOKE ALL ON FUNCTION audit_ingest_offline_mutation(uuid,uuid,text,text,bigint,text,text,text,jsonb,text,timestamptz) FROM PUBLIC;

CREATE OR REPLACE FUNCTION audit_link_occurrence_run(
  p_occurrence_id uuid,
  p_audit_run_id uuid,
  p_actor text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE
  v_tenant_id text := public.audit_current_tenant();
  occurrence_row public.audit_occurrences%ROWTYPE;
  run_row public.audit_run_snapshots%ROWTYPE;
  existing_run uuid;
BEGIN
  IF v_tenant_id IS NULL OR btrim(v_tenant_id)='' THEN
    RAISE EXCEPTION 'trusted audit tenant binding is required';
  END IF;
  IF p_occurrence_id IS NULL OR p_audit_run_id IS NULL OR p_actor IS NULL OR btrim(p_actor)='' THEN
    RAISE EXCEPTION 'occurrence, audit run and actor are required';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(v_tenant_id || ':' || p_occurrence_id::text, 1));

  SELECT * INTO occurrence_row
  FROM public.audit_occurrences
  WHERE tenant_id=v_tenant_id AND occurrence_id=p_occurrence_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'scheduled audit occurrence not found for tenant'; END IF;

  SELECT * INTO run_row
  FROM public.audit_run_snapshots
  WHERE tenant_id=v_tenant_id AND audit_run_id=p_audit_run_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'audit run snapshot not found for tenant'; END IF;

  IF run_row.template_key IS DISTINCT FROM occurrence_row.template_key
     OR run_row.template_revision IS DISTINCT FROM occurrence_row.template_revision
     OR run_row.template_hash IS DISTINCT FROM occurrence_row.template_hash THEN
    RAISE EXCEPTION 'audit run template does not match frozen schedule occurrence';
  END IF;
  IF run_row.completed_by IS DISTINCT FROM occurrence_row.assignee_subject THEN
    RAISE EXCEPTION 'audit run actor does not match frozen schedule assignee';
  END IF;

  SELECT audit_run_id INTO existing_run
  FROM public.audit_occurrence_runs
  WHERE tenant_id=v_tenant_id AND occurrence_id=p_occurrence_id;
  IF FOUND THEN
    IF existing_run IS DISTINCT FROM p_audit_run_id THEN
      RAISE EXCEPTION 'schedule occurrence is already linked to a different audit run';
    END IF;
    RETURN false;
  END IF;

  INSERT INTO public.audit_occurrence_runs(tenant_id,occurrence_id,audit_run_id,linked_by)
  VALUES (v_tenant_id,p_occurrence_id,p_audit_run_id,p_actor);
  RETURN true;
END $$;

REVOKE ALL ON FUNCTION audit_link_occurrence_run(uuid,uuid,text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION audit_offline_history_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'audit_schedules',
    'audit_occurrences',
    'audit_offline_packages',
    'audit_offline_mutations',
    'audit_occurrence_runs',
    'audit_offline_sync_receipts'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', table_name || '_immutable', table_name);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION audit_offline_history_immutable()',
      table_name || '_immutable', table_name
    );
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=audit_current_tenant()) WITH CHECK (tenant_id=audit_current_tenant())',
      table_name || '_tenant', table_name
    );
  END LOOP;
END $$;

COMMIT;
