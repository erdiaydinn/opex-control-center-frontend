-- Workforce V42: scanner-backed evidence release authority.
-- Aggregate JSON is not an authorization source. Production reads/approvals must
-- prove that the latest append-only cryptographic scanner receipt for the exact
-- tenant/request/candidate/evidence/SHA binding is CLEAN.

CREATE OR REPLACE FUNCTION recruitment.candidate_evidence_release_authorized(
  p_tenant_id text,
  p_request_id text,
  p_candidate_id text,
  p_evidence_id uuid,
  p_evidence_sha256 bytea
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_latest_result text;
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR NULLIF(btrim(p_request_id), '') IS NULL
     OR NULLIF(btrim(p_candidate_id), '') IS NULL
     OR p_evidence_id IS NULL
     OR p_evidence_sha256 IS NULL
     OR octet_length(p_evidence_sha256) <> 32 THEN
    RETURN false;
  END IF;

  IF NOT EXISTS (
    SELECT 1
      FROM recruitment.candidate_evidence_objects AS evidence
     WHERE evidence.tenant_id = p_tenant_id
       AND evidence.request_id = p_request_id
       AND evidence.candidate_id = p_candidate_id
       AND evidence.evidence_id = p_evidence_id
       AND evidence.sha256 = p_evidence_sha256
       AND evidence.storage_backend = 'S3_KMS_ENVELOPE'
  ) THEN
    RETURN false;
  END IF;

  SELECT receipt.result
    INTO v_latest_result
    FROM recruitment.candidate_evidence_scan_receipts AS receipt
   WHERE receipt.tenant_id = p_tenant_id
     AND receipt.evidence_id = p_evidence_id
     AND receipt.evidence_sha256 = p_evidence_sha256
   ORDER BY receipt.recorded_at DESC, receipt.scanned_at DESC, receipt.scan_receipt_id DESC
   LIMIT 1;

  RETURN COALESCE(v_latest_result = 'CLEAN', false);
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.request_evidence_release_authorized(
  p_tenant_id text,
  p_request_id text,
  p_evidence_id uuid,
  p_evidence_sha256 bytea
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_payload jsonb;
  v_latest_result text;
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR NULLIF(btrim(p_request_id), '') IS NULL
     OR p_evidence_id IS NULL
     OR p_evidence_sha256 IS NULL
     OR octet_length(p_evidence_sha256) <> 32 THEN
    RETURN false;
  END IF;

  SELECT request.payload
    INTO v_payload
    FROM public.recruitment_requests AS request
   WHERE request.tenant_id = p_tenant_id
     AND request.id = p_request_id;

  IF NOT FOUND
     OR v_payload->'evidence' IS NULL
     OR v_payload->'evidence'->>'id' IS DISTINCT FROM p_evidence_id::text
     OR v_payload->'evidence'->>'sha256' IS DISTINCT FROM encode(p_evidence_sha256, 'hex')
     OR COALESCE(v_payload->'evidence'->>'storage_backend', '') <> 'S3_KMS_ENVELOPE' THEN
    RETURN false;
  END IF;

  SELECT receipt.result
    INTO v_latest_result
    FROM recruitment.request_evidence_scan_receipts AS receipt
   WHERE receipt.tenant_id = p_tenant_id
     AND receipt.request_id = p_request_id
     AND receipt.evidence_id = p_evidence_id
     AND receipt.evidence_sha256 = p_evidence_sha256
   ORDER BY receipt.recorded_at DESC, receipt.scanned_at DESC, receipt.scan_receipt_id DESC
   LIMIT 1;

  RETURN COALESCE(v_latest_result = 'CLEAN', false);
END;
$$;

REVOKE ALL ON FUNCTION recruitment.candidate_evidence_release_authorized(
  text, text, text, uuid, bytea
) FROM PUBLIC;
REVOKE ALL ON FUNCTION recruitment.request_evidence_release_authorized(
  text, text, uuid, bytea
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'workforce_runtime') THEN
    GRANT USAGE ON SCHEMA recruitment TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.candidate_evidence_release_authorized(
      text, text, text, uuid, bytea
    ) TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.request_evidence_release_authorized(
      text, text, uuid, bytea
    ) TO workforce_runtime;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (42, 'cryptographic recruitment evidence release authority')
ON CONFLICT (version) DO NOTHING;
