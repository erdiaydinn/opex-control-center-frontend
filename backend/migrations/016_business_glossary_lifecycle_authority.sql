-- Item 18: enforce the Business Glossary lifecycle at the PostgreSQL boundary.
-- Historical migration 007 remains unchanged; this migration closes direct-write bypasses.
BEGIN;

ALTER TABLE glossary_terms
  DROP CONSTRAINT IF EXISTS glossary_effective_requires_start;
ALTER TABLE glossary_terms
  ADD CONSTRAINT glossary_effective_requires_start
  CHECK (status NOT IN ('effective','superseded') OR effective_from IS NOT NULL) NOT VALID;
ALTER TABLE glossary_terms VALIDATE CONSTRAINT glossary_effective_requires_start;

CREATE OR REPLACE FUNCTION glossary_protect_definition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'new glossary versions must enter governance as draft';
    END IF;
    IF NEW.effective_from IS NOT NULL OR NEW.effective_to IS NOT NULL THEN
      RAISE EXCEPTION 'draft glossary versions cannot carry effective dates';
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.concept_id IS DISTINCT FROM OLD.concept_id
     OR NEW.version IS DISTINCT FROM OLD.version THEN
    RAISE EXCEPTION 'glossary identity/version is immutable';
  END IF;

  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF OLD.status = 'draft' AND NEW.status <> 'review' THEN
      RAISE EXCEPTION 'invalid glossary lifecycle transition: draft -> %', NEW.status;
    ELSIF OLD.status = 'review' AND NEW.status NOT IN ('draft','approved') THEN
      RAISE EXCEPTION 'invalid glossary lifecycle transition: review -> %', NEW.status;
    ELSIF OLD.status = 'approved' AND NEW.status NOT IN ('draft','effective') THEN
      RAISE EXCEPTION 'invalid glossary lifecycle transition: approved -> %', NEW.status;
    ELSIF OLD.status = 'effective' AND NEW.status <> 'superseded' THEN
      RAISE EXCEPTION 'invalid glossary lifecycle transition: effective -> %', NEW.status;
    ELSIF OLD.status = 'superseded' THEN
      RAISE EXCEPTION 'superseded glossary version is immutable';
    END IF;
  END IF;

  IF NEW.status = 'effective' AND NEW.effective_from IS NULL THEN
    RAISE EXCEPTION 'effective glossary version requires effective_from';
  END IF;

  IF OLD.status = 'effective' THEN
    IF NEW.canonical_key IS DISTINCT FROM OLD.canonical_key
       OR NEW.country IS DISTINCT FROM OLD.country
       OR NEW.region IS DISTINCT FROM OLD.region
       OR NEW.business_unit IS DISTINCT FROM OLD.business_unit
       OR NEW.domain IS DISTINCT FROM OLD.domain
       OR NEW.display_name IS DISTINCT FROM OLD.display_name
       OR NEW.short_definition IS DISTINCT FROM OLD.short_definition
       OR NEW.detailed_definition IS DISTINCT FROM OLD.detailed_definition
       OR NEW.aliases IS DISTINCT FROM OLD.aliases
       OR NEW.formula IS DISTINCT FROM OLD.formula
       OR NEW.unit IS DISTINCT FROM OLD.unit
       OR NEW.data_source_refs IS DISTINCT FROM OLD.data_source_refs
       OR NEW.related_concepts IS DISTINCT FROM OLD.related_concepts
       OR NEW.owner_subject IS DISTINCT FROM OLD.owner_subject
       OR NEW.effective_from IS DISTINCT FROM OLD.effective_from THEN
      RAISE EXCEPTION 'effective glossary definition is immutable; create a new version';
    END IF;
  END IF;

  IF OLD.status = 'superseded' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'superseded glossary version is immutable';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS glossary_definition_guard ON glossary_terms;
CREATE TRIGGER glossary_definition_guard
BEFORE INSERT OR UPDATE ON glossary_terms
FOR EACH ROW EXECUTE FUNCTION glossary_protect_definition();

COMMIT;
