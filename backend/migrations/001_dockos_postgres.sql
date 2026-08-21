BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS dockos;

CREATE TABLE IF NOT EXISTS dockos.schema_migrations (
  version text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dockos.tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_key text NOT NULL UNIQUE,
  display_name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dockos.suppliers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  supplier_key text NOT NULL,
  supplier_name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, supplier_key),
  UNIQUE (tenant_id, supplier_name)
);

CREATE TABLE IF NOT EXISTS dockos.distribution_centers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  dc_key text NOT NULL,
  warehouse_name text NOT NULL,
  timezone text NOT NULL DEFAULT 'Europe/Istanbul',
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, dc_key),
  UNIQUE (tenant_id, warehouse_name)
);

CREATE TABLE IF NOT EXISTS dockos.supplier_access (
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  subject_id text NOT NULL,
  email text NOT NULL,
  supplier_id uuid NOT NULL REFERENCES dockos.suppliers(id) ON DELETE CASCADE,
  dc_id uuid REFERENCES dockos.distribution_centers(id) ON DELETE CASCADE,
  all_dcs boolean NOT NULL DEFAULT false,
  locale text NOT NULL DEFAULT 'tr' CHECK (locale IN ('tr','en','de','ar')),
  active boolean NOT NULL DEFAULT true,
  updated_by text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  access_key text GENERATED ALWAYS AS (subject_id || '|' || supplier_id::text || '|' || COALESCE(dc_id::text, '*')) STORED,
  PRIMARY KEY (tenant_id, access_key),
  CHECK ((all_dcs AND dc_id IS NULL) OR (NOT all_dcs AND dc_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS supplier_access_email_idx ON dockos.supplier_access (tenant_id, lower(email)) WHERE active;

CREATE TABLE IF NOT EXISTS dockos.purchase_orders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  po_number text NOT NULL,
  supplier_id uuid NOT NULL REFERENCES dockos.suppliers(id),
  dc_id uuid NOT NULL REFERENCES dockos.distribution_centers(id),
  supplier_external_id text,
  created_date date,
  promised_date date,
  order_status text NOT NULL,
  dockos_status text NOT NULL DEFAULT 'OPEN' CHECK (dockos_status IN ('OPEN','RESERVED','CLOSED','CANCELLED')),
  total_sku integer NOT NULL DEFAULT 0 CHECK (total_sku >= 0),
  pallet_count integer NOT NULL DEFAULT 0 CHECK (pallet_count >= 0),
  source text NOT NULL,
  source_identity text,
  raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, po_number)
);
CREATE INDEX IF NOT EXISTS po_supplier_dc_status_idx ON dockos.purchase_orders (tenant_id, supplier_id, dc_id, dockos_status);

CREATE TABLE IF NOT EXISTS dockos.slot_capacity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  dc_id uuid NOT NULL REFERENCES dockos.distribution_centers(id) ON DELETE CASCADE,
  slot_date date NOT NULL,
  slot_start time NOT NULL,
  slot_end time NOT NULL,
  max_pallet integer NOT NULL CHECK (max_pallet >= 0),
  max_sku integer NOT NULL CHECK (max_sku >= 0),
  blocked boolean NOT NULL DEFAULT false,
  version bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text,
  UNIQUE (tenant_id, dc_id, slot_date, slot_start, slot_end),
  CHECK (slot_start <> slot_end)
);

CREATE TABLE IF NOT EXISTS dockos.supplier_slot_capacity (
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  slot_id uuid NOT NULL REFERENCES dockos.slot_capacity(id) ON DELETE CASCADE,
  supplier_id uuid NOT NULL REFERENCES dockos.suppliers(id) ON DELETE CASCADE,
  reserved_pallet integer NOT NULL DEFAULT 0 CHECK (reserved_pallet >= 0),
  reserved_sku integer NOT NULL DEFAULT 0 CHECK (reserved_sku >= 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text,
  PRIMARY KEY (tenant_id, slot_id, supplier_id)
);

CREATE TABLE IF NOT EXISTS dockos.supplier_daily_limits (
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  dc_id uuid NOT NULL REFERENCES dockos.distribution_centers(id) ON DELETE CASCADE,
  supplier_id uuid NOT NULL REFERENCES dockos.suppliers(id) ON DELETE CASCADE,
  limit_date date NOT NULL,
  max_pallet integer NOT NULL CHECK (max_pallet >= 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text,
  PRIMARY KEY (tenant_id, dc_id, supplier_id, limit_date)
);

CREATE TABLE IF NOT EXISTS dockos.reservations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  reservation_no text NOT NULL,
  supplier_id uuid NOT NULL REFERENCES dockos.suppliers(id),
  dc_id uuid NOT NULL REFERENCES dockos.distribution_centers(id),
  shipment_mode text NOT NULL CHECK (shipment_mode IN ('SEVKIYAT','KARGO')),
  slot_id uuid REFERENCES dockos.slot_capacity(id),
  slot_date date NOT NULL,
  selected_slot text NOT NULL,
  pallet_count integer NOT NULL DEFAULT 0 CHECK (pallet_count >= 0),
  sku_count integer NOT NULL DEFAULT 0 CHECK (sku_count >= 0),
  shipment_details text NOT NULL DEFAULT '',
  waybill_info text,
  shipment_form text,
  box_count integer,
  vehicle_type text,
  vehicle_count integer,
  vehicle_plate text NOT NULL DEFAULT '',
  cargo_tracking_no text NOT NULL DEFAULT '',
  reservation_user text,
  contact_email text,
  status text NOT NULL DEFAULT 'APPROVED',
  status_note text NOT NULL DEFAULT '',
  dc_task_status text NOT NULL,
  arrival_check jsonb NOT NULL DEFAULT '{"arrived":null,"dock_compatible":null,"on_time":null,"ramp_no":"","note":""}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  cancelled_at timestamptz,
  version bigint NOT NULL DEFAULT 0,
  UNIQUE (tenant_id, reservation_no)
);
CREATE INDEX IF NOT EXISTS reservations_capacity_idx ON dockos.reservations (tenant_id, dc_id, slot_date, slot_id, status);
CREATE INDEX IF NOT EXISTS reservations_supplier_date_idx ON dockos.reservations (tenant_id, supplier_id, slot_date, status);

CREATE TABLE IF NOT EXISTS dockos.reservation_purchase_orders (
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  reservation_id uuid NOT NULL REFERENCES dockos.reservations(id) ON DELETE CASCADE,
  purchase_order_id uuid NOT NULL REFERENCES dockos.purchase_orders(id),
  PRIMARY KEY (tenant_id, reservation_id, purchase_order_id),
  UNIQUE (tenant_id, purchase_order_id)
);

CREATE TABLE IF NOT EXISTS dockos.notification_outbox (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  reservation_id uuid REFERENCES dockos.reservations(id) ON DELETE CASCADE,
  idempotency_key text NOT NULL,
  event_type text NOT NULL,
  due_at timestamptz NOT NULL,
  recipients jsonb NOT NULL,
  subject text NOT NULL,
  html text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','SENDING','SENT','FAILED','WAITING_CONFIG','CANCELLED','DEAD')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  next_attempt_at timestamptz,
  locked_at timestamptz,
  locked_by text,
  sent_at timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS notification_due_idx ON dockos.notification_outbox (tenant_id, status, due_at);

CREATE TABLE IF NOT EXISTS dockos.audit_events (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_subject text NOT NULL,
  actor_email text,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  request_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_tenant_time_idx ON dockos.audit_events (tenant_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS dockos.settings (
  tenant_id uuid NOT NULL REFERENCES dockos.tenants(id) ON DELETE CASCADE,
  key text NOT NULL,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text,
  PRIMARY KEY (tenant_id, key)
);

CREATE OR REPLACE FUNCTION dockos.current_tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('dockos.tenant_id', true), '')::uuid $$;

ALTER TABLE dockos.suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.distribution_centers ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.supplier_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.slot_capacity ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.supplier_slot_capacity ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.supplier_daily_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.reservation_purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.notification_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE dockos.settings ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['suppliers','distribution_centers','supplier_access','purchase_orders','slot_capacity','supplier_slot_capacity','supplier_daily_limits','reservations','reservation_purchase_orders','notification_outbox','audit_events','settings'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='dockos' AND tablename=t AND policyname='tenant_isolation') THEN
      EXECUTE format('CREATE POLICY tenant_isolation ON dockos.%I USING (tenant_id = dockos.current_tenant_id()) WITH CHECK (tenant_id = dockos.current_tenant_id())', t);
    END IF;
  END LOOP;
END $$;

INSERT INTO dockos.schema_migrations(version) VALUES ('001_dockos_postgres') ON CONFLICT DO NOTHING;
COMMIT;
