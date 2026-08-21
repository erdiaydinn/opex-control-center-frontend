-- Workforce V43: isolate cryptographic scanner writes from the main API role.
-- The user-facing workforce_runtime can ask release-authority questions but can
-- no longer create scanner receipts. A dedicated tenant-bound scanner login gets
-- only the projection/audit columns needed to commit a verified receipt and its
-- aggregate state in one transaction.

DO $$
DECLARE
  v_audit_sequence text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'workforce_runtime') THEN
    REVOKE EXECUTE ON FUNCTION recruitment.get_candidate_evidence_scan_binding(
      text, uuid
    ) FROM workforce_runtime;
    REVOKE EXECUTE ON FUNCTION recruitment.record_candidate_evidence_scan_receipt(
      text, uuid, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) FROM workforce_runtime;
    REVOKE EXECUTE ON FUNCTION recruitment.record_request_evidence_scan_receipt(
      text, uuid, text, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) FROM workforce_runtime;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eay_candidate_scanner_runtime') THEN
    GRANT USAGE ON SCHEMA public, recruitment TO eay_candidate_scanner_runtime;
    GRANT EXECUTE ON FUNCTION public.workforce_current_tenant()
      TO eay_candidate_scanner_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.get_candidate_evidence_scan_binding(
      text, uuid
    ) TO eay_candidate_scanner_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.record_candidate_evidence_scan_receipt(
      text, uuid, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) TO eay_candidate_scanner_runtime;
    GRANT EXECUTE ON FUNCTION recruitment.record_request_evidence_scan_receipt(
      text, uuid, text, uuid, text, text, text, bytea, text, text, bytea, bytea, timestamptz
    ) TO eay_candidate_scanner_runtime;

    GRANT SELECT (tenant_id, id, revision, payload)
      ON public.recruitment_requests TO eay_candidate_scanner_runtime;
    GRANT UPDATE (revision, payload)
      ON public.recruitment_requests TO eay_candidate_scanner_runtime;
    GRANT SELECT, INSERT ON public.workforce_audit TO eay_candidate_scanner_runtime;

    v_audit_sequence := pg_get_serial_sequence('public.workforce_audit', 'sequence');
    IF v_audit_sequence IS NOT NULL THEN
      EXECUTE format(
        'GRANT USAGE, SELECT ON SEQUENCE %s TO eay_candidate_scanner_runtime',
        v_audit_sequence
      );
    END IF;
  END IF;
END;
$$;

INSERT INTO workforce_schema_migrations(version, name)
VALUES (43, 'dedicated recruitment scanner database role')
ON CONFLICT (version) DO NOTHING;
