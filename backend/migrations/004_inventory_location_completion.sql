-- EAY Inventory v4: durable location-completion events.
-- A location completion is an operational event, not a synthetic barcode/SKU.
BEGIN;

ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_event_type_check;
ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_quantity_check;
ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_event_type_v4_check;
ALTER TABLE inventory_events
  DROP CONSTRAINT IF EXISTS inventory_events_payload_v4_check;

ALTER TABLE inventory_events ALTER COLUMN barcode DROP NOT NULL;
ALTER TABLE inventory_events ALTER COLUMN quantity DROP NOT NULL;
ALTER TABLE inventory_events ALTER COLUMN symbology DROP NOT NULL;

ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_event_type_v4_check
  CHECK (event_type IN ('SCAN','CORRECTION','UNEXPECTED_SKU','RECOUNT','LOCATION_COMPLETE'));

ALTER TABLE inventory_events
  ADD CONSTRAINT inventory_events_payload_v4_check
  CHECK (
    (
      event_type='LOCATION_COMPLETE'
      AND barcode IS NULL
      AND quantity IS NULL
      AND symbology IS NULL
    )
    OR
    (
      event_type<>'LOCATION_COMPLETE'
      AND barcode IS NOT NULL
      AND quantity IS NOT NULL
      AND quantity >= 0
      AND symbology IS NOT NULL
    )
  );

-- Completion state is anchored to the authoritative document/location row. The
-- event trigger below locks this row for every count/completion insert, which
-- serializes a completion against concurrent scans for the same physical location.
ALTER TABLE inventory_document_locations
  ADD COLUMN IF NOT EXISTS completed_event_id uuid;
ALTER TABLE inventory_document_locations
  ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE inventory_document_locations
  DROP CONSTRAINT IF EXISTS inventory_document_locations_completion_pair_v4;
ALTER TABLE inventory_document_locations
  ADD CONSTRAINT inventory_document_locations_completion_pair_v4
  CHECK (
    (completed_event_id IS NULL AND completed_at IS NULL)
    OR
    (completed_event_id IS NOT NULL AND completed_at IS NOT NULL)
  );

CREATE UNIQUE INDEX IF NOT EXISTS inventory_document_location_completed_event_idx
  ON inventory_document_locations (tenant_id, completed_event_id)
  WHERE completed_event_id IS NOT NULL;

CREATE OR REPLACE FUNCTION inventory_guard_location_event_v4() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  completion_event uuid;
BEGIN
  SELECT completed_event_id
    INTO completion_event
    FROM inventory_document_locations
   WHERE tenant_id=NEW.tenant_id
     AND document_id=NEW.document_id
     AND location_id=NEW.location_id
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Inventory event location is outside the document scope.';
  END IF;

  IF NEW.event_type='LOCATION_COMPLETE' THEN
    IF completion_event IS NOT NULL THEN
      RAISE EXCEPTION 'Inventory location is already completed.';
    END IF;
    UPDATE inventory_document_locations
       SET completed_event_id=NEW.event_id,
           completed_at=NEW.occurred_at
     WHERE tenant_id=NEW.tenant_id
       AND document_id=NEW.document_id
       AND location_id=NEW.location_id;
  ELSIF completion_event IS NOT NULL THEN
    RAISE EXCEPTION 'Inventory location is completed; new count events are forbidden.';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_location_event_v4_trigger ON inventory_events;
CREATE TRIGGER inventory_guard_location_event_v4_trigger
BEFORE INSERT ON inventory_events
FOR EACH ROW EXECUTE FUNCTION inventory_guard_location_event_v4();

-- One immutable completion per document/location. Recount requires a governed
-- new document/revision path instead of mutating or deleting accepted evidence.
CREATE UNIQUE INDEX IF NOT EXISTS inventory_location_completion_once_idx
  ON inventory_events (tenant_id, document_id, location_id)
  WHERE event_type='LOCATION_COMPLETE';

INSERT INTO inventory_schema_migrations(version,name)
VALUES (4,'inventory durable location completion')
ON CONFLICT (version) DO NOTHING;

COMMIT;
