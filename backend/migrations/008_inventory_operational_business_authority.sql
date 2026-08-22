-- EAY Inventory v8: typed business authority for Picking, Putaway, Receiving and Transfer.
-- Existing v7 missions remain readable/auditable but fail closed for new execution
-- until recreated with intent_version=1.
--
-- Replay compatibility: later runtime authority permits an empty condition set for
-- non-Receiving missions while Receiving still requires explicit condition policy.
-- Keep this historical migration replay-safe with that stronger final contract so
-- a full migration replay never rejects rows that are valid under v9+ authority.
BEGIN;

ALTER TABLE inventory_operational_missions
  ADD COLUMN IF NOT EXISTS intent_version smallint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS sku_id text,
  ADD COLUMN IF NOT EXISTS item_value_hash text,
  ADD COLUMN IF NOT EXISTS planned_quantity numeric(18,3),
  ADD COLUMN IF NOT EXISTS source_location_id text,
  ADD COLUMN IF NOT EXISTS destination_location_id text,
  ADD COLUMN IF NOT EXISTS container_id text,
  ADD COLUMN IF NOT EXISTS allowed_conditions jsonb NOT NULL DEFAULT '["GOOD"]'::jsonb,
  ADD COLUMN IF NOT EXISTS actual_quantity numeric(18,3),
  ADD COLUMN IF NOT EXISTS condition_code text,
  ADD COLUMN IF NOT EXISTS reconciliation_state text,
  ADD COLUMN IF NOT EXISTS result_hash text,
  ADD COLUMN IF NOT EXISTS reconciled_at timestamptz;

ALTER TABLE inventory_operational_events
  ADD COLUMN IF NOT EXISTS contract_version smallint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS safe_value text,
  ADD COLUMN IF NOT EXISTS numeric_value numeric(18,3);

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
        WHEN 'PICKING' THEN source_location_id IS NOT NULL
          AND container_id IS NOT NULL
          AND allowed_conditions <@ '["GOOD"]'::jsonb
        WHEN 'PUTAWAY' THEN destination_location_id IS NOT NULL
          AND allowed_conditions <@ '["GOOD"]'::jsonb
        WHEN 'RECEIVING' THEN container_id IS NOT NULL
          AND jsonb_array_length(allowed_conditions)>0
        WHEN 'TRANSFER' THEN source_location_id IS NOT NULL
          AND destination_location_id IS NOT NULL
          AND source_location_id<>destination_location_id
          AND allowed_conditions <@ '["GOOD"]'::jsonb
        ELSE false
      END
    )
  );

ALTER TABLE inventory_operational_missions
  DROP CONSTRAINT IF EXISTS inventory_operational_result_v8_check;
ALTER TABLE inventory_operational_missions
  ADD CONSTRAINT inventory_operational_result_v8_check
  CHECK (
    (
      reconciliation_state IS NULL
      AND result_hash IS NULL
      AND reconciled_at IS NULL
      AND actual_quantity IS NULL
    )
    OR (
      state='COMPLETED'
      AND reconciliation_state IN ('AUTO_RECONCILED','REVIEW_REQUIRED')
      AND result_hash ~ '^[0-9a-f]{64}$'
      AND reconciled_at IS NOT NULL
      AND actual_quantity IS NOT NULL
      AND actual_quantity>=0
    )
  );

ALTER TABLE inventory_operational_events
  DROP CONSTRAINT IF EXISTS inventory_operational_event_fact_v8_check;
ALTER TABLE inventory_operational_events
  ADD CONSTRAINT inventory_operational_event_fact_v8_check
  CHECK (
    contract_version=0
    OR (
      contract_version=1
      AND (
        (step_kind='QUANTITY' AND numeric_value IS NOT NULL AND numeric_value>=0 AND safe_value IS NULL)
        OR
        (step_kind<>'QUANTITY' AND numeric_value IS NULL AND safe_value IS NOT NULL AND btrim(safe_value)<>'')
      )
    )
  );

CREATE OR REPLACE FUNCTION inventory_guard_operational_intent_v8() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.intent_version=1 AND (
       NEW.intent_version IS DISTINCT FROM OLD.intent_version
    OR NEW.sku_id IS DISTINCT FROM OLD.sku_id
    OR NEW.item_value_hash IS DISTINCT FROM OLD.item_value_hash
    OR NEW.planned_quantity IS DISTINCT FROM OLD.planned_quantity
    OR NEW.source_location_id IS DISTINCT FROM OLD.source_location_id
    OR NEW.destination_location_id IS DISTINCT FROM OLD.destination_location_id
    OR NEW.container_id IS DISTINCT FROM OLD.container_id
    OR NEW.allowed_conditions IS DISTINCT FROM OLD.allowed_conditions
  ) THEN
    RAISE EXCEPTION 'Operational mission intent is immutable.';
  END IF;

  IF NEW.intent_version=1 AND NEW.state='COMPLETED'
     AND NEW.reconciliation_state IS NULL THEN
    RAISE EXCEPTION 'Typed operational mission cannot complete without reconciliation result.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_operational_intent_v8_guard
  ON inventory_operational_missions;
CREATE TRIGGER inventory_operational_intent_v8_guard
BEFORE UPDATE ON inventory_operational_missions
FOR EACH ROW EXECUTE FUNCTION inventory_guard_operational_intent_v8();

CREATE OR REPLACE FUNCTION inventory_guard_operational_event_v8() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  mission inventory_operational_missions%ROWTYPE;
BEGIN
  IF NEW.contract_version=0 THEN
    RETURN NEW;
  END IF;

  SELECT * INTO mission
    FROM inventory_operational_missions
   WHERE tenant_id=NEW.tenant_id AND mission_id=NEW.mission_id
   FOR SHARE;

  IF NOT FOUND OR mission.intent_version<>1 THEN
    RAISE EXCEPTION 'Typed operational event requires typed mission intent.';
  END IF;

  IF NEW.step_kind='ITEM' AND NEW.safe_value<>mission.sku_id THEN
    RAISE EXCEPTION 'Operational ITEM fact does not match frozen SKU.';
  ELSIF NEW.step_kind='SOURCE_LOCATION'
        AND NEW.safe_value IS DISTINCT FROM mission.source_location_id THEN
    RAISE EXCEPTION 'Operational source location does not match intent.';
  ELSIF NEW.step_kind='DESTINATION_LOCATION'
        AND NEW.safe_value IS DISTINCT FROM mission.destination_location_id THEN
    RAISE EXCEPTION 'Operational destination location does not match intent.';
  ELSIF NEW.step_kind='CONTAINER'
        AND NEW.safe_value IS DISTINCT FROM mission.container_id THEN
    RAISE EXCEPTION 'Operational container does not match intent.';
  ELSIF NEW.step_kind='CONDITION'
        AND NOT (mission.allowed_conditions ? NEW.safe_value) THEN
    RAISE EXCEPTION 'Operational condition is outside mission policy.';
  ELSIF NEW.step_kind='COMPLETE' AND NEW.safe_value<>'COMPLETE' THEN
    RAISE EXCEPTION 'Operational completion fact is invalid.';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_operational_event_v8_guard
  ON inventory_operational_events;
CREATE TRIGGER inventory_operational_event_v8_guard
BEFORE INSERT ON inventory_operational_events
FOR EACH ROW EXECUTE FUNCTION inventory_guard_operational_event_v8();

INSERT INTO inventory_schema_migrations(version,name)
VALUES(8,'inventory typed operational business authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
