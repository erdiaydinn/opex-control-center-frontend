-- EAY Inventory v10: make managed-device replacement recovery atomically reopen
-- every operational mission whose live claim was released by the replacement.
--
-- v9 correctly made claim release append-only and device-bound, but its
-- data-modifying CTE could leave the mission row CLAIMED even though the claim
-- was already released. v10 keeps v9 immutable history intact and replaces only
-- the trigger implementation. Historical operational events/responses are never
-- rewritten or rebound.
BEGIN;

CREATE OR REPLACE FUNCTION inventory_release_operational_claims_on_device_replacement_v10()
RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  affected_mission_id uuid;
BEGIN
  IF OLD.status='ACTIVE' AND NEW.status='REPLACED' THEN
    FOR affected_mission_id IN
      UPDATE inventory_operational_claims c
         SET released_at=COALESCE(NEW.revoked_at,now()),
             release_reason='DEVICE_REPLACED'
       WHERE c.tenant_id=OLD.tenant_id
         AND c.device_id=OLD.device_id
         AND c.released_at IS NULL
       RETURNING c.mission_id
    LOOP
      UPDATE inventory_operational_missions m
         SET state='OPEN'
       WHERE m.tenant_id=OLD.tenant_id
         AND m.mission_id=affected_mission_id
         AND m.state='CLAIMED'
         AND m.completed_at IS NULL;

      IF NOT FOUND THEN
        RAISE EXCEPTION
          'Released operational claim could not reopen its active mission: %',
          affected_mission_id;
      END IF;
    END LOOP;
  END IF;
  RETURN NEW;
END;
$$;

-- Preserve the public trigger contract/name introduced by v9 while swapping its
-- implementation forward-only. Existing static/schema acceptance therefore keeps
-- proving one canonical device-recovery trigger rather than a parallel authority.
DROP TRIGGER IF EXISTS inventory_device_operational_recovery_v10
  ON inventory_devices;
DROP TRIGGER IF EXISTS inventory_device_operational_recovery_v9
  ON inventory_devices;
CREATE TRIGGER inventory_device_operational_recovery_v9
AFTER UPDATE OF status,replaced_by,revoked_at ON inventory_devices
FOR EACH ROW EXECUTE FUNCTION inventory_release_operational_claims_on_device_replacement_v10();

INSERT INTO inventory_schema_migrations(version,name)
VALUES(10,'inventory operational device recovery atomicity')
ON CONFLICT (version) DO NOTHING;

COMMIT;
