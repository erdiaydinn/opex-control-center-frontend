-- Item 21: immutable bulk import review evidence.
-- Import planning never promotes a glossary definition; lifecycle authority remains 016.
BEGIN;

CREATE TABLE IF NOT EXISTS glossary_import_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  fingerprint text NOT NULL,
  source_kind text NOT NULL CHECK (source_kind IN ('csv','api')),
  actor_subject text NOT NULL,
  row_count integer NOT NULL CHECK (row_count >= 0),
  review_required boolean NOT NULL DEFAULT true CHECK (review_required = true),
  automatic_effective_permitted boolean NOT NULL DEFAULT false CHECK (automatic_effective_permitted = false),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, fingerprint, source_kind),
  UNIQUE (batch_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS glossary_import_entries (
  batch_id uuid NOT NULL,
  tenant_id text NOT NULL,
  entry_no integer NOT NULL CHECK (entry_no >= 1),
  concept_id text NOT NULL,
  canonical_key text NOT NULL,
  action text NOT NULL CHECK (action IN ('no_change','new_draft','new_version_draft')),
  source_version integer,
  proposed_version integer,
  diff jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(diff) = 'array'),
  proposed_term jsonb,
  review_required boolean NOT NULL DEFAULT true CHECK (review_required = true),
  automatic_effective_permitted boolean NOT NULL DEFAULT false CHECK (automatic_effective_permitted = false),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (batch_id, entry_no),
  FOREIGN KEY (batch_id, tenant_id) REFERENCES glossary_import_batches(batch_id, tenant_id),
  CHECK ((action = 'no_change' AND proposed_version IS NULL AND proposed_term IS NULL)
      OR (action IN ('new_draft','new_version_draft') AND proposed_version IS NOT NULL AND proposed_term IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS glossary_import_batches_tenant_created_idx
  ON glossary_import_batches(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS glossary_import_entries_tenant_concept_idx
  ON glossary_import_entries(tenant_id, concept_id, created_at DESC);

ALTER TABLE glossary_import_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE glossary_import_batches FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS glossary_import_batches_tenant_policy ON glossary_import_batches;
CREATE POLICY glossary_import_batches_tenant_policy ON glossary_import_batches
  USING (tenant_id = glossary_current_tenant())
  WITH CHECK (tenant_id = glossary_current_tenant());

ALTER TABLE glossary_import_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE glossary_import_entries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS glossary_import_entries_tenant_policy ON glossary_import_entries;
CREATE POLICY glossary_import_entries_tenant_policy ON glossary_import_entries
  USING (tenant_id = glossary_current_tenant())
  WITH CHECK (tenant_id = glossary_current_tenant());

CREATE OR REPLACE FUNCTION glossary_import_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'glossary import review evidence is append-only';
END $$;

DROP TRIGGER IF EXISTS glossary_import_batches_immutable ON glossary_import_batches;
CREATE TRIGGER glossary_import_batches_immutable
BEFORE UPDATE OR DELETE ON glossary_import_batches
FOR EACH ROW EXECUTE FUNCTION glossary_import_evidence_immutable();

DROP TRIGGER IF EXISTS glossary_import_entries_immutable ON glossary_import_entries;
CREATE TRIGGER glossary_import_entries_immutable
BEFORE UPDATE OR DELETE ON glossary_import_entries
FOR EACH ROW EXECUTE FUNCTION glossary_import_evidence_immutable();

COMMIT;
