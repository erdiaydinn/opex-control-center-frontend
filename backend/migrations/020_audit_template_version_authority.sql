-- Item 23: versioned Audit templates, scoring/branching and immutable run snapshots.
BEGIN;

CREATE TABLE IF NOT EXISTS audit_tenant_bindings (
  role_name name PRIMARY KEY,
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> '')
);
REVOKE ALL ON audit_tenant_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION audit_current_tenant() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
  SELECT tenant_id FROM public.audit_tenant_bindings WHERE role_name=session_user
$$;

CREATE TABLE IF NOT EXISTS audit_template_revisions (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  template_key text NOT NULL CHECK (btrim(template_key) <> ''),
  revision integer NOT NULL CHECK (revision > 0),
  status text NOT NULL CHECK (status IN ('draft','published')),
  schema_json jsonb NOT NULL
    CHECK (jsonb_typeof(schema_json) = 'object')
    CHECK (jsonb_typeof(schema_json->'questions') = 'array')
    CHECK (jsonb_array_length(schema_json->'questions') > 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_by text,
  published_at timestamptz,
  PRIMARY KEY (tenant_id, template_key, revision),
  UNIQUE (tenant_id, template_key, revision, content_hash),
  CHECK (
    (status='draft' AND published_by IS NULL AND published_at IS NULL) OR
    (
      status='published'
      AND published_by IS NOT NULL
      AND btrim(published_by) <> ''
      AND published_at IS NOT NULL
    )
  )
);

CREATE TABLE IF NOT EXISTS audit_template_current (
  tenant_id text NOT NULL,
  template_key text NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  selected_by text NOT NULL CHECK (btrim(selected_by) <> ''),
  selected_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, template_key),
  FOREIGN KEY (tenant_id, template_key, revision, content_hash)
    REFERENCES audit_template_revisions(tenant_id, template_key, revision, content_hash)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_run_snapshots (
  tenant_id text NOT NULL,
  audit_run_id uuid NOT NULL DEFAULT gen_random_uuid(),
  template_key text NOT NULL,
  template_revision integer NOT NULL CHECK (template_revision > 0),
  template_hash text NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
  answers jsonb NOT NULL CHECK (jsonb_typeof(answers) = 'object'),
  visible_question_ids jsonb NOT NULL CHECK (jsonb_typeof(visible_question_ids) = 'array'),
  score_awarded numeric(12,2) NOT NULL CHECK (score_awarded >= 0),
  score_possible numeric(12,2) NOT NULL CHECK (score_possible >= 0),
  score_percent numeric(5,2) NOT NULL CHECK (score_percent >= 0 AND score_percent <= 100),
  completed_by text NOT NULL CHECK (btrim(completed_by) <> ''),
  completed_at timestamptz NOT NULL,
  snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (tenant_id, audit_run_id),
  UNIQUE (tenant_id, snapshot_hash),
  FOREIGN KEY (tenant_id, template_key, template_revision, template_hash)
    REFERENCES audit_template_revisions(tenant_id, template_key, revision, content_hash)
    ON DELETE RESTRICT,
  CHECK (
    (score_possible = 0 AND score_awarded = 0 AND score_percent = 0) OR
    (score_possible > 0 AND score_awarded <= score_possible)
  )
);

CREATE INDEX IF NOT EXISTS audit_template_lookup_idx
  ON audit_template_revisions(tenant_id, template_key, status, revision DESC);
CREATE INDEX IF NOT EXISTS audit_run_template_history_idx
  ON audit_run_snapshots(tenant_id, template_key, template_revision, completed_at DESC);

CREATE OR REPLACE FUNCTION audit_template_revision_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'audit template revisions are history-preserving and cannot be deleted';
  END IF;
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.template_key IS DISTINCT FROM OLD.template_key
     OR NEW.revision IS DISTINCT FROM OLD.revision THEN
    RAISE EXCEPTION 'audit template identity/revision is immutable';
  END IF;
  IF OLD.status = 'published' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'published audit template revision is immutable; create a new revision';
  END IF;
  IF OLD.status = 'draft' AND NEW.status = 'published' THEN
    IF NEW.schema_json IS DISTINCT FROM OLD.schema_json
       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
      RAISE EXCEPTION 'publish transition cannot mutate draft content; save draft before publishing';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'draft' AND NEW.status = 'draft' THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'invalid audit template status transition % -> %', OLD.status, NEW.status;
END $$;

DROP TRIGGER IF EXISTS audit_template_revision_guard_trigger ON audit_template_revisions;
CREATE TRIGGER audit_template_revision_guard_trigger
BEFORE UPDATE OR DELETE ON audit_template_revisions
FOR EACH ROW EXECUTE FUNCTION audit_template_revision_guard();

CREATE OR REPLACE FUNCTION audit_template_current_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE revision_status text;
BEGIN
  SELECT status INTO revision_status
  FROM audit_template_revisions
  WHERE tenant_id=NEW.tenant_id
    AND template_key=NEW.template_key
    AND revision=NEW.revision
    AND content_hash=NEW.content_hash;
  IF revision_status IS DISTINCT FROM 'published' THEN
    RAISE EXCEPTION 'current audit template pointer must reference an exact published revision';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS audit_template_current_guard_trigger ON audit_template_current;
CREATE TRIGGER audit_template_current_guard_trigger
BEFORE INSERT OR UPDATE ON audit_template_current
FOR EACH ROW EXECUTE FUNCTION audit_template_current_guard();

CREATE OR REPLACE FUNCTION audit_run_snapshot_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE revision_status text;
BEGIN
  IF TG_OP IN ('UPDATE','DELETE') THEN
    RAISE EXCEPTION 'audit run snapshots are immutable';
  END IF;
  SELECT status INTO revision_status
  FROM audit_template_revisions
  WHERE tenant_id=NEW.tenant_id
    AND template_key=NEW.template_key
    AND revision=NEW.template_revision
    AND content_hash=NEW.template_hash;
  IF revision_status IS DISTINCT FROM 'published' THEN
    RAISE EXCEPTION 'audit run must pin an exact published template revision and hash';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS audit_run_snapshot_guard_trigger ON audit_run_snapshots;
CREATE TRIGGER audit_run_snapshot_guard_trigger
BEFORE INSERT OR UPDATE OR DELETE ON audit_run_snapshots
FOR EACH ROW EXECUTE FUNCTION audit_run_snapshot_guard();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'audit_template_revisions',
    'audit_template_current',
    'audit_run_snapshots'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id=audit_current_tenant()) WITH CHECK (tenant_id=audit_current_tenant())',
      table_name || '_tenant',
      table_name
    );
  END LOOP;
END $$;

COMMIT;
