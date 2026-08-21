-- Item 22: exact-version Business Glossary data/API/dashboard lineage.
BEGIN;

CREATE TABLE IF NOT EXISTS glossary_lineage_bindings (
  tenant_id text NOT NULL,
  binding_id uuid NOT NULL DEFAULT gen_random_uuid(),
  concept_id text NOT NULL,
  glossary_version integer NOT NULL CHECK (glossary_version > 0),
  asset_kind text NOT NULL CHECK (asset_kind IN ('dataset','api_field','dashboard')),
  relation text NOT NULL CHECK (relation IN ('source','exposed_as','used_by')),
  asset_ref text NOT NULL CHECK (btrim(asset_ref) <> ''),
  display_label text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, binding_id),
  FOREIGN KEY (tenant_id, concept_id, glossary_version)
    REFERENCES glossary_terms(tenant_id, concept_id, version) ON DELETE RESTRICT,
  UNIQUE (tenant_id, concept_id, glossary_version, asset_kind, relation, asset_ref),
  CHECK (
    (asset_kind='dataset' AND relation='source') OR
    (asset_kind='api_field' AND relation='exposed_as') OR
    (asset_kind='dashboard' AND relation='used_by')
  ),
  CHECK (display_label IS NULL OR btrim(display_label) <> '')
);

CREATE INDEX IF NOT EXISTS glossary_lineage_exact_version_idx
  ON glossary_lineage_bindings(tenant_id, concept_id, glossary_version, asset_kind, asset_ref);

ALTER TABLE glossary_lineage_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE glossary_lineage_bindings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS glossary_lineage_bindings_tenant ON glossary_lineage_bindings;
CREATE POLICY glossary_lineage_bindings_tenant ON glossary_lineage_bindings
  USING (tenant_id = glossary_current_tenant())
  WITH CHECK (tenant_id = glossary_current_tenant());

CREATE OR REPLACE FUNCTION glossary_lineage_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'glossary lineage is append-only; bind changes to the intended glossary version';
END $$;
DROP TRIGGER IF EXISTS glossary_lineage_immutable_guard ON glossary_lineage_bindings;
CREATE TRIGGER glossary_lineage_immutable_guard
BEFORE UPDATE OR DELETE ON glossary_lineage_bindings
FOR EACH ROW EXECUTE FUNCTION glossary_lineage_immutable();

COMMIT;
