-- Workforce V32: durable corporate identity/session revocation coupled to
-- employment exit. The outbox is tenant-scoped and idempotent; no biometric
-- image or template is stored.

CREATE TABLE IF NOT EXISTS workforce_identity_revocation_outbox (
  tenant_id text NOT NULL,
  id text NOT NULL,
  employee_id text NOT NULL,
  provider text NOT NULL DEFAULT 'CORPORATE_OIDC',
  status text NOT NULL DEFAULT 'PENDING',
  attempts integer NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  next_attempt_at timestamptz,
  delivered_at timestamptz,
  payload jsonb NOT NULL,
  PRIMARY KEY (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS workforce_identity_revocation_due_idx
  ON workforce_identity_revocation_outbox(tenant_id, status, next_attempt_at, created_at);

ALTER TABLE workforce_identity_revocation_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE workforce_identity_revocation_outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workforce_identity_revocation_tenant ON workforce_identity_revocation_outbox;
CREATE POLICY workforce_identity_revocation_tenant ON workforce_identity_revocation_outbox
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

INSERT INTO workforce_schema_migrations(version, name)
VALUES (32, 'durable employment exit identity revocation')
ON CONFLICT (version) DO NOTHING;
