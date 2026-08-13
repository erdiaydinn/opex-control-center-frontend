-- Workforce V29: tenant-scoped, optimistic and auditable PostgreSQL state.
-- This migration is intentionally idempotent so CI can exercise cold and
-- repeated startup paths. Production deploys should apply it before the app.

CREATE TABLE IF NOT EXISTS workforce_schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workforce_entities (
  tenant_id text NOT NULL,
  kind text NOT NULL,
  entity_id text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, kind, entity_id)
);
ALTER TABLE workforce_entities ADD COLUMN IF NOT EXISTS tenant_id text;
UPDATE workforce_entities
SET tenant_id = COALESCE(NULLIF(current_setting('app.workforce_tenant', true), ''), 'eay')
WHERE tenant_id IS NULL;
ALTER TABLE workforce_entities ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE workforce_entities DROP CONSTRAINT IF EXISTS workforce_entities_pkey;
ALTER TABLE workforce_entities ADD PRIMARY KEY (tenant_id, kind, entity_id);
CREATE INDEX IF NOT EXISTS workforce_entities_kind_idx
  ON workforce_entities (tenant_id, kind, updated_at DESC);

CREATE TABLE IF NOT EXISTS workforce_collection_versions (
  tenant_id text NOT NULL,
  kind text NOT NULL,
  version bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, kind)
);

CREATE TABLE IF NOT EXISTS workforce_tenant_bindings (
  role_name name PRIMARY KEY,
  tenant_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON workforce_tenant_bindings FROM PUBLIC;

CREATE OR REPLACE FUNCTION workforce_current_tenant()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT binding.tenant_id
  FROM public.workforce_tenant_bindings AS binding
  WHERE binding.role_name = session_user
$$;

CREATE TABLE IF NOT EXISTS workforce_audit (
  sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id text NOT NULL,
  id text NOT NULL UNIQUE,
  at timestamptz NOT NULL,
  event text NOT NULL,
  actor text NOT NULL,
  record jsonb NOT NULL,
  previous_hash text NOT NULL,
  hash text NOT NULL UNIQUE
);
ALTER TABLE workforce_audit ADD COLUMN IF NOT EXISTS tenant_id text;
UPDATE workforce_audit
SET tenant_id = COALESCE(NULLIF(current_setting('app.workforce_tenant', true), ''), 'eay')
WHERE tenant_id IS NULL;
ALTER TABLE workforce_audit ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS workforce_audit_tenant_sequence_idx
  ON workforce_audit (tenant_id, sequence DESC);

CREATE OR REPLACE FUNCTION workforce_audit_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workforce_audit is append-only';
END $$;
DROP TRIGGER IF EXISTS workforce_audit_no_update ON workforce_audit;
CREATE TRIGGER workforce_audit_no_update
  BEFORE UPDATE OR DELETE ON workforce_audit
  FOR EACH ROW EXECUTE FUNCTION workforce_audit_immutable();

CREATE TABLE IF NOT EXISTS workforce_notification_outbox (
  tenant_id text NOT NULL,
  id text NOT NULL,
  person_id text NOT NULL,
  platform text,
  push_token text,
  notification_type text NOT NULL,
  scheduled_at timestamptz NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  attempts integer NOT NULL DEFAULT 0,
  locked_at timestamptz,
  delivered_at timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id)
);
ALTER TABLE workforce_notification_outbox ADD COLUMN IF NOT EXISTS tenant_id text;
UPDATE workforce_notification_outbox
SET tenant_id = COALESCE(NULLIF(current_setting('app.workforce_tenant', true), ''), 'eay')
WHERE tenant_id IS NULL;
ALTER TABLE workforce_notification_outbox ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE workforce_notification_outbox DROP CONSTRAINT IF EXISTS workforce_notification_outbox_pkey;
ALTER TABLE workforce_notification_outbox ADD PRIMARY KEY (tenant_id, id);
CREATE INDEX IF NOT EXISTS workforce_outbox_due_idx
  ON workforce_notification_outbox (tenant_id, status, scheduled_at);

ALTER TABLE workforce_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_entities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_entities_tenant ON workforce_entities;
CREATE POLICY workforce_entities_tenant ON workforce_entities
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_collection_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_collection_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_versions_tenant ON workforce_collection_versions;
CREATE POLICY workforce_versions_tenant ON workforce_collection_versions
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_audit FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_audit_tenant ON workforce_audit;
CREATE POLICY workforce_audit_tenant ON workforce_audit
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE workforce_notification_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_notification_outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_outbox_tenant ON workforce_notification_outbox;
CREATE POLICY workforce_outbox_tenant ON workforce_notification_outbox
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

INSERT INTO workforce_schema_migrations(version, name)
VALUES (29, 'workforce tenant atomic snapshot')
ON CONFLICT (version) DO NOTHING;
