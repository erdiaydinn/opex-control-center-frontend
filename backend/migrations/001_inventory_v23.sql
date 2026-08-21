BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS opex_warehouses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  server_group text NOT NULL DEFAULT 'primary',
  active boolean NOT NULL DEFAULT true,
  UNIQUE(company_id, code)
);
CREATE TABLE IF NOT EXISTS opex_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL,
  username text NOT NULL,
  display_name text NOT NULL,
  password_hash text NOT NULL,
  roles text[] NOT NULL,
  active boolean NOT NULL DEFAULT true,
  token_version integer NOT NULL DEFAULT 1,
  UNIQUE(company_id, username)
);
CREATE TABLE IF NOT EXISTS opex_user_warehouses (
  user_id uuid NOT NULL REFERENCES opex_users(id) ON DELETE CASCADE,
  warehouse_id uuid NOT NULL REFERENCES opex_warehouses(id) ON DELETE CASCADE,
  PRIMARY KEY(user_id, warehouse_id)
);
CREATE TABLE IF NOT EXISTS inventory_documents_v23 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL,
  warehouse_id uuid NOT NULL REFERENCES opex_warehouses(id),
  campaign_id uuid NOT NULL,
  status text NOT NULL CHECK(status IN ('DRAFT','COUNTING','RECOUNT','APPROVAL','APPROVED','CLOSED')),
  snapshot_at timestamptz NOT NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS inventory_events_v23 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_event_id uuid NOT NULL,
  company_id uuid NOT NULL,
  warehouse_id uuid NOT NULL REFERENCES opex_warehouses(id),
  document_id uuid NOT NULL REFERENCES inventory_documents_v23(id),
  user_id uuid NOT NULL REFERENCES opex_users(id),
  device_id text NOT NULL,
  location_id text NOT NULL,
  sku text NOT NULL,
  quantity numeric(18,3) NOT NULL CHECK(quantity >= 0),
  occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(document_id, client_event_id)
) PARTITION BY HASH (warehouse_id);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p0 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 0);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p1 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 1);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p2 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 2);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p3 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 3);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p4 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 4);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p5 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 5);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p6 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 6);
CREATE TABLE IF NOT EXISTS inventory_events_v23_p7 PARTITION OF inventory_events_v23 FOR VALUES WITH (MODULUS 8, REMAINDER 7);
CREATE INDEX IF NOT EXISTS inventory_events_document_location ON inventory_events_v23(document_id, location_id);
CREATE INDEX IF NOT EXISTS inventory_events_received_at ON inventory_events_v23(received_at);

ALTER TABLE opex_warehouses ENABLE ROW LEVEL SECURITY;
ALTER TABLE opex_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_documents_v23 ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_events_v23 ENABLE ROW LEVEL SECURITY;
ALTER TABLE opex_warehouses FORCE ROW LEVEL SECURITY;
ALTER TABLE opex_users FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_documents_v23 FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_events_v23 FORCE ROW LEVEL SECURITY;

CREATE POLICY warehouse_company_scope ON opex_warehouses
  USING (company_id = nullif(current_setting('opex.company_id', true), '')::uuid);
CREATE POLICY user_company_scope ON opex_users
  USING (company_id = nullif(current_setting('opex.company_id', true), '')::uuid);
CREATE POLICY document_warehouse_scope ON inventory_documents_v23
  USING (
    company_id = nullif(current_setting('opex.company_id', true), '')::uuid
    AND (
      current_setting('opex.is_global_admin', true) = 'true'
      OR warehouse_id::text = ANY(string_to_array(current_setting('opex.warehouse_ids', true), ','))
    )
  );
CREATE POLICY event_warehouse_scope ON inventory_events_v23
  USING (
    company_id = nullif(current_setting('opex.company_id', true), '')::uuid
    AND (
      current_setting('opex.is_global_admin', true) = 'true'
      OR warehouse_id::text = ANY(string_to_array(current_setting('opex.warehouse_ids', true), ','))
    )
  );
COMMIT;
