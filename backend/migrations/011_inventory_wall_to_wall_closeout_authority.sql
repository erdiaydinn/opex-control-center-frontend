-- EAY Inventory v11: wall-to-wall scope freeze and immutable aggregate closeout authority.
-- The existing inventory document remains the canonical wall-to-wall aggregate.
-- This migration does not introduce a competing campaign/master identity.
BEGIN;

CREATE TABLE IF NOT EXISTS inventory_document_closeouts (
  tenant_id text NOT NULL,
  document_id uuid NOT NULL,
  warehouse_id text NOT NULL,
  submitted_revision integer NOT NULL CHECK (submitted_revision >= 2),
  required_location_count integer NOT NULL CHECK (required_location_count > 0),
  completed_location_count integer NOT NULL CHECK (completed_location_count > 0),
  completion_evidence jsonb NOT NULL,
  evidence_fingerprint text NOT NULL CHECK (length(evidence_fingerprint)=32),
  submitted_by_subject text NOT NULL CHECK (length(trim(submitted_by_subject)) > 0),
  submitted_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, document_id),
  FOREIGN KEY (tenant_id, document_id)
    REFERENCES inventory_documents(tenant_id, id) ON DELETE RESTRICT,
  CHECK (completed_location_count = required_location_count)
);

DROP TRIGGER IF EXISTS inventory_document_closeouts_immutable ON inventory_document_closeouts;
CREATE TRIGGER inventory_document_closeouts_immutable
BEFORE UPDATE OR DELETE ON inventory_document_closeouts
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();

ALTER TABLE inventory_document_closeouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_document_closeouts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS inventory_document_closeouts_tenant ON inventory_document_closeouts;
CREATE POLICY inventory_document_closeouts_tenant ON inventory_document_closeouts
USING (tenant_id=inventory_current_tenant())
WITH CHECK (tenant_id=inventory_current_tenant());

-- Common check used by table-specific triggers. Keeping the trigger functions
-- table-specific avoids RECORD-field ambiguity across different scope tables.
CREATE OR REPLACE FUNCTION inventory_assert_wall_to_wall_scope_mutable_v11(
  v_tenant text,
  v_document uuid
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_state text;
  v_started boolean;
BEGIN
  SELECT state INTO v_state
    FROM inventory_documents
   WHERE tenant_id=v_tenant AND id=v_document;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Inventory wall-to-wall scope document does not exist.';
  END IF;

  SELECT EXISTS (
           SELECT 1 FROM inventory_mission_attempts
            WHERE tenant_id=v_tenant AND document_id=v_document
         ) OR EXISTS (
           SELECT 1 FROM inventory_events
            WHERE tenant_id=v_tenant AND document_id=v_document
         )
    INTO v_started;

  IF v_state<>'COUNTING' OR v_started THEN
    RAISE EXCEPTION 'Inventory wall-to-wall scope is frozen after counting starts.';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION inventory_guard_wall_to_wall_location_scope_v11() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF TG_OP='UPDATE' THEN
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.document_id IS DISTINCT FROM OLD.document_id
       OR NEW.location_id IS DISTINCT FROM OLD.location_id THEN
      RAISE EXCEPTION 'Inventory wall-to-wall location identity is immutable.';
    END IF;
    -- Same-row completion fields are governed by the deferred anchor validator.
    RETURN NEW;
  ELSIF TG_OP='DELETE' THEN
    PERFORM inventory_assert_wall_to_wall_scope_mutable_v11(OLD.tenant_id,OLD.document_id);
    RETURN OLD;
  END IF;

  PERFORM inventory_assert_wall_to_wall_scope_mutable_v11(NEW.tenant_id,NEW.document_id);
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION inventory_guard_wall_to_wall_sku_scope_v11() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF TG_OP='UPDATE' THEN
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.document_id IS DISTINCT FROM OLD.document_id
       OR NEW.sku IS DISTINCT FROM OLD.sku
       OR NEW.barcode IS DISTINCT FROM OLD.barcode THEN
      RAISE EXCEPTION 'Inventory wall-to-wall SKU identity is immutable.';
    END IF;
    PERFORM inventory_assert_wall_to_wall_scope_mutable_v11(NEW.tenant_id,NEW.document_id);
    RETURN NEW;
  ELSIF TG_OP='DELETE' THEN
    PERFORM inventory_assert_wall_to_wall_scope_mutable_v11(OLD.tenant_id,OLD.document_id);
    RETURN OLD;
  END IF;

  PERFORM inventory_assert_wall_to_wall_scope_mutable_v11(NEW.tenant_id,NEW.document_id);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_wall_to_wall_location_scope_v11 ON inventory_document_locations;
CREATE TRIGGER inventory_wall_to_wall_location_scope_v11
BEFORE INSERT OR UPDATE OR DELETE ON inventory_document_locations
FOR EACH ROW EXECUTE FUNCTION inventory_guard_wall_to_wall_location_scope_v11();

DROP TRIGGER IF EXISTS inventory_wall_to_wall_sku_scope_v11 ON inventory_expected_stock;
CREATE TRIGGER inventory_wall_to_wall_sku_scope_v11
BEFORE INSERT OR UPDATE OR DELETE ON inventory_expected_stock
FOR EACH ROW EXECUTE FUNCTION inventory_guard_wall_to_wall_sku_scope_v11();

-- v4 updates the location row before inserting LOCATION_COMPLETE. A deferred
-- constraint trigger validates the completed-event anchor at transaction end,
-- after the immutable event exists, and prevents later clearing/substitution.
CREATE OR REPLACE FUNCTION inventory_validate_location_completion_anchor_v11() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  matched boolean;
BEGIN
  IF OLD.completed_event_id IS NOT NULL AND (
       NEW.completed_event_id IS DISTINCT FROM OLD.completed_event_id
       OR NEW.completed_at IS DISTINCT FROM OLD.completed_at
     ) THEN
    RAISE EXCEPTION 'Inventory completed location anchor is immutable.';
  END IF;

  IF NEW.completed_event_id IS NULL THEN
    IF NEW.completed_at IS NOT NULL THEN
      RAISE EXCEPTION 'Inventory completed location timestamp requires event anchor.';
    END IF;
    RETURN NEW;
  END IF;

  SELECT EXISTS (
    SELECT 1
      FROM inventory_events e
     WHERE e.tenant_id=NEW.tenant_id
       AND e.document_id=NEW.document_id
       AND e.location_id=NEW.location_id
       AND e.event_id=NEW.completed_event_id
       AND e.event_type='LOCATION_COMPLETE'
       AND e.occurred_at=NEW.completed_at
  ) INTO matched;
  IF NOT matched THEN
    RAISE EXCEPTION 'Inventory completed location anchor does not match immutable LOCATION_COMPLETE evidence.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_location_completion_anchor_v11 ON inventory_document_locations;
CREATE CONSTRAINT TRIGGER inventory_location_completion_anchor_v11
AFTER UPDATE OF completed_event_id, completed_at ON inventory_document_locations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION inventory_validate_location_completion_anchor_v11();

-- Final DB-side authority. Application preflight remains useful for friendly
-- errors, but the database independently rejects incomplete/misaligned closeout.
CREATE OR REPLACE FUNCTION inventory_guard_wall_to_wall_submit_v11() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  required_count integer;
  valid_completed_count integer;
  active_attempt_count integer;
  live_lease_count integer;
BEGIN
  IF NOT (OLD.state='COUNTING' AND NEW.state='SUBMITTED') THEN
    RETURN NEW;
  END IF;

  SELECT count(*)::integer INTO required_count
    FROM inventory_document_locations
   WHERE tenant_id=NEW.tenant_id AND document_id=NEW.id;

  SELECT count(*)::integer INTO valid_completed_count
    FROM inventory_document_locations l
    JOIN inventory_events e
      ON e.tenant_id=l.tenant_id
     AND e.document_id=l.document_id
     AND e.location_id=l.location_id
     AND e.event_id=l.completed_event_id
     AND e.event_type='LOCATION_COMPLETE'
    JOIN inventory_mission_attempts a
      ON a.tenant_id=e.tenant_id
     AND a.attempt_id=e.attempt_id
     AND a.document_id=e.document_id
     AND a.location_id=e.location_id
     AND a.state='COMPLETED'
    JOIN inventory_mission_lease_closures c
      ON c.tenant_id=e.tenant_id
     AND c.lease_id=e.lease_id
     AND c.state='COMPLETED'
   WHERE l.tenant_id=NEW.tenant_id
     AND l.document_id=NEW.id;

  SELECT count(*)::integer INTO active_attempt_count
    FROM inventory_mission_attempts
   WHERE tenant_id=NEW.tenant_id
     AND document_id=NEW.id
     AND state='ACTIVE';

  SELECT count(*)::integer INTO live_lease_count
    FROM inventory_mission_leases ml
    JOIN inventory_mission_attempts a
      ON a.tenant_id=ml.tenant_id AND a.attempt_id=ml.attempt_id
    LEFT JOIN inventory_mission_lease_closures c
      ON c.tenant_id=ml.tenant_id AND c.lease_id=ml.lease_id
   WHERE a.tenant_id=NEW.tenant_id
     AND a.document_id=NEW.id
     AND c.lease_id IS NULL
     AND ml.valid_until>now();

  IF required_count<=0 THEN
    RAISE EXCEPTION 'Wall-to-wall document has no governed location scope.';
  END IF;
  IF valid_completed_count<>required_count THEN
    RAISE EXCEPTION 'Wall-to-wall submission rejected: not every scoped location has current completed attempt/lease evidence.';
  END IF;
  IF active_attempt_count<>0 THEN
    RAISE EXCEPTION 'Wall-to-wall submission rejected: active mission attempt remains.';
  END IF;
  IF live_lease_count<>0 THEN
    RAISE EXCEPTION 'Wall-to-wall submission rejected: live mission lease remains.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_wall_to_wall_submit_guard_v11 ON inventory_documents;
CREATE TRIGGER inventory_wall_to_wall_submit_guard_v11
BEFORE UPDATE OF state ON inventory_documents
FOR EACH ROW EXECUTE FUNCTION inventory_guard_wall_to_wall_submit_v11();

CREATE OR REPLACE FUNCTION inventory_capture_wall_to_wall_closeout_v11() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  evidence jsonb;
  required_count integer;
  completed_count integer;
  fingerprint text;
BEGIN
  IF NOT (OLD.state='COUNTING' AND NEW.state='SUBMITTED') THEN
    RETURN NEW;
  END IF;

  SELECT count(*)::integer,
         jsonb_agg(
           jsonb_build_object(
             'location_id',l.location_id,
             'completion_event_id',e.event_id,
             'attempt_id',e.attempt_id,
             'lease_id',e.lease_id,
             'active_shift_id',e.active_shift_id,
             'employee_id',e.employee_id,
             'device_id',e.device_id,
             'payload_hash',e.payload_hash,
             'occurred_at',e.occurred_at
           ) ORDER BY l.location_id
         )
    INTO completed_count,evidence
    FROM inventory_document_locations l
    JOIN inventory_events e
      ON e.tenant_id=l.tenant_id
     AND e.document_id=l.document_id
     AND e.location_id=l.location_id
     AND e.event_id=l.completed_event_id
     AND e.event_type='LOCATION_COMPLETE'
   WHERE l.tenant_id=NEW.tenant_id AND l.document_id=NEW.id;

  SELECT count(*)::integer INTO required_count
    FROM inventory_document_locations
   WHERE tenant_id=NEW.tenant_id AND document_id=NEW.id;

  fingerprint := md5(
    NEW.tenant_id || '|' || NEW.id::text || '|' || NEW.warehouse_id || '|' ||
    NEW.revision::text || '|' || COALESCE(evidence,'[]'::jsonb)::text
  );

  INSERT INTO inventory_document_closeouts(
    tenant_id,document_id,warehouse_id,submitted_revision,
    required_location_count,completed_location_count,completion_evidence,
    evidence_fingerprint,submitted_by_subject,submitted_at
  ) VALUES (
    NEW.tenant_id,NEW.id,NEW.warehouse_id,NEW.revision,
    required_count,completed_count,COALESCE(evidence,'[]'::jsonb),
    fingerprint,COALESCE(NULLIF(trim(NEW.submitted_by),''),'unknown'),now()
  )
  ON CONFLICT (tenant_id,document_id) DO NOTHING;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_wall_to_wall_closeout_v11 ON inventory_documents;
CREATE TRIGGER inventory_wall_to_wall_closeout_v11
AFTER UPDATE OF state ON inventory_documents
FOR EACH ROW EXECUTE FUNCTION inventory_capture_wall_to_wall_closeout_v11();

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='inventory_runtime') THEN
    GRANT SELECT ON inventory_document_closeouts TO inventory_runtime;
  END IF;
END $$;

INSERT INTO inventory_schema_migrations(version,name)
VALUES (11,'inventory wall-to-wall scope freeze and closeout authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
