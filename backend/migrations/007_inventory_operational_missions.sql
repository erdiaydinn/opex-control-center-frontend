-- EAY Inventory v7: server authority for Picking, Putaway, Receiving and Transfer.
BEGIN;

CREATE TABLE IF NOT EXISTS inventory_operational_missions (
  tenant_id text NOT NULL,
  mission_id uuid NOT NULL,
  warehouse_id text NOT NULL,
  mission_type text NOT NULL CHECK (mission_type IN ('PICKING','PUTAWAY','RECEIVING','TRANSFER')),
  operation text NOT NULL,
  external_reference text NOT NULL,
  steps jsonb NOT NULL CHECK (jsonb_typeof(steps)='array' AND jsonb_array_length(steps)>0),
  state text NOT NULL DEFAULT 'OPEN' CHECK (state IN ('OPEN','CLAIMED','COMPLETED','CANCELLED')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  PRIMARY KEY (tenant_id,mission_id),
  UNIQUE (tenant_id,warehouse_id,mission_type,external_reference),
  CHECK ((state='COMPLETED')=(completed_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS inventory_operational_claims (
  tenant_id text NOT NULL,
  claim_id uuid NOT NULL,
  mission_id uuid NOT NULL,
  employee_id text NOT NULL,
  device_id uuid NOT NULL,
  shift_id text NOT NULL,
  claimed_at timestamptz NOT NULL DEFAULT now(),
  released_at timestamptz,
  PRIMARY KEY (tenant_id,claim_id),
  FOREIGN KEY (tenant_id,mission_id) REFERENCES inventory_operational_missions(tenant_id,mission_id),
  FOREIGN KEY (tenant_id,device_id) REFERENCES inventory_devices(tenant_id,device_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS inventory_operational_one_live_claim
  ON inventory_operational_claims(tenant_id,mission_id) WHERE released_at IS NULL;

CREATE TABLE IF NOT EXISTS inventory_operational_events (
  tenant_id text NOT NULL,
  event_id uuid NOT NULL,
  mission_id uuid NOT NULL,
  claim_id uuid NOT NULL,
  employee_id text NOT NULL,
  device_id uuid NOT NULL,
  shift_id text NOT NULL,
  device_sequence bigint NOT NULL CHECK (device_sequence>0),
  step_index integer NOT NULL CHECK (step_index>=0),
  step_kind text NOT NULL CHECK (step_kind IN ('SOURCE_LOCATION','DESTINATION_LOCATION','ITEM','QUANTITY','CONDITION','CONTAINER','COMPLETE')),
  value_hash text NOT NULL CHECK (value_hash ~ '^[0-9a-f]{64}$'),
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id,event_id),
  UNIQUE (tenant_id,device_id,device_sequence),
  UNIQUE (tenant_id,mission_id,step_index),
  FOREIGN KEY (tenant_id,mission_id) REFERENCES inventory_operational_missions(tenant_id,mission_id),
  FOREIGN KEY (tenant_id,claim_id) REFERENCES inventory_operational_claims(tenant_id,claim_id)
);

CREATE TABLE IF NOT EXISTS inventory_operational_event_responses (
  tenant_id text NOT NULL,
  event_id uuid NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id,event_id),
  FOREIGN KEY (tenant_id,event_id) REFERENCES inventory_operational_events(tenant_id,event_id)
);

DROP TRIGGER IF EXISTS inventory_operational_events_immutable ON inventory_operational_events;
CREATE TRIGGER inventory_operational_events_immutable BEFORE UPDATE OR DELETE
ON inventory_operational_events FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();

ALTER TABLE inventory_operational_missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_operational_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_operational_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_operational_event_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_operational_missions FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_operational_claims FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_operational_events FORCE ROW LEVEL SECURITY;
ALTER TABLE inventory_operational_event_responses FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operational_missions_tenant ON inventory_operational_missions;
DROP POLICY IF EXISTS operational_claims_tenant ON inventory_operational_claims;
DROP POLICY IF EXISTS operational_events_tenant ON inventory_operational_events;
DROP POLICY IF EXISTS operational_responses_tenant ON inventory_operational_event_responses;
CREATE POLICY operational_missions_tenant ON inventory_operational_missions USING (tenant_id=inventory_current_tenant()) WITH CHECK (tenant_id=inventory_current_tenant());
CREATE POLICY operational_claims_tenant ON inventory_operational_claims USING (tenant_id=inventory_current_tenant()) WITH CHECK (tenant_id=inventory_current_tenant());
CREATE POLICY operational_events_tenant ON inventory_operational_events USING (tenant_id=inventory_current_tenant()) WITH CHECK (tenant_id=inventory_current_tenant());
CREATE POLICY operational_responses_tenant ON inventory_operational_event_responses USING (tenant_id=inventory_current_tenant()) WITH CHECK (tenant_id=inventory_current_tenant());

INSERT INTO inventory_schema_migrations(version,name) VALUES(7,'inventory operational mission authority') ON CONFLICT DO NOTHING;
COMMIT;
