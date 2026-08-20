-- Workforce V39: tenant-scoped candidate upload authority.
-- Raw bearer secrets never enter this schema; only 32-byte SHA-256 digests do.

CREATE SCHEMA IF NOT EXISTS recruitment;

CREATE TABLE IF NOT EXISTS recruitment.candidate_upload_capabilities (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  capability_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  token_sha256 bytea NOT NULL CHECK (octet_length(token_sha256) = 32),
  document_type text NOT NULL CHECK (document_type IN (
    'CRIMINAL_RECORD','RESIDENCE','SGK_SERVICE','MILITARY_STATUS',
    'EDUCATION','CIVIL_REGISTRY','OTHER'
  )),
  staging_object_key text NOT NULL CHECK (btrim(staging_object_key) <> ''),
  max_bytes bigint NOT NULL DEFAULT 10485760 CHECK (max_bytes BETWEEN 1 AND 10485760),
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  issued_by text NOT NULL CHECK (btrim(issued_by) <> ''),
  revoked_at timestamptz,
  revoked_by text,
  revoke_reason text,
  consumed_at timestamptz,
  consumed_evidence_id uuid,
  PRIMARY KEY (tenant_id, capability_id),
  UNIQUE (token_sha256),
  UNIQUE (tenant_id, staging_object_key),
  UNIQUE (
    tenant_id, capability_id, request_id, candidate_id,
    document_type, staging_object_key
  ),
  CHECK (expires_at > issued_at),
  CHECK ((revoked_at IS NULL AND revoked_by IS NULL) OR
         (revoked_at IS NOT NULL AND btrim(revoked_by) <> '')),
  CHECK (NOT (revoked_at IS NOT NULL AND consumed_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS candidate_upload_active_expiry_idx
  ON recruitment.candidate_upload_capabilities(expires_at)
  WHERE consumed_at IS NULL AND revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS candidate_upload_subject_idx
  ON recruitment.candidate_upload_capabilities(
    tenant_id, request_id, candidate_id, issued_at DESC
  );

CREATE TABLE IF NOT EXISTS recruitment.candidate_evidence_objects (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  evidence_id uuid NOT NULL,
  capability_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  candidate_id text NOT NULL CHECK (btrim(candidate_id) <> ''),
  document_type text NOT NULL CHECK (document_type IN (
    'CRIMINAL_RECORD','RESIDENCE','SGK_SERVICE','MILITARY_STATUS',
    'EDUCATION','CIVIL_REGISTRY','OTHER'
  )),
  object_key text NOT NULL CHECK (btrim(object_key) <> ''),
  original_name text NOT NULL CHECK (btrim(original_name) <> ''),
  media_type text NOT NULL CHECK (media_type IN ('application/pdf','image/jpeg','image/png')),
  byte_size bigint NOT NULL CHECK (byte_size BETWEEN 1 AND 10485760),
  sha256 bytea NOT NULL CHECK (octet_length(sha256) = 32),
  uploaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  retention_until timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, evidence_id),
  UNIQUE (tenant_id, capability_id),
  UNIQUE (tenant_id, capability_id, evidence_id),
  UNIQUE (tenant_id, evidence_id, sha256),
  UNIQUE (tenant_id, object_key),
  FOREIGN KEY (tenant_id, capability_id)
    REFERENCES recruitment.candidate_upload_capabilities(tenant_id, capability_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, capability_id, request_id, candidate_id, document_type, object_key
  ) REFERENCES recruitment.candidate_upload_capabilities(
    tenant_id, capability_id, request_id, candidate_id, document_type, staging_object_key
  ) ON DELETE RESTRICT,
  CHECK (retention_until > uploaded_at)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'candidate_capability_consumed_evidence_fk'
      AND conrelid = 'recruitment.candidate_upload_capabilities'::regclass
  ) THEN
    ALTER TABLE recruitment.candidate_upload_capabilities
      ADD CONSTRAINT candidate_capability_consumed_evidence_fk
      FOREIGN KEY (tenant_id, capability_id, consumed_evidence_id)
      REFERENCES recruitment.candidate_evidence_objects(tenant_id, capability_id, evidence_id)
      DEFERRABLE INITIALLY DEFERRED;
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS candidate_evidence_subject_idx
  ON recruitment.candidate_evidence_objects(
    tenant_id, request_id, candidate_id, uploaded_at DESC
  );

CREATE TABLE IF NOT EXISTS recruitment.candidate_evidence_scan_receipts (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  scan_receipt_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  provider text NOT NULL CHECK (btrim(provider) <> ''),
  provider_key_id text NOT NULL CHECK (btrim(provider_key_id) <> ''),
  receipt_id text NOT NULL CHECK (btrim(receipt_id) <> ''),
  evidence_sha256 bytea NOT NULL CHECK (octet_length(evidence_sha256) = 32),
  result text NOT NULL CHECK (result IN ('CLEAN','INFECTED','ERROR')),
  algorithm text NOT NULL CHECK (algorithm IN ('HMAC-SHA256')),
  signed_payload_sha256 bytea NOT NULL CHECK (octet_length(signed_payload_sha256) = 32),
  signature_sha256 bytea NOT NULL CHECK (octet_length(signature_sha256) = 32),
  scanned_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  signature_verified boolean NOT NULL CHECK (signature_verified),
  PRIMARY KEY (tenant_id, scan_receipt_id),
  UNIQUE (tenant_id, provider, receipt_id),
  FOREIGN KEY (tenant_id, evidence_id, evidence_sha256)
    REFERENCES recruitment.candidate_evidence_objects(tenant_id, evidence_id, sha256)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS candidate_scan_receipt_evidence_idx
  ON recruitment.candidate_evidence_scan_receipts(
    tenant_id, evidence_id, scanned_at DESC
  );

CREATE OR REPLACE FUNCTION recruitment.reject_candidate_authority_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, recruitment
AS $$
BEGIN
  RAISE EXCEPTION 'candidate upload authority records are append-only'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.guard_candidate_capability_transition()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, recruitment
AS $$
BEGIN
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.capability_id IS DISTINCT FROM NEW.capability_id
     OR OLD.request_id IS DISTINCT FROM NEW.request_id
     OR OLD.candidate_id IS DISTINCT FROM NEW.candidate_id
     OR OLD.token_sha256 IS DISTINCT FROM NEW.token_sha256
     OR OLD.document_type IS DISTINCT FROM NEW.document_type
     OR OLD.staging_object_key IS DISTINCT FROM NEW.staging_object_key
     OR OLD.max_bytes IS DISTINCT FROM NEW.max_bytes
     OR OLD.issued_at IS DISTINCT FROM NEW.issued_at
     OR OLD.expires_at IS DISTINCT FROM NEW.expires_at
     OR OLD.issued_by IS DISTINCT FROM NEW.issued_by THEN
    RAISE EXCEPTION 'candidate upload capability authority is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.revoked_at IS NOT NULL OR OLD.consumed_at IS NOT NULL THEN
    RAISE EXCEPTION 'terminal candidate upload capability cannot change'
      USING ERRCODE = '55000';
  END IF;
  IF (NEW.revoked_at IS NULL) = (NEW.consumed_at IS NULL) THEN
    RAISE EXCEPTION 'capability must transition to exactly one terminal state'
      USING ERRCODE = '55000';
  END IF;
  IF NEW.consumed_at IS NOT NULL AND NEW.consumed_evidence_id IS NULL THEN
    RAISE EXCEPTION 'consumed capability requires evidence authority'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS candidate_capability_terminal_transition
  ON recruitment.candidate_upload_capabilities;
CREATE TRIGGER candidate_capability_terminal_transition
BEFORE UPDATE ON recruitment.candidate_upload_capabilities
FOR EACH ROW EXECUTE FUNCTION recruitment.guard_candidate_capability_transition();

DROP TRIGGER IF EXISTS candidate_capability_no_delete
  ON recruitment.candidate_upload_capabilities;
CREATE TRIGGER candidate_capability_no_delete
BEFORE DELETE ON recruitment.candidate_upload_capabilities
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_candidate_authority_mutation();

DROP TRIGGER IF EXISTS candidate_evidence_no_update ON recruitment.candidate_evidence_objects;
CREATE TRIGGER candidate_evidence_no_update
BEFORE UPDATE OR DELETE ON recruitment.candidate_evidence_objects
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_candidate_authority_mutation();

DROP TRIGGER IF EXISTS candidate_scan_receipt_no_update ON recruitment.candidate_evidence_scan_receipts;
CREATE TRIGGER candidate_scan_receipt_no_update
BEFORE UPDATE OR DELETE ON recruitment.candidate_evidence_scan_receipts
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_candidate_authority_mutation();

-- The upload runtime receives EXECUTE only.  It cannot insert evidence or mark a
-- capability consumed in two independent statements.  The row lock makes a
-- concurrent replay serialize behind the first successful finalization.
CREATE OR REPLACE FUNCTION recruitment.finalize_candidate_evidence_upload(
  p_tenant_id text,
  p_token_sha256 bytea,
  p_document_type text,
  p_evidence_id uuid,
  p_original_name text,
  p_media_type text,
  p_byte_size bigint,
  p_evidence_sha256 bytea,
  p_retention_until timestamptz
)
RETURNS TABLE (
  evidence_id uuid,
  capability_id uuid,
  request_id text,
  candidate_id text,
  document_type text,
  object_key text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_capability recruitment.candidate_upload_capabilities%ROWTYPE;
  v_now timestamptz := clock_timestamp();
BEGIN
  -- Tenant context is an independent authority; a caller-controlled argument
  -- can never select a different tenant.
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR p_token_sha256 IS NULL
     OR octet_length(p_token_sha256) <> 32
     OR p_evidence_sha256 IS NULL
     OR octet_length(p_evidence_sha256) <> 32 THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
  END IF;

  SELECT * INTO v_capability
    FROM recruitment.candidate_upload_capabilities
   WHERE tenant_id = p_tenant_id
     AND token_sha256 = p_token_sha256
   FOR UPDATE;

  IF NOT FOUND
     OR v_capability.document_type IS DISTINCT FROM p_document_type
     OR v_capability.revoked_at IS NOT NULL
     OR v_capability.consumed_at IS NOT NULL
     OR v_capability.expires_at <= v_now
     OR p_byte_size IS NULL
     OR p_byte_size < 1
     OR p_byte_size > v_capability.max_bytes
     OR p_retention_until IS NULL
     OR p_retention_until <= v_now THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
  END IF;

  INSERT INTO recruitment.candidate_evidence_objects (
    tenant_id, evidence_id, capability_id, request_id, candidate_id,
    document_type, object_key, original_name, media_type, byte_size, sha256,
    uploaded_at, retention_until
  ) VALUES (
    p_tenant_id, p_evidence_id, v_capability.capability_id,
    v_capability.request_id, v_capability.candidate_id,
    v_capability.document_type, v_capability.staging_object_key,
    p_original_name, p_media_type, p_byte_size,
    p_evidence_sha256, v_now, p_retention_until
  );

  UPDATE recruitment.candidate_upload_capabilities AS capability
     SET consumed_at = v_now, consumed_evidence_id = p_evidence_id
   WHERE capability.tenant_id = p_tenant_id
     AND capability.capability_id = v_capability.capability_id;

  RETURN QUERY SELECT
    p_evidence_id,
    v_capability.capability_id,
    v_capability.request_id,
    v_capability.candidate_id,
    v_capability.document_type,
    v_capability.staging_object_key;
EXCEPTION
  WHEN SQLSTATE '28000' THEN
    RAISE;
  WHEN OTHERS THEN
    -- Do not expose constraint names, object existence, or conflicting IDs.
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.issue_candidate_upload_capability(
  p_tenant_id text,
  p_capability_id uuid,
  p_request_id text,
  p_candidate_id text,
  p_token_sha256 bytea,
  p_document_type text,
  p_staging_object_key text,
  p_max_bytes bigint,
  p_expires_at timestamptz,
  p_issued_by text
)
RETURNS TABLE (
  capability_id uuid,
  request_id text,
  candidate_id text,
  document_type text,
  staging_object_key text,
  expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_now timestamptz := clock_timestamp();
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR p_token_sha256 IS NULL
     OR octet_length(p_token_sha256) <> 32
     OR p_expires_at IS NULL
     OR p_expires_at <= v_now THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate capability rejected';
  END IF;

  INSERT INTO recruitment.candidate_upload_capabilities (
    tenant_id, capability_id, request_id, candidate_id, token_sha256,
    document_type, staging_object_key, max_bytes, issued_at, expires_at, issued_by
  ) VALUES (
    p_tenant_id, p_capability_id, p_request_id, p_candidate_id, p_token_sha256,
    p_document_type, p_staging_object_key, p_max_bytes, v_now, p_expires_at, p_issued_by
  );

  RETURN QUERY SELECT p_capability_id, p_request_id, p_candidate_id,
    p_document_type, p_staging_object_key, p_expires_at;
EXCEPTION
  WHEN SQLSTATE '28000' THEN
    RAISE;
  WHEN OTHERS THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate capability rejected';
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.get_candidate_evidence_scan_binding(
  p_tenant_id text,
  p_evidence_id uuid
)
RETURNS TABLE (request_id text, candidate_id text, evidence_sha256 bytea)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant() THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'scanner receipt rejected';
  END IF;
  RETURN QUERY
    SELECT evidence.request_id, evidence.candidate_id, evidence.sha256
      FROM recruitment.candidate_evidence_objects AS evidence
     WHERE evidence.tenant_id = p_tenant_id AND evidence.evidence_id = p_evidence_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'scanner receipt rejected';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.record_candidate_evidence_scan_receipt(
  p_tenant_id text,
  p_scan_receipt_id uuid,
  p_evidence_id uuid,
  p_provider text,
  p_provider_key_id text,
  p_receipt_id text,
  p_evidence_sha256 bytea,
  p_result text,
  p_algorithm text,
  p_signed_payload_sha256 bytea,
  p_signature_sha256 bytea,
  p_scanned_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR p_result NOT IN ('CLEAN','INFECTED','ERROR')
     OR p_scanned_at IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'scanner receipt rejected';
  END IF;
  INSERT INTO recruitment.candidate_evidence_scan_receipts (
    tenant_id, scan_receipt_id, evidence_id, provider, provider_key_id,
    receipt_id, evidence_sha256, result, algorithm, signed_payload_sha256,
    signature_sha256, scanned_at, signature_verified
  ) VALUES (
    p_tenant_id, p_scan_receipt_id, p_evidence_id, p_provider, p_provider_key_id,
    p_receipt_id, p_evidence_sha256, p_result, p_algorithm,
    p_signed_payload_sha256, p_signature_sha256, p_scanned_at, true
  );
EXCEPTION
  WHEN OTHERS THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'scanner receipt rejected';
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.revoke_candidate_upload_capability(
  p_tenant_id text,
  p_capability_id uuid,
  p_revoked_by text,
  p_revoke_reason text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_capability recruitment.candidate_upload_capabilities%ROWTYPE;
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR NULLIF(btrim(p_revoked_by), '') IS NULL
     OR NULLIF(btrim(p_revoke_reason), '') IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate capability rejected';
  END IF;

  SELECT * INTO v_capability
    FROM recruitment.candidate_upload_capabilities
   WHERE tenant_id = p_tenant_id AND capability_id = p_capability_id
   FOR UPDATE;

  IF NOT FOUND OR v_capability.revoked_at IS NOT NULL OR v_capability.consumed_at IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate capability rejected';
  END IF;

  UPDATE recruitment.candidate_upload_capabilities
     SET revoked_at = clock_timestamp(),
         revoked_by = p_revoked_by,
         revoke_reason = p_revoke_reason
   WHERE tenant_id = p_tenant_id AND capability_id = p_capability_id;
EXCEPTION
  WHEN SQLSTATE '28000' THEN
    RAISE;
  WHEN OTHERS THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate capability rejected';
END;
$$;

ALTER TABLE recruitment.candidate_upload_capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment.candidate_upload_capabilities FORCE ROW LEVEL SECURITY;
ALTER TABLE recruitment.candidate_evidence_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment.candidate_evidence_objects FORCE ROW LEVEL SECURITY;
ALTER TABLE recruitment.candidate_evidence_scan_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment.candidate_evidence_scan_receipts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS candidate_upload_capability_tenant ON recruitment.candidate_upload_capabilities;
CREATE POLICY candidate_upload_capability_tenant ON recruitment.candidate_upload_capabilities
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());
DROP POLICY IF EXISTS candidate_evidence_object_tenant ON recruitment.candidate_evidence_objects;
CREATE POLICY candidate_evidence_object_tenant ON recruitment.candidate_evidence_objects
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());
DROP POLICY IF EXISTS candidate_scan_receipt_tenant ON recruitment.candidate_evidence_scan_receipts;
CREATE POLICY candidate_scan_receipt_tenant ON recruitment.candidate_evidence_scan_receipts
  USING (tenant_id = workforce_current_tenant())
  WITH CHECK (tenant_id = workforce_current_tenant());

REVOKE ALL ON ALL TABLES IN SCHEMA recruitment FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA recruitment FROM PUBLIC;

-- Role creation and membership remain deployment authority.  If the dedicated
-- roles exist, grant only the narrow routines and never direct table access.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eay_candidate_upload_runtime') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA recruitment FROM eay_candidate_upload_runtime;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA recruitment FROM eay_candidate_upload_runtime;
    GRANT USAGE ON SCHEMA recruitment TO eay_candidate_upload_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.finalize_candidate_evidence_upload(
      text, bytea, text, uuid, text, text, bigint, bytea, timestamptz
    ) TO eay_candidate_upload_runtime;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eay_recruitment_runtime') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA recruitment FROM eay_recruitment_runtime;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA recruitment FROM eay_recruitment_runtime;
    GRANT USAGE ON SCHEMA recruitment TO eay_recruitment_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.issue_candidate_upload_capability(
      text, uuid, text, text, bytea, text, text, bigint, timestamptz, text
    ) TO eay_recruitment_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.revoke_candidate_upload_capability(
      text, uuid, text, text
    ) TO eay_recruitment_runtime;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eay_candidate_scanner_runtime') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA recruitment FROM eay_candidate_scanner_runtime;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA recruitment FROM eay_candidate_scanner_runtime;
    GRANT USAGE ON SCHEMA recruitment TO eay_candidate_scanner_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.get_candidate_evidence_scan_binding(
      text, uuid
    ) TO eay_candidate_scanner_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.record_candidate_evidence_scan_receipt(
      text, uuid, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) TO eay_candidate_scanner_runtime;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (39, 'tenant scoped recruitment candidate upload authority')
ON CONFLICT (version) DO NOTHING;
