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
  CHECK (event_type IN ('SCAN','CORRECTION','UNEXPECTED_SKU','LOCATION_COMPLETE'));

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

-- One immutable completion per document/location. Recount requires a governed
-- new document/revision path instead of mutating or deleting accepted evidence.
CREATE UNIQUE INDEX IF NOT EXISTS inventory_location_completion_once_idx
  ON inventory_events (tenant_id, document_id, location_id)
  WHERE event_type='LOCATION_COMPLETE';

INSERT INTO inventory_schema_migrations(version,name)
VALUES (4,'inventory durable location completion')
ON CONFLICT (version) DO NOTHING;

COMMIT;
