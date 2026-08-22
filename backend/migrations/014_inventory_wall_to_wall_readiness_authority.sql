-- EAY Inventory v14: machine-enforced Wall-to-Wall start readiness and warehouse quiescence.
-- inventory_documents remains the canonical count aggregate; count_mode is a discriminator,
-- not a competing campaign/master identity.
BEGIN;

ALTER TABLE inventory_documents
  ADD COLUMN IF NOT EXISTS count_mode text NOT NULL DEFAULT 'GOLDEN_COUNT';

ALTER TABLE inventory_documents
  DROP CONSTRAINT IF EXISTS inventory_documents_count_mode_v14;
ALTER TABLE inventory_documents
  ADD CONSTRAINT inventory_documents_count_mode_v14
  CHECK (count_mode IN ('GOLDEN_COUNT','WALL_TO_WALL'));

CREATE UNIQUE INDEX IF NOT EXISTS inventory_one_active_w2w_per_warehouse_v14
  ON inventory_documents(tenant_id,warehouse_id)
  WHERE count_mode='WALL_TO_WALL'
    AND state IN ('COUNTING','SUBMITTED','RECONCILING');

CREATE OR REPLACE FUNCTION inventory_guard_count_mode_v14() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF NEW.count_mode IS DISTINCT FROM OLD.count_mode THEN
    RAISE EXCEPTION 'Inventory count mode is immutable after document creation.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_count_mode_v14_trigger ON inventory_documents;
CREATE TRIGGER inventory_guard_count_mode_v14_trigger
BEFORE UPDATE OF count_mode ON inventory_documents
FOR EACH ROW EXECUTE FUNCTION inventory_guard_count_mode_v14();

CREATE TABLE IF NOT EXISTS inventory_w2w_start_evidence (
  tenant_id text NOT NULL,
  document_id uuid NOT NULL,
  warehouse_id text NOT NULL,
  first_attempt_id uuid NOT NULL,
  readiness_snapshot jsonb NOT NULL
    CHECK (jsonb_typeof(readiness_snapshot)='object')
    CHECK (readiness_snapshot->>'status'='READY'),
  evidence_fingerprint text NOT NULL CHECK (length(evidence_fingerprint)=32),
  started_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id,document_id),
  FOREIGN KEY (tenant_id,document_id)
    REFERENCES inventory_documents(tenant_id,id) ON DELETE RESTRICT,
  CONSTRAINT inventory_w2w_start_attempt_v14_fk
    FOREIGN KEY (tenant_id,first_attempt_id)
    REFERENCES inventory_mission_attempts(tenant_id,attempt_id)
    DEFERRABLE INITIALLY DEFERRED
);

DROP TRIGGER IF EXISTS inventory_w2w_start_evidence_immutable ON inventory_w2w_start_evidence;
CREATE TRIGGER inventory_w2w_start_evidence_immutable
BEFORE UPDATE OR DELETE ON inventory_w2w_start_evidence
FOR EACH ROW EXECUTE FUNCTION inventory_immutable_row();

ALTER TABLE inventory_w2w_start_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_w2w_start_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS inventory_w2w_start_evidence_tenant ON inventory_w2w_start_evidence;
CREATE POLICY inventory_w2w_start_evidence_tenant ON inventory_w2w_start_evidence
USING (tenant_id=inventory_current_tenant())
WITH CHECK (tenant_id=inventory_current_tenant());

REVOKE INSERT,UPDATE,DELETE ON inventory_w2w_start_evidence FROM PUBLIC;

CREATE OR REPLACE FUNCTION inventory_wall_to_wall_readiness_v14(
  v_tenant text,
  v_document uuid
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  document_row inventory_documents%ROWTYPE;
  location_count integer := 0;
  standard_location_count integer := 0;
  lost_found_count integer := 0;
  expected_sku_count integer := 0;
  active_operational_mission_count integer := 0;
  competing_w2w_count integer := 0;
  unknown_blockers text[] := ARRAY[]::text[];
  blockers text[] := ARRAY[]::text[];
  readiness_status text;
BEGIN
  SELECT * INTO document_row
    FROM inventory_documents
   WHERE tenant_id=v_tenant AND id=v_document;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'status','UNKNOWN',
      'applicable',true,
      'blockers',jsonb_build_array('DOCUMENT_UNKNOWN'),
      'document_id',v_document
    );
  END IF;

  IF document_row.count_mode<>'WALL_TO_WALL' THEN
    RETURN jsonb_build_object(
      'status','READY',
      'applicable',false,
      'blockers','[]'::jsonb,
      'document_id',document_row.id,
      'warehouse_id',document_row.warehouse_id,
      'count_mode',document_row.count_mode
    );
  END IF;

  SELECT count(*)::integer,
         count(*) FILTER (WHERE location_kind='STANDARD')::integer,
         count(*) FILTER (WHERE location_kind='LOST_FOUND')::integer
    INTO location_count,standard_location_count,lost_found_count
    FROM inventory_document_locations
   WHERE tenant_id=v_tenant AND document_id=v_document;

  SELECT count(*)::integer INTO expected_sku_count
    FROM inventory_expected_stock
   WHERE tenant_id=v_tenant AND document_id=v_document;

  SELECT count(*)::integer INTO active_operational_mission_count
    FROM inventory_operational_missions
   WHERE tenant_id=v_tenant
     AND warehouse_id=document_row.warehouse_id
     AND state IN ('OPEN','CLAIMED');

  SELECT count(*)::integer INTO competing_w2w_count
    FROM inventory_documents d
   WHERE d.tenant_id=v_tenant
     AND d.warehouse_id=document_row.warehouse_id
     AND d.id<>v_document
     AND d.count_mode='WALL_TO_WALL'
     AND d.state IN ('COUNTING','SUBMITTED','RECONCILING');

  IF location_count=0 THEN
    unknown_blockers := array_append(unknown_blockers,'LOCATION_SCOPE_UNKNOWN');
  END IF;
  IF expected_sku_count=0 THEN
    unknown_blockers := array_append(unknown_blockers,'SKU_SCOPE_UNKNOWN');
  END IF;
  IF document_row.state<>'COUNTING' THEN
    blockers := array_append(blockers,'DOCUMENT_NOT_COUNTING');
  END IF;
  IF location_count>0 AND standard_location_count=0 THEN
    blockers := array_append(blockers,'STANDARD_LOCATION_REQUIRED');
  END IF;
  IF location_count>0 AND lost_found_count<>1 THEN
    blockers := array_append(blockers,'LOST_FOUND_REQUIRED');
  END IF;
  IF active_operational_mission_count>0 THEN
    blockers := array_append(blockers,'OPERATIONAL_MISSIONS_ACTIVE');
  END IF;
  IF competing_w2w_count>0 THEN
    blockers := array_append(blockers,'ANOTHER_W2W_ACTIVE');
  END IF;

  readiness_status := CASE
    WHEN cardinality(unknown_blockers)>0 THEN 'UNKNOWN'
    WHEN cardinality(blockers)>0 THEN 'BLOCKED'
    ELSE 'READY'
  END;

  RETURN jsonb_build_object(
    'status',readiness_status,
    'applicable',true,
    'blockers',to_jsonb(unknown_blockers || blockers),
    'document_id',document_row.id,
    'warehouse_id',document_row.warehouse_id,
    'count_mode',document_row.count_mode,
    'location_count',location_count,
    'standard_location_count',standard_location_count,
    'lost_found_count',lost_found_count,
    'expected_sku_count',expected_sku_count,
    'active_operational_mission_count',active_operational_mission_count,
    'competing_w2w_count',competing_w2w_count
  );
END;
$$;

CREATE OR REPLACE FUNCTION inventory_guard_w2w_readiness_v14() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  document_mode text;
  document_warehouse text;
  readiness_snapshot jsonb;
BEGIN
  SELECT count_mode,warehouse_id INTO document_mode,document_warehouse
    FROM inventory_documents
   WHERE tenant_id=NEW.tenant_id AND id=NEW.document_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Inventory W2W readiness document does not exist.';
  END IF;
  IF document_mode<>'WALL_TO_WALL' THEN
    RETURN NEW;
  END IF;

  -- Serialize the W2W start boundary with operational mission admission for the
  -- same warehouse. This closes the race between "no open work" observation and
  -- the first physical count attempt.
  PERFORM pg_advisory_xact_lock(
    hashtextextended('inventory:w2w:warehouse:' || NEW.tenant_id || ':' || document_warehouse,0)
  );

  IF EXISTS (
    SELECT 1 FROM inventory_w2w_start_evidence
     WHERE tenant_id=NEW.tenant_id AND document_id=NEW.document_id
  ) THEN
    RETURN NEW;
  END IF;

  readiness_snapshot := inventory_wall_to_wall_readiness_v14(NEW.tenant_id,NEW.document_id);
  IF readiness_snapshot->>'status'<>'READY' THEN
    RAISE EXCEPTION 'Inventory W2W start rejected: readiness=% blockers=%',
      readiness_snapshot->>'status',readiness_snapshot->'blockers';
  END IF;

  -- The unique document key is the concurrency fence. With a deferred FK, the
  -- immutable start evidence can be inserted before NEW attempt exists. Concurrent
  -- first-location attempts collapse onto the same admitted readiness snapshot.
  INSERT INTO inventory_w2w_start_evidence(
    tenant_id,document_id,warehouse_id,first_attempt_id,
    readiness_snapshot,evidence_fingerprint,started_at
  ) VALUES (
    NEW.tenant_id,NEW.document_id,document_warehouse,NEW.attempt_id,
    readiness_snapshot,
    md5(NEW.tenant_id || '|' || NEW.document_id::text || '|' || NEW.attempt_id::text || '|' || readiness_snapshot::text),
    now()
  ) ON CONFLICT (tenant_id,document_id) DO NOTHING;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_w2w_readiness_v14_trigger ON inventory_mission_attempts;
CREATE TRIGGER inventory_guard_w2w_readiness_v14_trigger
BEFORE INSERT ON inventory_mission_attempts
FOR EACH ROW EXECUTE FUNCTION inventory_guard_w2w_readiness_v14();

CREATE OR REPLACE FUNCTION inventory_guard_operational_during_w2w_v14() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  target_state text;
BEGIN
  target_state := NEW.state;
  IF target_state NOT IN ('OPEN','CLAIMED') THEN
    RETURN NEW;
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended('inventory:w2w:warehouse:' || NEW.tenant_id || ':' || NEW.warehouse_id,0)
  );

  IF EXISTS (
    SELECT 1
      FROM inventory_documents d
      JOIN inventory_w2w_start_evidence s
        ON s.tenant_id=d.tenant_id AND s.document_id=d.id
     WHERE d.tenant_id=NEW.tenant_id
       AND d.warehouse_id=NEW.warehouse_id
       AND d.count_mode='WALL_TO_WALL'
       AND d.state='COUNTING'
  ) THEN
    RAISE EXCEPTION 'Inventory operational mission cannot open while Wall-to-Wall count is in progress.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_guard_operational_during_w2w_v14_trigger ON inventory_operational_missions;
CREATE TRIGGER inventory_guard_operational_during_w2w_v14_trigger
BEFORE INSERT OR UPDATE OF state ON inventory_operational_missions
FOR EACH ROW EXECUTE FUNCTION inventory_guard_operational_during_w2w_v14();

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='inventory_runtime') THEN
    GRANT SELECT ON inventory_w2w_start_evidence TO inventory_runtime;
    GRANT EXECUTE ON FUNCTION inventory_wall_to_wall_readiness_v14(text,uuid) TO inventory_runtime;
  END IF;
END $$;

INSERT INTO inventory_schema_migrations(version,name)
VALUES (14,'inventory wall-to-wall readiness and warehouse quiescence authority')
ON CONFLICT (version) DO NOTHING;

COMMIT;
