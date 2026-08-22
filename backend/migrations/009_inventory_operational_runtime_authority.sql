-- EAY Inventory v9: runtime authority hardening for Picking, Putaway, Receiving and Transfer.
-- Adds lifecycle guards, immutable replay responses and transactional recovery of
-- operational claims when a managed device is replaced. Historical step evidence
-- remains immutable and is never rebound to the replacement device.
BEGIN;

ALTER TABLE inventory_operational_missions
  ALTER COLUMN allowed_conditions SET DEFAULT '[]'::jsonb;

ALTER TABLE inventory_operational_missions
  DROP CONSTRAINT IF EXISTS inventory_operational_intent_v8_check;
ALTER TABLE inventory_operational_missions
  DROP CONSTRAINT IF EXISTS inventory_operational_intent_v9_check;
ALTER TABLE inventory_operational_missions
  ADD CONSTRAINT inventory_operational_intent_v9_check
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

ALTER TABLE inventory_operational_claims
  ADD COLUMN IF NOT EXISTS release_reason text;

ALTER TABLE inventory_operational_claims
  DROP CONSTRAINT IF EXISTS inventory_operational_claim_release_v9_check;
ALTER TABLE inventory_operational_claims
  ADD CONSTRAINT inventory_operational_claim_release_v9_check
  CHECK (
    (released_at IS NULL AND release_reason IS NULL)
    OR (released_at IS NOT NULL AND release_reason IS NOT NULL AND btrim(release_reason)<>'')
  );

CREATE OR REPLACE FUNCTION inventory_guard_operational_claim_v9() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'Operational claim history is append-only.';
  END IF;

  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.claim_id IS DISTINCT FROM NEW.claim_id
     OR OLD.mission_id IS DISTINCT FROM NEW.mission_id
     OR OLD.employee_id IS DISTINCT FROM NEW.employee_id
     OR OLD.device_id IS DISTINCT FROM NEW.device_id
     OR OLD.shift_id IS DISTINCT FROM NEW.shift_id
     OR OLD.claimed_at IS DISTINCT FROM NEW.claimed_at THEN
    RAISE EXCEPTION 'Operational claim identity is immutable.';
  END IF;

  IF OLD.released_at IS NOT NULL THEN
    RAISE EXCEPTION 'Released operational claim cannot be changed.';
  END IF;

  IF NEW.released_at IS NULL THEN
    IF NEW.release_reason IS NOT NULL THEN
      RAISE EXCEPTION 'Release reason requires released_at.';
    END IF;
  ELSE
    IF NEW.release_reason IS NULL OR btrim(NEW.release_reason)='' THEN
      NEW.release_reason := 'MISSION_COMPLETED';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_operational_claim_v9_guard
  ON inventory_operational_claims;
CREATE TRIGGER inventory_operational_claim_v9_guard
BEFORE UPDATE OR DELETE ON inventory_operational_claims
FOR EACH ROW EXECUTE FUNCTION inventory_guard_operational_claim_v9();

DROP TRIGGER IF EXISTS inventory_operational_responses_immutable
  ON inventory_operational_event_responses;
CREATE TRIGGER inventory_operational_responses_immutable
BEFORE UPDATE OR DELETE ON inventory_operational_event_responses
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();

CREATE OR REPLACE FUNCTION inventory_release_operational_claims_on_device_replacement_v9()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status='ACTIVE' AND NEW.status='REPLACED' THEN
    WITH released AS (
      UPDATE inventory_operational_claims c
         SET released_at=COALESCE(NEW.revoked_at,now()),
             release_reason='DEVICE_REPLACED'
       WHERE c.tenant_id=OLD.tenant_id
         AND c.device_id=OLD.device_id
         AND c.released_at IS NULL
       RETURNING c.tenant_id,c.mission_id
    )
    UPDATE inventory_operational_missions m
       SET state='OPEN'
     WHERE m.tenant_id=OLD.tenant_id
       AND m.state='CLAIMED'
       AND m.completed_at IS NULL
       AND EXISTS (
         SELECT 1 FROM released r
          WHERE r.tenant_id=m.tenant_id AND r.mission_id=m.mission_id
       );
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_device_operational_recovery_v9
  ON inventory_devices;
CREATE TRIGGER inventory_device_operational_recovery_v9
AFTER UPDATE OF status,replaced_by,revoked_at ON inventory_devices
FOR EACH ROW EXECUTE FUNCTION inventory_release_operational_claims_on_device_replacement_v9();

INSERT INTO inventory_schema_migrations(version,name)
VALUES(9,'inventory operational runtime authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
