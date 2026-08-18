-- EAY Inventory v5: server-owned mission attempts and historical leases.
-- Attempts preserve abandoned evidence while only completed attempts contribute to stock truth.
BEGIN;

CREATE TABLE IF NOT EXISTS inventory_mission_attempts (
  tenant_id text NOT NULL,
  attempt_id uuid NOT NULL,
  document_id uuid NOT NULL,
  location_id text NOT NULL,
  warehouse_id text NOT NULL,
  employee_id text NOT NULL,
  device_id uuid NOT NULL,
  active_shift_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE','COMPLETED','ABANDONED','SUPERSEDED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  completed_event_id uuid,
  abandoned_at timestamptz,
  abandonment_reason text,
  PRIMARY KEY (tenant_id, attempt_id),
  FOREIGN KEY (tenant_id, document_id) REFERENCES inventory_documents(tenant_id, id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, device_id) REFERENCES inventory_devices(tenant_id, device_id) ON DELETE RESTRICT,
  CHECK (
    (status='COMPLETED' AND completed_at IS NOT NULL AND completed_event_id IS NOT NULL AND abandoned_at IS NULL)
    OR (status IN ('ABANDONED','SUPERSEDED') AND abandoned_at IS NOT NULL AND completed_at IS NULL AND completed_event_id IS NULL)
    OR (status='ACTIVE' AND completed_at IS NULL AND completed_event_id IS NULL AND abandoned_at IS NULL)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS inventory_mission_attempt_one_active_location_idx
  ON inventory_mission_attempts (tenant_id, document_id, location_id)
  WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS inventory_mission_attempt_document_idx
  ON inventory_mission_attempts (tenant_id, document_id, location_id, created_at);

CREATE TABLE IF NOT EXISTS inventory_mission_leases (
  tenant_id text NOT NULL,
  lease_id uuid NOT NULL,
  attempt_id uuid NOT NULL,
  employee_id text NOT NULL,
  device_id uuid NOT NULL,
  active_shift_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE','COMPLETED','REVOKED','EXPIRED','REPLACED')),
  valid_from timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  replaced_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, lease_id),
  FOREIGN KEY (tenant_id, attempt_id) REFERENCES inventory_mission_attempts(tenant_id, attempt_id) ON DELETE RESTRICT,
  CHECK (expires_at > valid_from),
  CHECK (revoked_at IS NULL OR revoked_at >= valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS inventory_mission_lease_one_active_attempt_idx
  ON inventory_mission_leases (tenant_id, attempt_id)
  WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS inventory_mission_lease_history_idx
  ON inventory_mission_leases (tenant_id, attempt_id, valid_from, expires_at);

ALTER TABLE inventory_events ADD COLUMN IF NOT EXISTS attempt_id uuid;
ALTER TABLE inventory_events ADD COLUMN IF NOT EXISTS lease_id uuid;
ALTER TABLE inventory_events ADD COLUMN IF NOT EXISTS active_shift_id text;

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_mission_binding_v5;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_mission_binding_v5
  CHECK (
    (attempt_id IS NULL AND lease_id IS NULL AND active_shift_id IS NULL)
    OR (attempt_id IS NOT NULL AND lease_id IS NOT NULL AND active_shift_id IS NOT NULL)
  );

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_attempt_v5_fk;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_attempt_v5_fk
  FOREIGN KEY (tenant_id, attempt_id)
  REFERENCES inventory_mission_attempts(tenant_id, attempt_id)
  ON DELETE RESTRICT;

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_lease_v5_fk;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_lease_v5_fk
  FOREIGN KEY (tenant_id, lease_id)
  REFERENCES inventory_mission_leases(tenant_id, lease_id)
  ON DELETE RESTRICT;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'inventory_mission_attempts','inventory_mission_leases'
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
VALUES (5,'inventory mission attempt historical lease authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
