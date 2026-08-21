-- Item 20: typed synonym/acronym and parent/related concept graph persistence.
-- Additive over 007 + 016; historical migrations remain unchanged.
BEGIN;

ALTER TABLE glossary_terms
  ADD COLUMN IF NOT EXISTS alias_bindings jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS concept_relations jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE glossary_terms DROP CONSTRAINT IF EXISTS glossary_alias_bindings_array;
ALTER TABLE glossary_terms
  ADD CONSTRAINT glossary_alias_bindings_array
  CHECK (jsonb_typeof(alias_bindings) = 'array') NOT VALID;
ALTER TABLE glossary_terms VALIDATE CONSTRAINT glossary_alias_bindings_array;

ALTER TABLE glossary_terms DROP CONSTRAINT IF EXISTS glossary_concept_relations_array;
ALTER TABLE glossary_terms
  ADD CONSTRAINT glossary_concept_relations_array
  CHECK (jsonb_typeof(concept_relations) = 'array') NOT VALID;
ALTER TABLE glossary_terms VALIDATE CONSTRAINT glossary_concept_relations_array;

CREATE OR REPLACE FUNCTION glossary_validate_concept_graph() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(NEW.alias_bindings) AS item
    WHERE jsonb_typeof(item) <> 'object'
       OR COALESCE(item->>'kind','') NOT IN ('synonym','acronym')
       OR btrim(COALESCE(item->>'value','')) = ''
  ) THEN
    RAISE EXCEPTION 'invalid glossary alias binding';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(NEW.concept_relations) AS item
    WHERE jsonb_typeof(item) <> 'object'
       OR COALESCE(item->>'kind','') NOT IN ('parent','related')
       OR btrim(COALESCE(item->>'target_concept_id','')) = ''
       OR item->>'target_concept_id' = NEW.concept_id
  ) THEN
    RAISE EXCEPTION 'invalid glossary concept relation';
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.status IN ('effective','superseded') THEN
    IF NEW.alias_bindings IS DISTINCT FROM OLD.alias_bindings
       OR NEW.concept_relations IS DISTINCT FROM OLD.concept_relations THEN
      RAISE EXCEPTION 'effective glossary graph is immutable; create a new version';
    END IF;
  END IF;

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS glossary_concept_graph_guard ON glossary_terms;
CREATE TRIGGER glossary_concept_graph_guard
BEFORE INSERT OR UPDATE ON glossary_terms
FOR EACH ROW EXECUTE FUNCTION glossary_validate_concept_graph();

COMMIT;
