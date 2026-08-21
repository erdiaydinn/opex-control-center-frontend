-- EAY Inventory v13: wall-to-wall one-operator/one-location and Lost & Found-last authority.
-- Existing inventory_documents / locations / mission attempts / leases remain canonical.
-- No competing campaign, assignment master or client-owned authority is introduced.
BEGIN;

-- LOST_FOUND is a reserved canonical physical-location id. The classification is
-- derived, not client supplied, so a terminal cannot relabel an ordinary
-- location to bypass ordering. Existing rows are backfilled by PostgreSQL.
ALTER TABLE inventory_document_locations
  ADD COLUMN IF NOT EXISTS location_kind text
  GENERATED ALWAYS AS (
    CASE WHEN location_id='LOST_FOUND' THEN 'LOST_FOUND' ELSE 'STANDARD' END
  ) STORED;

ALTER TABLE inventory_document_locations
  DROP CONSTRAINT IF EXISTS inventory_document_location_kind_v13;
ALTER TABLE inventory_document_locations
  ADD CONSTRAINT inventory_document_location_kind_v13
  CHECK (location_kind IN ('STANDARD','LOST_FOUND'));

-- A W2W document may expose at most one reserved Lost & Found mission.
CREATE UNIQUE INDEX IF NOT EXISTS inventory_document_one_lost_found_v13_idx
  ON inventory_document_locations (tenant_id, document_id)
  WHERE location_kind='LOST_FOUND';

-- Fail migration rather than silently grandfathering state that violates the
-- new Lost & Found ordering invariant.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM inventory_mission_attempts a
      JOIN inventory_document_locations lf
        ON lf.tenant_id=a.tenant_id
       AND lf.document_id=a.document_id
       AND lf.location_id=a.location_id
     WHERE a.state='ACTIVE'
       AND lf.location_kind='LOST_FOUND'
       AND EXISTS (
         SELECT 1
           FROM inventory_document_locations standard
          WHERE standard.tenant_id=a.tenant_id
            AND standard.document_id=a.document_id
            AND standard.location_kind='STANDARD'
            AND standard.completed_event_id IS NULL
       )
  ) THEN
    RAISE EXCEPTION
      'Inventory v13 cannot activate: active Lost & Found attempt exists before standard locations are complete.';
  END IF;
END $$;

-- Attempt creation itself is database-authoritative. Direct SQL/runtime callers
-- cannot open Lost & Found while a standard location is incomplete or still has
-- an ACTIVE attempt.
CREATE OR REPLACE FUNCTION inventory_guard_w2w_lost_found_attempt_v13() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_kind text;
  v_remaining_standard integer;
  v_active_standard integer;
BEGIN
  SELECT location_kind
    INTO v_kind
    FROM inventory_document_locations
   WHERE tenant_id=NEW.tenant_id
     AND document_id=NEW.document_id
     AND location_id=NEW.location_id
   FOR SHARE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Inventory v13 attempt location is outside governed document scope.';
  END IF;

  IF v_kind<>'LOST_FOUND' THEN
    RETURN NEW;
  END IF;

  SELECT count(*)::integer
    INTO v_remaining_standard
    FROM inventory_document_locations
   WHERE tenant_id=NEW.tenant_id
     AND document_id=NEW.document_id
     AND location_kind='STANDARD'
     AND completed_event_id IS NULL;

  SELECT count(*)::integer
    INTO v_active_standard
    FROM inventory_mission_attempts a
    JOIN inventory_document_locations l
      ON l.tenant_id=a.tenant_id
     AND l.document_id=a.document_id
     AND l.location_id=a.location_id
   WHERE a.tenant_id=NEW.tenant_id
     AND a.document_id=NEW.document_id
     AND a.state='ACTIVE'
     AND l.location_kind='STANDARD';

  IF v_remaining_standard<>0 OR v_active_standard<>0 THEN
    RAISE EXCEPTION
      'Lost & Found is the final W2W location; complete every standard location first.';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_w2w_lost_found_attempt_v13_trigger
  ON inventory_mission_attempts;
CREATE TRIGGER inventory_guard_w2w_lost_found_attempt_v13_trigger
BEFORE INSERT ON inventory_mission_attempts
FOR EACH ROW EXECUTE FUNCTION inventory_guard_w2w_lost_found_attempt_v13();

-- One operator may own only one ACTIVE W2W location at a time. Ownership is
-- derived from the latest immutable lease on ACTIVE attempts, not from attempt
-- creator provenance (supervisor reassignment may create an unleased attempt).
--
-- The operator-scoped advisory lock serializes concurrent claims on different
-- locations. If two transactions race, only the first lease can commit; the
-- second sees the first as the latest owner and fails closed.
CREATE OR REPLACE FUNCTION inventory_guard_w2w_operator_lease_v13() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_attempt_state text;
  v_other_location text;
BEGIN
  SELECT state
    INTO v_attempt_state
    FROM inventory_mission_attempts
   WHERE tenant_id=NEW.tenant_id
     AND attempt_id=NEW.attempt_id
   FOR SHARE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Inventory v13 mission attempt does not exist.';
  END IF;
  IF v_attempt_state<>'ACTIVE' THEN
    RAISE EXCEPTION 'Inventory v13 lease requires an ACTIVE mission attempt.';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(
      'inventory:w2w:operator:' || NEW.tenant_id || ':' || NEW.employee_id,
      0
    )
  );

  SELECT a.location_id
    INTO v_other_location
    FROM inventory_mission_attempts a
    JOIN LATERAL (
      SELECT l.employee_id
        FROM inventory_mission_leases l
       WHERE l.tenant_id=a.tenant_id
         AND l.attempt_id=a.attempt_id
       ORDER BY l.valid_from DESC, l.issued_at DESC, l.lease_id DESC
       LIMIT 1
    ) latest_owner ON TRUE
   WHERE a.tenant_id=NEW.tenant_id
     AND a.state='ACTIVE'
     AND a.attempt_id<>NEW.attempt_id
     AND latest_owner.employee_id=NEW.employee_id
   LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'Inventory operator already owns active W2W location %; complete or reassign it first.',
      v_other_location;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_w2w_operator_lease_v13_trigger
  ON inventory_mission_leases;
CREATE TRIGGER inventory_guard_w2w_operator_lease_v13_trigger
BEFORE INSERT ON inventory_mission_leases
FOR EACH ROW EXECUTE FUNCTION inventory_guard_w2w_operator_lease_v13();

-- Fail migration on historical state that would make the new operator authority
-- ambiguous. Closed/superseded attempts remain valid immutable history.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM (
        SELECT a.tenant_id, latest_owner.employee_id, count(*) AS active_location_count
          FROM inventory_mission_attempts a
          JOIN LATERAL (
            SELECT l.employee_id
              FROM inventory_mission_leases l
             WHERE l.tenant_id=a.tenant_id
               AND l.attempt_id=a.attempt_id
             ORDER BY l.valid_from DESC, l.issued_at DESC, l.lease_id DESC
             LIMIT 1
          ) latest_owner ON TRUE
         WHERE a.state='ACTIVE'
         GROUP BY a.tenant_id, latest_owner.employee_id
        HAVING count(*)>1
      ) conflicts
  ) THEN
    RAISE EXCEPTION
      'Inventory v13 cannot activate: an operator owns more than one ACTIVE W2W location.';
  END IF;
END $$;

INSERT INTO inventory_schema_migrations(version,name)
VALUES (13,'inventory wall-to-wall operator and lost-found ordering authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
