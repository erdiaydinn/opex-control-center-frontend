-- Workforce V41: cryptographic scanner authority for request-level recruitment evidence.
-- Request evidence (planned departure / resignation proof) is encrypted in V40;
-- V41 prevents it from being treated as reviewable until an exact, signed,
-- replay-safe scanner receipt has been atomically recorded.

CREATE TABLE IF NOT EXISTS recruitment.request_evidence_scan_receipts (
  tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
  scan_receipt_id uuid NOT NULL,
  request_id text NOT NULL CHECK (btrim(request_id) <> ''),
  evidence_id uuid NOT NULL,
  provider text NOT NULL CHECK (btrim(provider) <> ''),
  provider_key_id text NOT NULL CHECK (btrim(provider_key_id) <> ''),
  receipt_id text NOT NULL CHECK (btrim(receipt_id) <> ''),
  evidence_sha256 bytea NOT NULL CHECK (octet_length(evidence_sha256) = 32),
  result text NOT NULL CHECK (result IN ('CLEAN','INFECTED','ERROR')),
  algorithm text NOT NULL CHECK (algorithm = 'HMAC-SHA256'),
  signed_payload_sha256 bytea NOT NULL CHECK (octet_length(signed_payload_sha256) = 32),
  signature_sha256 bytea NOT NULL CHECK (octet_length(signature_sha256) = 32),
  scanned_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  signature_verified boolean NOT NULL CHECK (signature_verified),
  PRIMARY KEY (tenant_id, scan_receipt_id),
  UNIQUE (tenant_id, provider, receipt_id),
  UNIQUE (tenant_id, request_id, evidence_id, provider, receipt_id)
);

CREATE INDEX IF NOT EXISTS request_evidence_scan_receipt_subject_idx
  ON recruitment.request_evidence_scan_receipts(
    tenant_id, request_id, evidence_id, scanned_at DESC
  );

ALTER TABLE recruitment.request_evidence_scan_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE recruitment.request_evidence_scan_receipts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS request_evidence_scan_tenant_policy
  ON recruitment.request_evidence_scan_receipts;
CREATE POLICY request_evidence_scan_tenant_policy
  ON recruitment.request_evidence_scan_receipts
  USING (tenant_id = public.workforce_current_tenant())
  WITH CHECK (tenant_id = public.workforce_current_tenant());

DROP TRIGGER IF EXISTS request_evidence_scan_receipt_no_update
  ON recruitment.request_evidence_scan_receipts;
CREATE TRIGGER request_evidence_scan_receipt_no_update
BEFORE UPDATE OR DELETE ON recruitment.request_evidence_scan_receipts
FOR EACH ROW EXECUTE FUNCTION recruitment.reject_candidate_authority_mutation();

CREATE OR REPLACE FUNCTION recruitment.record_request_evidence_scan_receipt(
  p_tenant_id text,
  p_scan_receipt_id uuid,
  p_request_id text,
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
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_payload jsonb;
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR p_scan_receipt_id IS NULL
     OR p_evidence_id IS NULL
     OR NULLIF(btrim(p_request_id), '') IS NULL
     OR NULLIF(btrim(p_provider), '') IS NULL
     OR NULLIF(btrim(p_provider_key_id), '') IS NULL
     OR NULLIF(btrim(p_receipt_id), '') IS NULL
     OR p_evidence_sha256 IS NULL
     OR octet_length(p_evidence_sha256) <> 32
     OR p_result NOT IN ('CLEAN','INFECTED','ERROR')
     OR p_algorithm IS DISTINCT FROM 'HMAC-SHA256'
     OR p_signed_payload_sha256 IS NULL
     OR octet_length(p_signed_payload_sha256) <> 32
     OR p_signature_sha256 IS NULL
     OR octet_length(p_signature_sha256) <> 32
     OR p_scanned_at IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'request scanner receipt rejected';
  END IF;

  SELECT request.payload
    INTO v_payload
    FROM public.recruitment_requests AS request
   WHERE request.tenant_id = p_tenant_id
     AND request.id = p_request_id
   FOR UPDATE;

  IF NOT FOUND
     OR v_payload->'evidence' IS NULL
     OR v_payload->'evidence'->>'id' IS DISTINCT FROM p_evidence_id::text
     OR v_payload->'evidence'->>'sha256' IS DISTINCT FROM encode(p_evidence_sha256, 'hex')
     OR COALESCE(v_payload->'evidence'->>'storage_backend', '') <> 'S3_KMS_ENVELOPE' THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'request scanner receipt rejected';
  END IF;

  INSERT INTO recruitment.request_evidence_scan_receipts (
    tenant_id, scan_receipt_id, request_id, evidence_id, provider,
    provider_key_id, receipt_id, evidence_sha256, result, algorithm,
    signed_payload_sha256, signature_sha256, scanned_at, signature_verified
  ) VALUES (
    p_tenant_id, p_scan_receipt_id, p_request_id, p_evidence_id, p_provider,
    p_provider_key_id, p_receipt_id, p_evidence_sha256, p_result, p_algorithm,
    p_signed_payload_sha256, p_signature_sha256, p_scanned_at, true
  );

  RETURN p_scan_receipt_id;
EXCEPTION
  WHEN SQLSTATE '28000' THEN
    RAISE;
  WHEN OTHERS THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'request scanner receipt rejected';
END;
$$;

REVOKE ALL ON TABLE recruitment.request_evidence_scan_receipts FROM PUBLIC;
REVOKE ALL ON FUNCTION recruitment.record_request_evidence_scan_receipt(
  text, uuid, text, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eay_candidate_scanner_runtime') THEN
    REVOKE ALL ON recruitment.request_evidence_scan_receipts
      FROM eay_candidate_scanner_runtime;
    GRANT USAGE ON SCHEMA recruitment TO eay_candidate_scanner_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.record_request_evidence_scan_receipt(
      text, uuid, text, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) TO eay_candidate_scanner_runtime;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'workforce_runtime') THEN
    REVOKE ALL ON recruitment.request_evidence_scan_receipts FROM workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.record_request_evidence_scan_receipt(
      text, uuid, text, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) TO workforce_runtime;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (41, 'request recruitment evidence cryptographic scanner authority')
ON CONFLICT (version) DO NOTHING;
