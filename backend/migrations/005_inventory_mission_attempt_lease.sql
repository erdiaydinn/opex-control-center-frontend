-- EAY Inventory v5: server-owned mission attempts and append-only historical lease intervals.
-- Lease authority is evaluated at event occurred_at; upload time never widens authority.
BEGIN;

CREATE TABLE IF NOT EXISTS inventory_mission_attempts (
  tenant_id text NOT NULL,
  attempt_id uuid NOT NULL,
  document_id uuid NOT NULL,
  warehouse_id text NOT NULL,
  location_id text NOT NULL,
  state text NOT NULL DEFAULT 'ACTIVE'
    CHECK (state IN ('ACTIVE','COMPLETED','ABANDONED','SUPERSEDED')),
  created_by_subject text NOT NULL,
  created_by_employee_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  close_reason text,
  PRIMARY KEY (tenant_id, attempt_id),
  FOREIGN KEY (tenant_id, document_id)
    REFERENCES inventory_documents(tenant_id, id) ON DELETE RESTRICT,
  CHECK (
    (state='ACTIVE' AND closed_at IS NULL AND close_reason IS NULL)
    OR
    (state<>'ACTIVE' AND closed_at IS NOT NULL AND length(trim(close_reason)) >= 3)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS inventory_mission_attempt_one_active_idx
  ON inventory_mission_attempts (tenant_id, document_id, location_id)
  WHERE state='ACTIVE';
CREATE INDEX IF NOT EXISTS inventory_mission_attempt_document_idx
  ON inventory_mission_attempts (tenant_id, document_id, location_id, created_at);

CREATE OR REPLACE FUNCTION inventory_guard_mission_attempt_v5() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'inventory_mission_attempts is history-preserving';
  END IF;

  IF NEW.tenant_id<>OLD.tenant_id
     OR NEW.attempt_id<>OLD.attempt_id
     OR NEW.document_id<>OLD.document_id
     OR NEW.warehouse_id<>OLD.warehouse_id
     OR NEW.location_id<>OLD.location_id
     OR NEW.created_by_subject<>OLD.created_by_subject
     OR NEW.created_by_employee_id<>OLD.created_by_employee_id
     OR NEW.created_at<>OLD.created_at THEN
    RAISE EXCEPTION 'Inventory mission-attempt provenance is immutable.';
  END IF;

  IF OLD.state<>'ACTIVE' THEN
    RAISE EXCEPTION 'Closed Inventory mission attempts are immutable.';
  END IF;
  IF NEW.state NOT IN ('COMPLETED','ABANDONED','SUPERSEDED') THEN
    RAISE EXCEPTION 'Inventory mission attempt may only close from ACTIVE.';
  END IF;
  IF NEW.closed_at IS NULL OR NEW.closed_at<OLD.created_at OR length(trim(NEW.close_reason))<3 THEN
    RAISE EXCEPTION 'Closed Inventory mission attempt requires a valid close time and reason.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_mission_attempt_v5_trigger ON inventory_mission_attempts;
CREATE TRIGGER inventory_guard_mission_attempt_v5_trigger
BEFORE UPDATE OR DELETE ON inventory_mission_attempts
FOR EACH ROW EXECUTE FUNCTION inventory_guard_mission_attempt_v5();

CREATE TABLE IF NOT EXISTS inventory_mission_leases (
  tenant_id text NOT NULL,
  lease_id uuid NOT NULL,
  attempt_id uuid NOT NULL,
  employee_id text NOT NULL,
  device_id uuid NOT NULL,
  shift_id text NOT NULL,
  warehouse_id text NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz NOT NULL,
  issued_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, lease_id),
  UNIQUE (tenant_id, lease_id, attempt_id),
  FOREIGN KEY (tenant_id, attempt_id)
    REFERENCES inventory_mission_attempts(tenant_id, attempt_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, device_id)
    REFERENCES inventory_devices(tenant_id, device_id) ON DELETE RESTRICT,
  CHECK (valid_until>valid_from),
  CHECK (length(trim(shift_id))>0),
  CHECK (length(trim(employee_id))>0),
  CHECK (length(trim(warehouse_id))>0)
);
CREATE INDEX IF NOT EXISTS inventory_mission_lease_attempt_interval_idx
  ON inventory_mission_leases (tenant_id, attempt_id, valid_from, valid_until);
CREATE INDEX IF NOT EXISTS inventory_mission_lease_owner_idx
  ON inventory_mission_leases (tenant_id, employee_id, device_id, valid_until);

DROP TRIGGER IF EXISTS inventory_mission_leases_immutable ON inventory_mission_leases;
CREATE TRIGGER inventory_mission_leases_immutable
BEFORE UPDATE OR DELETE ON inventory_mission_leases
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();

CREATE TABLE IF NOT EXISTS inventory_mission_lease_closures (
  tenant_id text NOT NULL,
  lease_id uuid NOT NULL,
  state text NOT NULL CHECK (state IN ('COMPLETED','REVOKED','SUPERSEDED')),
  reason text NOT NULL CHECK (length(trim(reason))>=3),
  closed_at timestamptz NOT NULL,
  closed_by_subject text NOT NULL,
  PRIMARY KEY (tenant_id, lease_id),
  FOREIGN KEY (tenant_id, lease_id)
    REFERENCES inventory_mission_leases(tenant_id, lease_id) ON DELETE RESTRICT
);

DROP TRIGGER IF EXISTS inventory_mission_lease_closures_immutable ON inventory_mission_lease_closures;
CREATE TRIGGER inventory_mission_lease_closures_immutable
BEFORE UPDATE OR DELETE ON inventory_mission_lease_closures
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();

ALTER TABLE inventory_events ADD COLUMN IF NOT EXISTS attempt_id uuid;
ALTER TABLE inventory_events ADD COLUMN IF NOT EXISTS lease_id uuid;
ALTER TABLE inventory_events ADD COLUMN IF NOT EXISTS active_shift_id text;

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_mission_binding_v5;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_mission_binding_v5
  CHECK (
    event_type NOT IN ('SCAN','UNEXPECTED_SKU','LOCATION_COMPLETE')
    OR (attempt_id IS NOT NULL AND lease_id IS NOT NULL AND active_shift_id IS NOT NULL)
  ) NOT VALID;

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_attempt_v5_fk;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_attempt_v5_fk
  FOREIGN KEY (tenant_id, attempt_id)
  REFERENCES inventory_mission_attempts(tenant_id, attempt_id)
  NOT VALID;

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_lease_attempt_v5_fk;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_lease_attempt_v5_fk
  FOREIGN KEY (tenant_id, lease_id, attempt_id)
  REFERENCES inventory_mission_leases(tenant_id, lease_id, attempt_id)
  NOT VALID;

CREATE OR REPLACE FUNCTION inventory_guard_mission_event_v5() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  attempt_row inventory_mission_attempts%ROWTYPE;
  lease_row inventory_mission_leases%ROWTYPE;
  lease_closed_at timestamptz;
BEGIN
  IF NEW.event_type NOT IN ('SCAN','UNEXPECTED_SKU','LOCATION_COMPLETE') THEN
    RETURN NEW;
  END IF;
  IF NEW.attempt_id IS NULL OR NEW.lease_id IS NULL OR NEW.active_shift_id IS NULL THEN
    RAISE EXCEPTION 'Inventory terminal event requires mission attempt and lease binding.';
  END IF;

  SELECT * INTO attempt_row
    FROM inventory_mission_attempts
   WHERE tenant_id=NEW.tenant_id AND attempt_id=NEW.attempt_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Inventory mission attempt does not exist.';
  END IF;

  IF attempt_row.document_id<>NEW.document_id
     OR attempt_row.warehouse_id<>NEW.warehouse_id
     OR attempt_row.location_id<>NEW.location_id THEN
    RAISE EXCEPTION 'Inventory event does not match its mission attempt binding.';
  END IF;

  SELECT * INTO lease_row
    FROM inventory_mission_leases
   WHERE tenant_id=NEW.tenant_id
     AND lease_id=NEW.lease_id
     AND attempt_id=NEW.attempt_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Inventory mission lease does not exist.';
  END IF;

  IF lease_row.employee_id<>NEW.employee_id
     OR lease_row.device_id<>NEW.device_id
     OR lease_row.shift_id<>NEW.active_shift_id
     OR lease_row.warehouse_id<>NEW.warehouse_id THEN
    RAISE EXCEPTION 'Inventory event does not match its historical lease owner.';
  END IF;

  IF NEW.occurred_at<lease_row.valid_from OR NEW.occurred_at>lease_row.valid_until THEN
    RAISE EXCEPTION 'Inventory event occurred outside its issued lease interval.';
  END IF;

  SELECT closed_at INTO lease_closed_at
    FROM inventory_mission_lease_closures
   WHERE tenant_id=NEW.tenant_id AND lease_id=NEW.lease_id;
  IF FOUND AND NEW.occurred_at>lease_closed_at THEN
    RAISE EXCEPTION 'Inventory event occurred after its lease was closed.';
  END IF;

  IF attempt_row.closed_at IS NOT NULL AND NEW.occurred_at>attempt_row.closed_at THEN
    RAISE EXCEPTION 'Inventory event occurred after its mission attempt was closed.';
  END IF;

  IF NEW.event_type='LOCATION_COMPLETE' AND attempt_row.state<>'ACTIVE' THEN
    RAISE EXCEPTION 'Only an ACTIVE Inventory mission attempt may complete a location.';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_mission_event_v5_trigger ON inventory_events;
CREATE TRIGGER inventory_guard_mission_event_v5_trigger
BEFORE INSERT ON inventory_events
FOR EACH ROW EXECUTE FUNCTION inventory_guard_mission_event_v5();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'inventory_mission_attempts','inventory_mission_leases','inventory_mission_lease_closures'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=inventory_current_tenant()) WITH CHECK (tenant_id=inventory_current_tenant())',
      table_name || '_tenant', table_name
    );
  END LOOP;
END $$;

INSERT INTO inventory_schema_migrations(version,name)
VALUES (5,'inventory mission attempt and historical lease authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
