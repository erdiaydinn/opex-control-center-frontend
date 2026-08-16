-- EAY tenant-aware Business Glossary persistence.
BEGIN;

CREATE TABLE IF NOT EXISTS glossary_terms (
  tenant_id text NOT NULL,
  concept_id text NOT NULL,
  canonical_key text NOT NULL,
  country text,
  region text,
  business_unit text,
  domain text,
  version integer NOT NULL CHECK (version > 0),
  status text NOT NULL CHECK (status IN ('draft','review','approved','effective','superseded')),
  effective_from timestamptz,
  effective_to timestamptz,
  display_name jsonb NOT NULL,
  short_definition jsonb NOT NULL,
  detailed_definition jsonb,
  aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
  formula text,
  unit text,
  data_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  related_concepts jsonb NOT NULL DEFAULT '[]'::jsonb,
  owner_subject text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, concept_id, version),
  CHECK (effective_to IS NULL OR effective_from IS NOT NULL),
  CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS glossary_semantic_scope_version_uq
  ON glossary_terms (tenant_id, canonical_key, country, region, business_unit, domain, version)
  NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS glossary_lookup_idx
  ON glossary_terms (tenant_id, canonical_key, status, country, region, business_unit, domain, version DESC);

CREATE OR REPLACE FUNCTION glossary_protect_definition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.concept_id IS DISTINCT FROM OLD.concept_id
     OR NEW.version IS DISTINCT FROM OLD.version THEN
    RAISE EXCEPTION 'glossary identity/version is immutable';
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
       OR NEW.owner_subject IS DISTINCT FROM OLD.owner_subject THEN
      RAISE EXCEPTION 'effective glossary definition is immutable; create a new version';
    END IF;
    IF NEW.status NOT IN ('effective','superseded') THEN
      RAISE EXCEPTION 'effective glossary status may only remain effective or become superseded';
    END IF;
  END IF;

  IF OLD.status = 'superseded' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'superseded glossary version is immutable';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS glossary_definition_guard ON glossary_terms;
CREATE TRIGGER glossary_definition_guard BEFORE UPDATE ON glossary_terms
FOR EACH ROW EXECUTE FUNCTION glossary_protect_definition();

CREATE TABLE IF NOT EXISTS glossary_governance_events (
  tenant_id text NOT NULL,
  event_id uuid NOT NULL,
  concept_id text NOT NULL,
  version integer NOT NULL,
  actor_subject text NOT NULL,
  from_status text,
  to_status text NOT NULL,
  reason text,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (tenant_id, event_id),
  FOREIGN KEY (tenant_id, concept_id, version) REFERENCES glossary_terms(tenant_id, concept_id, version) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION glossary_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$;
DROP TRIGGER IF EXISTS glossary_governance_immutable ON glossary_governance_events;
CREATE TRIGGER glossary_governance_immutable BEFORE UPDATE OR DELETE ON glossary_governance_events
FOR EACH ROW EXECUTE FUNCTION glossary_immutable_row();

CREATE TABLE IF NOT EXISTS glossary_tenant_bindings (
  role_name name PRIMARY KEY,
  tenant_id text NOT NULL
);
REVOKE ALL ON glossary_tenant_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION glossary_current_tenant() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
  SELECT tenant_id FROM public.glossary_tenant_bindings WHERE role_name=session_user
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['glossary_terms','glossary_governance_events'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=glossary_current_tenant()) WITH CHECK (tenant_id=glossary_current_tenant())',
      table_name || '_tenant', table_name
    );
  END LOOP;
END $$;

COMMIT;
