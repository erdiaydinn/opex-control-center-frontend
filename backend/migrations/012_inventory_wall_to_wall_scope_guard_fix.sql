-- EAY Inventory v12: record-shape safe wall-to-wall scope guard.
-- v11 intentionally shares one trigger function across location and SKU scope tables.
-- PostgreSQL trigger records have table-specific fields, so table-specific fields
-- must only be referenced inside a table-specific branch.
BEGIN;

CREATE OR REPLACE FUNCTION inventory_guard_wall_to_wall_scope_v11() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_tenant text;
  v_document uuid;
  v_state text;
  v_started boolean;
BEGIN
  v_tenant := CASE WHEN TG_OP='DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END;
  v_document := CASE WHEN TG_OP='DELETE' THEN OLD.document_id ELSE NEW.document_id END;

  IF TG_TABLE_NAME='inventory_document_locations' THEN
    IF TG_OP='UPDATE'
       AND NEW.tenant_id=OLD.tenant_id
       AND NEW.document_id=OLD.document_id
       AND NEW.location_id=OLD.location_id THEN
      -- Completion columns are governed by the deferred anchor validator.
      RETURN NEW;
    END IF;
  ELSIF TG_TABLE_NAME<>'inventory_expected_stock' THEN
    RAISE EXCEPTION 'Inventory wall-to-wall scope guard attached to unsupported table: %', TG_TABLE_NAME;
  END IF;

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

  IF TG_OP='DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;

INSERT INTO inventory_schema_migrations(version,name)
VALUES (12,'inventory wall-to-wall record-shape safe scope guard')
ON CONFLICT (version) DO NOTHING;

COMMIT;
