-- EAY Inventory v9: scope condition authority to Receiving without mutating frozen legacy intent.
-- Existing non-Receiving v8 rows may retain historical GOOD metadata, but new typed
-- Picking/Putaway/Transfer missions no longer need or mint a condition policy.
BEGIN;

ALTER TABLE inventory_operational_missions
  ALTER COLUMN allowed_conditions SET DEFAULT '[]'::jsonb;

ALTER TABLE inventory_operational_missions
  DROP CONSTRAINT IF EXISTS inventory_operational_intent_v8_check;
ALTER TABLE inventory_operational_missions
  ADD CONSTRAINT inventory_operational_intent_v8_check
  CHECK (
    intent_version=0
    OR (
      intent_version=1
      AND sku_id IS NOT NULL AND btrim(sku_id)<>''
      AND item_value_hash ~ '^[0-9a-f]{64}$'
      AND planned_quantity IS NOT NULL AND planned_quantity>0
      AND jsonb_typeof(allowed_conditions)='array'
      AND CASE mission_type
        WHEN 'PICKING' THEN source_location_id IS NOT NULL AND container_id IS NOT NULL
        WHEN 'PUTAWAY' THEN destination_location_id IS NOT NULL
        WHEN 'RECEIVING' THEN container_id IS NOT NULL
          AND jsonb_array_length(allowed_conditions)>0
        WHEN 'TRANSFER' THEN source_location_id IS NOT NULL
          AND destination_location_id IS NOT NULL
          AND source_location_id<>destination_location_id
        ELSE false
      END
    )
  );

INSERT INTO inventory_schema_migrations(version,name)
VALUES(9,'inventory operational condition scope authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
