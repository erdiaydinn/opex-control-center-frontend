-- EAY Inventory v6: immutable, versioned recount evidence.
BEGIN;

ALTER TABLE inventory_events
  ADD COLUMN IF NOT EXISTS count_version integer NOT NULL DEFAULT 1;
ALTER TABLE inventory_events
  ADD COLUMN IF NOT EXISTS supersedes_event_id uuid;
ALTER TABLE inventory_events
  ADD COLUMN IF NOT EXISTS recount_reason_code text;

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_event_type_v4_check;
ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_event_type_v6_check;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_event_type_v6_check
  CHECK (event_type IN ('SCAN','CORRECTION','UNEXPECTED_SKU','RECOUNT','LOCATION_COMPLETE'));

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_recount_shape_v6;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_recount_shape_v6
  CHECK (
    (
      event_type='RECOUNT'
      AND count_version > 1
      AND supersedes_event_id IS NOT NULL
      AND recount_reason_code IN (
        'OPERATOR_CORRECTION','SUPERVISOR_REQUEST','DEVICE_RECOVERY','VARIANCE_REVIEW'
      )
    )
    OR
    (
      event_type<>'RECOUNT'
      AND count_version=1
      AND supersedes_event_id IS NULL
      AND recount_reason_code IS NULL
    )
  );

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_recount_predecessor_v6_fk;
ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_recount_predecessor_v6_fk
  FOREIGN KEY (tenant_id, supersedes_event_id)
  REFERENCES inventory_events(tenant_id, event_id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX IF NOT EXISTS inventory_recount_one_successor_v6_idx
  ON inventory_events(tenant_id, supersedes_event_id)
  WHERE supersedes_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS inventory_count_line_version_v6_idx
  ON inventory_events(tenant_id,attempt_id,location_id,barcode,count_version)
  WHERE event_type IN ('SCAN','UNEXPECTED_SKU','RECOUNT');

CREATE OR REPLACE FUNCTION inventory_guard_recount_v6() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  predecessor inventory_events%ROWTYPE;
BEGIN
  IF NEW.event_type<>'RECOUNT' THEN
    RETURN NEW;
  END IF;
  SELECT * INTO predecessor
    FROM inventory_events
   WHERE tenant_id=NEW.tenant_id AND event_id=NEW.supersedes_event_id
   FOR SHARE;
  IF NOT FOUND
     OR predecessor.document_id<>NEW.document_id
     OR predecessor.attempt_id<>NEW.attempt_id
     OR predecessor.lease_id<>NEW.lease_id
     OR predecessor.active_shift_id<>NEW.active_shift_id
     OR predecessor.location_id<>NEW.location_id
     OR predecessor.barcode<>NEW.barcode
     OR predecessor.count_version+1<>NEW.count_version THEN
    RAISE EXCEPTION 'Inventory recount predecessor binding is invalid.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_recount_v6_trigger ON inventory_events;
CREATE TRIGGER inventory_guard_recount_v6_trigger
BEFORE INSERT ON inventory_events
FOR EACH ROW EXECUTE FUNCTION inventory_guard_recount_v6();

INSERT INTO inventory_schema_migrations(version,name)
VALUES (6,'inventory immutable recount chain')
ON CONFLICT (version) DO NOTHING;

COMMIT;
