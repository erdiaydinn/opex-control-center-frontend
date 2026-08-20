-- Workforce/Hiring V45: database-enforced audit hash-chain fencing.
-- Any writer may calculate its record before taking an application lock. This
-- trigger serializes inserts per tenant and rejects a stale previous_hash so a
-- concurrent transaction cannot silently fork the append-only audit chain.

CREATE OR REPLACE FUNCTION public.workforce_audit_chain_fence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_expected_previous text;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM public.workforce_current_tenant() THEN
    RAISE EXCEPTION USING ERRCODE='28000', MESSAGE='audit tenant authority rejected';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended('workforce:' || NEW.tenant_id, 0));

  SELECT audit.hash
    INTO v_expected_previous
    FROM public.workforce_audit AS audit
   WHERE audit.tenant_id = NEW.tenant_id
   ORDER BY audit.sequence DESC
   LIMIT 1;

  v_expected_previous := COALESCE(v_expected_previous, 'GENESIS');
  IF NEW.previous_hash IS DISTINCT FROM v_expected_previous
     OR NEW.record->>'previous_hash' IS DISTINCT FROM NEW.previous_hash
     OR NEW.record->>'hash' IS DISTINCT FROM NEW.hash
     OR NEW.record->>'tenant_id' IS DISTINCT FROM NEW.tenant_id THEN
    RAISE EXCEPTION USING
      ERRCODE='40001',
      MESSAGE='audit hash chain stale; retry transaction';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workforce_audit_chain_fence_before_insert ON public.workforce_audit;
CREATE TRIGGER workforce_audit_chain_fence_before_insert
BEFORE INSERT ON public.workforce_audit
FOR EACH ROW EXECUTE FUNCTION public.workforce_audit_chain_fence();

REVOKE ALL ON FUNCTION public.workforce_audit_chain_fence() FROM PUBLIC;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (45, 'database audit hash chain fencing')
ON CONFLICT (version) DO NOTHING;
