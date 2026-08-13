-- EAY Inventory P0 authoritative PostgreSQL state.
-- Apply with the migration identity. Runtime roles must never own these objects.
BEGIN;

CREATE TABLE IF NOT EXISTS inventory_schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory_devices (
  tenant_id text NOT NULL,
  device_id uuid NOT NULL,
  employee_id text NOT NULL,
  public_key_pem text NOT NULL,
  mdm_enrollment_hash text NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE','REVOKED','REPLACED')),
  replaced_by uuid,
  enrolled_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  PRIMARY KEY (tenant_id, device_id),
  UNIQUE (tenant_id, mdm_enrollment_hash)
);

CREATE TABLE IF NOT EXISTS inventory_device_activation_codes (
  tenant_id text NOT NULL,
  activation_hash text NOT NULL,
  employee_id text NOT NULL,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  consumed_by uuid,
  PRIMARY KEY (tenant_id, activation_hash)
);

CREATE TABLE IF NOT EXISTS inventory_device_nonces (
  tenant_id text NOT NULL,
  device_id uuid NOT NULL,
  nonce text NOT NULL,
  request_timestamp timestamptz NOT NULL,
  consumed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, device_id, nonce),
  FOREIGN KEY (tenant_id, device_id) REFERENCES inventory_devices(tenant_id, device_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS inventory_documents (
  tenant_id text NOT NULL,
  id uuid NOT NULL,
  warehouse_id text NOT NULL,
  name text NOT NULL,
  state text NOT NULL CHECK (state IN ('COUNTING','SUBMITTED','RECONCILING','APPROVED','LOCKED','REJECTED')),
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  created_by text NOT NULL,
  submitted_by text,
  approved_by text,
  locked_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id),
  CHECK (approved_by IS NULL OR approved_by IS DISTINCT FROM submitted_by),
  CHECK (locked_by IS NULL OR locked_by IS DISTINCT FROM submitted_by)
);

CREATE TABLE IF NOT EXISTS inventory_document_locations (
  tenant_id text NOT NULL,
  document_id uuid NOT NULL,
  location_id text NOT NULL,
  PRIMARY KEY (tenant_id, document_id, location_id),
  FOREIGN KEY (tenant_id, document_id) REFERENCES inventory_documents(tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS inventory_expected_stock (
  tenant_id text NOT NULL,
  document_id uuid NOT NULL,
  sku text NOT NULL,
  barcode text NOT NULL,
  expected_quantity numeric(18,3) NOT NULL,
  unit_cost numeric(18,4) NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, document_id, sku),
  UNIQUE (tenant_id, document_id, barcode),
  FOREIGN KEY (tenant_id, document_id) REFERENCES inventory_documents(tenant_id, id) ON DELETE RESTRICT
);
REVOKE SELECT ON inventory_expected_stock FROM PUBLIC;

CREATE TABLE IF NOT EXISTS inventory_events (
  tenant_id text NOT NULL,
  event_id uuid NOT NULL,
  device_id uuid NOT NULL,
  device_sequence bigint NOT NULL CHECK (device_sequence > 0),
  document_id uuid NOT NULL,
  warehouse_id text NOT NULL,
  employee_id text NOT NULL,
  event_type text NOT NULL CHECK (event_type IN ('SCAN','CORRECTION','UNEXPECTED_SKU')),
  location_id text NOT NULL,
  barcode text NOT NULL,
  quantity numeric(18,3) NOT NULL CHECK (quantity >= 0),
  symbology text NOT NULL,
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, event_id),
  UNIQUE (tenant_id, device_id, device_sequence),
  FOREIGN KEY (tenant_id, device_id) REFERENCES inventory_devices(tenant_id, device_id),
  FOREIGN KEY (tenant_id, document_id) REFERENCES inventory_documents(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS inventory_events_document_idx
  ON inventory_events (tenant_id, document_id, location_id, received_at);

CREATE TABLE IF NOT EXISTS inventory_event_responses (
  tenant_id text NOT NULL,
  event_id uuid NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, event_id),
  FOREIGN KEY (tenant_id, event_id) REFERENCES inventory_events(tenant_id, event_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS inventory_revisions (
  tenant_id text NOT NULL,
  document_id uuid NOT NULL,
  revision bigint NOT NULL,
  state text NOT NULL,
  actor_subject text NOT NULL,
  employee_id text NOT NULL,
  reason text NOT NULL,
  snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, document_id, revision),
  FOREIGN KEY (tenant_id, document_id) REFERENCES inventory_documents(tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS inventory_audit (
  tenant_id text NOT NULL,
  sequence bigint GENERATED ALWAYS AS IDENTITY,
  event_id uuid NOT NULL,
  actor_subject text NOT NULL,
  employee_id text NOT NULL,
  device_id uuid,
  warehouse_id text NOT NULL,
  document_id uuid,
  action text NOT NULL,
  record jsonb NOT NULL,
  previous_hash text NOT NULL,
  hash text NOT NULL CHECK (hash ~ '^[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, sequence),
  UNIQUE (tenant_id, event_id),
  UNIQUE (tenant_id, hash)
);

CREATE TABLE IF NOT EXISTS inventory_outbox (
  tenant_id text NOT NULL,
  id uuid NOT NULL,
  aggregate_id uuid NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DELIVERED','DEAD')),
  attempts integer NOT NULL DEFAULT 0,
  available_at timestamptz NOT NULL DEFAULT now(),
  delivered_at timestamptz,
  PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS inventory_outbox_due_idx ON inventory_outbox(tenant_id, status, available_at);

CREATE OR REPLACE FUNCTION inventory_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$;
DROP TRIGGER IF EXISTS inventory_events_immutable ON inventory_events;
CREATE TRIGGER inventory_events_immutable BEFORE UPDATE OR DELETE ON inventory_events
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();
DROP TRIGGER IF EXISTS inventory_revisions_immutable ON inventory_revisions;
CREATE TRIGGER inventory_revisions_immutable BEFORE UPDATE OR DELETE ON inventory_revisions
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();
DROP TRIGGER IF EXISTS inventory_audit_immutable ON inventory_audit;
CREATE TRIGGER inventory_audit_immutable BEFORE UPDATE OR DELETE ON inventory_audit
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();

CREATE TABLE IF NOT EXISTS inventory_tenant_bindings (
  role_name name PRIMARY KEY,
  tenant_id text NOT NULL
);
REVOKE ALL ON inventory_tenant_bindings FROM PUBLIC;
CREATE OR REPLACE FUNCTION inventory_current_tenant() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
  SELECT tenant_id FROM public.inventory_tenant_bindings WHERE role_name=session_user
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'inventory_devices','inventory_device_activation_codes','inventory_device_nonces','inventory_documents','inventory_document_locations',
    'inventory_expected_stock','inventory_events','inventory_event_responses',
    'inventory_revisions','inventory_audit','inventory_outbox'
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

INSERT INTO inventory_schema_migrations(version,name) VALUES (3,'inventory production authority')
ON CONFLICT (version) DO NOTHING;
COMMIT;
