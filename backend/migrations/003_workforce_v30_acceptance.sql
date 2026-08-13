-- Workforce V30: production acceptance, durable notification retry and
-- tenant-scoped Recruitment truth. Apply after 002_workforce_v29.sql.

ALTER TABLE workforce_notification_outbox
  ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;

CREATE TABLE IF NOT EXISTS recruitment_requests (
  tenant_id text NOT NULL,
  id text NOT NULL,
  status text NOT NULL,
  warehouse_id text NOT NULL,
  revision bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  payload jsonb NOT NULL,
  PRIMARY KEY (tenant_id, id)
);
ALTER TABLE recruitment_requests ADD COLUMN IF NOT EXISTS tenant_id text;
ALTER TABLE recruitment_requests ADD COLUMN IF NOT EXISTS revision bigint NOT NULL DEFAULT 1;
UPDATE recruitment_requests
SET tenant_id = COALESCE(NULLIF(current_setting('app.workforce_tenant', true), ''), 'eay')
WHERE tenant_id IS NULL;
ALTER TABLE recruitment_requests ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE recruitment_requests DROP CONSTRAINT IF EXISTS recruitment_requests_pkey;
ALTER TABLE recruitment_requests ADD PRIMARY KEY (tenant_id, id);
DROP INDEX IF EXISTS recruitment_request_status_idx;
CREATE INDEX recruitment_request_status_idx
  ON recruitment_requests(tenant_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS recruitment_settings (
  tenant_id text NOT NULL,
  id text NOT NULL,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, id)
);
ALTER TABLE recruitment_settings ADD COLUMN IF NOT EXISTS tenant_id text;
UPDATE recruitment_settings
SET tenant_id = COALESCE(NULLIF(current_setting('app.workforce_tenant', true), ''), 'eay')
WHERE tenant_id IS NULL;
ALTER TABLE recruitment_settings ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE recruitment_settings DROP CONSTRAINT IF EXISTS recruitment_settings_pkey;
ALTER TABLE recruitment_settings ADD PRIMARY KEY (tenant_id, id);

CREATE TABLE IF NOT EXISTS recruitment_norms (
  tenant_id text NOT NULL,
  id text NOT NULL,
  warehouse text NOT NULL,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, id)
);
ALTER TABLE recruitment_norms ADD COLUMN IF NOT EXISTS tenant_id text;
UPDATE recruitment_norms
SET tenant_id = COALESCE(NULLIF(current_setting('app.workforce_tenant', true), ''), 'eay')
WHERE tenant_id IS NULL;
ALTER TABLE recruitment_norms ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE recruitment_norms DROP CONSTRAINT IF EXISTS recruitment_norms_pkey;
ALTER TABLE recruitment_norms ADD PRIMARY KEY (tenant_id, id);
DROP INDEX IF EXISTS recruitment_norm_warehouse_idx;
CREATE UNIQUE INDEX IF NOT EXISTS recruitment_norm_tenant_warehouse_idx
  ON recruitment_norms(tenant_id, lower(warehouse));

CREATE TABLE IF NOT EXISTS recruitment_email_outbox (
  tenant_id text NOT NULL,
  id text NOT NULL,
  request_id text NOT NULL,
  recipient_group text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  attempts integer NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL,
  delivered_at timestamptz,
  payload jsonb NOT NULL,
  PRIMARY KEY (tenant_id, id)
);
ALTER TABLE recruitment_email_outbox ADD COLUMN IF NOT EXISTS tenant_id text;
ALTER TABLE recruitment_email_outbox ADD COLUMN IF NOT EXISTS locked_at timestamptz;
ALTER TABLE recruitment_email_outbox ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz;
ALTER TABLE recruitment_email_outbox ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;
UPDATE recruitment_email_outbox
SET tenant_id = COALESCE(NULLIF(current_setting('app.workforce_tenant', true), ''), 'eay')
WHERE tenant_id IS NULL;
ALTER TABLE recruitment_email_outbox ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE recruitment_email_outbox DROP CONSTRAINT IF EXISTS recruitment_email_outbox_pkey;
ALTER TABLE recruitment_email_outbox ADD PRIMARY KEY (tenant_id, id);
DROP INDEX IF EXISTS recruitment_outbox_status_idx;
CREATE INDEX recruitment_outbox_status_idx
  ON recruitment_email_outbox(tenant_id, status, next_attempt_at, created_at);

ALTER TABLE recruitment_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recruitment_requests_tenant ON recruitment_requests;
CREATE POLICY recruitment_requests_tenant ON recruitment_requests
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE recruitment_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment_settings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recruitment_settings_tenant ON recruitment_settings;
CREATE POLICY recruitment_settings_tenant ON recruitment_settings
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE recruitment_norms ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment_norms FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recruitment_norms_tenant ON recruitment_norms;
CREATE POLICY recruitment_norms_tenant ON recruitment_norms
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

ALTER TABLE recruitment_email_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment_email_outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS recruitment_outbox_tenant ON recruitment_email_outbox;
CREATE POLICY recruitment_outbox_tenant ON recruitment_email_outbox
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

INSERT INTO workforce_schema_migrations(version, name)
VALUES (30, 'workforce production acceptance and recruitment truth')
ON CONFLICT (version) DO NOTHING;
