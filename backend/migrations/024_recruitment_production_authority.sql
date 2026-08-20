-- Workforce V40: encrypted recruitment evidence production authority.
-- V39 created the tenant-scoped append-only authority. V40 adds the production
-- KMS/S3 storage contract while keeping runtime roles off the authority tables.

ALTER TABLE recruitment.candidate_evidence_objects
  ADD COLUMN IF NOT EXISTS storage_backend text NOT NULL DEFAULT 'LEGACY_LOCAL',
  ADD COLUMN IF NOT EXISTS storage_bucket text,
  ADD COLUMN IF NOT EXISTS encryption_scheme text,
  ADD COLUMN IF NOT EXISTS kms_key_id text,
  ADD COLUMN IF NOT EXISTS envelope_version integer;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'candidate_evidence_storage_contract'
      AND conrelid = 'recruitment.candidate_evidence_objects'::regclass
  ) THEN
    ALTER TABLE recruitment.candidate_evidence_objects
      ADD CONSTRAINT candidate_evidence_storage_contract CHECK (
        (
          storage_backend = 'LEGACY_LOCAL'
          AND storage_bucket IS NULL
          AND encryption_scheme IS NULL
          AND kms_key_id IS NULL
          AND envelope_version IS NULL
        )
        OR
        (
          storage_backend = 'S3_KMS_ENVELOPE'
          AND NULLIF(btrim(storage_bucket), '') IS NOT NULL
          AND encryption_scheme = 'AES-256-GCM+AWS-KMS-DATA-KEY'
          AND NULLIF(btrim(kms_key_id), '') IS NOT NULL
          AND envelope_version = 1
        )
      );
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.prepare_candidate_evidence_upload(
  p_tenant_id text,
  p_token_sha256 bytea,
  p_document_type text,
  p_byte_size bigint,
  p_evidence_sha256 bytea
)
RETURNS TABLE (
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
BEGIN
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR p_token_sha256 IS NULL
     OR octet_length(p_token_sha256) <> 32
     OR p_evidence_sha256 IS NULL
     OR octet_length(p_evidence_sha256) <> 32
     OR p_byte_size IS NULL
     OR p_byte_size < 1 THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
  END IF;

  SELECT capability.*
    INTO v_capability
    FROM recruitment.candidate_upload_capabilities AS capability
   WHERE capability.tenant_id = p_tenant_id
     AND capability.token_sha256 = p_token_sha256
   FOR UPDATE;

  IF NOT FOUND
     OR v_capability.document_type IS DISTINCT FROM p_document_type
     OR v_capability.revoked_at IS NOT NULL
     OR v_capability.consumed_at IS NOT NULL
     OR v_capability.expires_at <= clock_timestamp()
     OR p_byte_size > v_capability.max_bytes THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
  END IF;

  RETURN QUERY SELECT
    v_capability.capability_id,
    v_capability.request_id,
    v_capability.candidate_id,
    v_capability.document_type,
    v_capability.staging_object_key;
END;
$$;

CREATE OR REPLACE FUNCTION recruitment.finalize_candidate_evidence_upload_v2(
  p_tenant_id text,
  p_token_sha256 bytea,
  p_document_type text,
  p_evidence_id uuid,
  p_original_name text,
  p_media_type text,
  p_byte_size bigint,
  p_evidence_sha256 bytea,
  p_retention_until timestamptz,
  p_storage_bucket text,
  p_encryption_scheme text,
  p_kms_key_id text,
  p_envelope_version integer
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
  IF p_tenant_id IS DISTINCT FROM public.workforce_current_tenant()
     OR p_token_sha256 IS NULL
     OR octet_length(p_token_sha256) <> 32
     OR p_evidence_sha256 IS NULL
     OR octet_length(p_evidence_sha256) <> 32
     OR p_byte_size IS NULL
     OR p_byte_size < 1
     OR p_retention_until IS NULL
     OR p_retention_until <= v_now
     OR NULLIF(btrim(p_storage_bucket), '') IS NULL
     OR p_encryption_scheme IS DISTINCT FROM 'AES-256-GCM+AWS-KMS-DATA-KEY'
     OR NULLIF(btrim(p_kms_key_id), '') IS NULL
     OR p_envelope_version IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
  END IF;

  SELECT capability.*
    INTO v_capability
    FROM recruitment.candidate_upload_capabilities AS capability
   WHERE capability.tenant_id = p_tenant_id
     AND capability.token_sha256 = p_token_sha256
   FOR UPDATE;

  IF NOT FOUND
     OR v_capability.document_type IS DISTINCT FROM p_document_type
     OR v_capability.revoked_at IS NOT NULL
     OR v_capability.consumed_at IS NOT NULL
     OR v_capability.expires_at <= v_now
     OR p_byte_size > v_capability.max_bytes THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
  END IF;

  INSERT INTO recruitment.candidate_evidence_objects (
    tenant_id, evidence_id, capability_id, request_id, candidate_id,
    document_type, object_key, original_name, media_type, byte_size, sha256,
    uploaded_at, retention_until, storage_backend, storage_bucket,
    encryption_scheme, kms_key_id, envelope_version
  ) VALUES (
    p_tenant_id, p_evidence_id, v_capability.capability_id,
    v_capability.request_id, v_capability.candidate_id,
    v_capability.document_type, v_capability.staging_object_key,
    p_original_name, p_media_type, p_byte_size, p_evidence_sha256,
    v_now, p_retention_until, 'S3_KMS_ENVELOPE', p_storage_bucket,
    p_encryption_scheme, p_kms_key_id, p_envelope_version
  );

  UPDATE recruitment.candidate_upload_capabilities AS capability
     SET consumed_at = v_now,
         consumed_evidence_id = p_evidence_id
   WHERE capability.tenant_id = p_tenant_id
     AND capability.capability_id = v_capability.capability_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
  END IF;

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
    RAISE EXCEPTION USING ERRCODE = '28000', MESSAGE = 'candidate upload rejected';
END;
$$;

REVOKE ALL ON FUNCTION recruitment.prepare_candidate_evidence_upload(
  text, bytea, text, bigint, bytea
) FROM PUBLIC;
REVOKE ALL ON FUNCTION recruitment.finalize_candidate_evidence_upload_v2(
  text, bytea, text, uuid, text, text, bigint, bytea, timestamptz,
  text, text, text, integer
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eay_candidate_upload_runtime') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA recruitment FROM eay_candidate_upload_runtime;
    REVOKE EXECUTE ON FUNCTION recruitment.finalize_candidate_evidence_upload(
      text, bytea, text, uuid, text, text, bigint, bytea, timestamptz
    ) FROM eay_candidate_upload_runtime;
    GRANT USAGE ON SCHEMA recruitment TO eay_candidate_upload_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.prepare_candidate_evidence_upload(
      text, bytea, text, bigint, bytea
    ) TO eay_candidate_upload_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.finalize_candidate_evidence_upload_v2(
      text, bytea, text, uuid, text, text, bigint, bytea, timestamptz,
      text, text, text, integer
    ) TO eay_candidate_upload_runtime;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'workforce_runtime') THEN
    REVOKE ALL ON recruitment.candidate_upload_capabilities,
                  recruitment.candidate_evidence_objects,
                  recruitment.candidate_evidence_scan_receipts
      FROM workforce_runtime;
    REVOKE EXECUTE ON FUNCTION recruitment.finalize_candidate_evidence_upload(
      text, bytea, text, uuid, text, text, bigint, bytea, timestamptz
    ) FROM workforce_runtime;
    GRANT USAGE ON SCHEMA recruitment TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.issue_candidate_upload_capability(
      text, uuid, text, text, bytea, text, text, bigint, timestamptz, text
    ) TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.revoke_candidate_upload_capability(
      text, uuid, text, text
    ) TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.prepare_candidate_evidence_upload(
      text, bytea, text, bigint, bytea
    ) TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.finalize_candidate_evidence_upload_v2(
      text, bytea, text, uuid, text, text, bigint, bytea, timestamptz,
      text, text, text, integer
    ) TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.get_candidate_evidence_scan_binding(
      text, uuid
    ) TO workforce_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.record_candidate_evidence_scan_receipt(
      text, uuid, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) TO workforce_runtime;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (40, 'encrypted recruitment evidence production authority')
ON CONFLICT (version) DO NOTHING;
