"""Live, non-document production preflight for Hiring security authorities.

The preflight may contact AWS KMS/S3 and the authorized OAuth token endpoint,
but it never submits a citizen document or claims an official verification.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from app.modules.workforce import persistence
from .candidate_evidence_storage import EvidenceStorageError, S3KmsEnvelopeEvidenceStore
from .official_document_m2m import (
    AuthorizedOfficialM2MAdapter,
    OfficialM2MError,
    canonical_response_mapper,
)
from .scanner_key_authority import AwsKmsHmacKeyAuthority, ScannerKeyAuthorityError


class ProductionAuthorityPreflightError(RuntimeError):
    pass


def run_live_preflight() -> dict:
    checks: list[dict] = []

    schema = persistence.schema_version() if persistence.ENABLED else None
    database_ok = bool(persistence.ENABLED and (schema or 0) >= 41)
    checks.append(
        {
            "key": "postgres_v41",
            "ok": database_ok,
            "detail": f"schema={schema or 0}",
        }
    )
    if not database_ok:
        raise ProductionAuthorityPreflightError("PostgreSQL V41 authority hazır değil.")

    try:
        storage = S3KmsEnvelopeEvidenceStore.from_environment()
        storage_result = storage.preflight()
        checks.append({"key": "aws_evidence_storage", "ok": True, "detail": storage_result})
    except EvidenceStorageError as error:
        checks.append({"key": "aws_evidence_storage", "ok": False, "detail": str(error)})
        raise ProductionAuthorityPreflightError(str(error)) from error

    try:
        scanner = AwsKmsHmacKeyAuthority.from_environment()
        scanner_result = scanner.preflight()
        checks.append({"key": "aws_scanner_hmac", "ok": True, "detail": scanner_result})
    except ScannerKeyAuthorityError as error:
        checks.append({"key": "aws_scanner_hmac", "ok": False, "detail": str(error)})
        raise ProductionAuthorityPreflightError(str(error)) from error

    try:
        adapter = AuthorizedOfficialM2MAdapter.from_environment()
        for certificate_path in (adapter.config.mtls_cert, adapter.config.mtls_key):
            path = Path(certificate_path)
            if not path.is_file():
                raise OfficialM2MError("Yetkili M2M mTLS certificate/key dosyası bulunamadı.")
        # The canonical mapper invocation validates the explicitly reviewed
        # response profile without accepting any provider result.
        canonical_response_mapper({})
        token = adapter._access_token()
        token_fingerprint = sha256(token.encode("utf-8")).hexdigest()[:16]
        checks.append(
            {
                "key": "official_m2m_transport",
                "ok": True,
                "detail": {
                    "contract_id": adapter.config.contract_id,
                    "oauth_token_acquired": True,
                    "token_fingerprint": token_fingerprint,
                    "document_submitted": False,
                },
            }
        )
    except (OfficialM2MError, OSError, RuntimeError, ValueError) as error:
        checks.append({"key": "official_m2m_transport", "ok": False, "detail": str(error)})
        raise ProductionAuthorityPreflightError(str(error)) from error

    return {
        "ready": all(check["ok"] for check in checks),
        "checks": checks,
        "truth_boundary": "LIVE_INFRASTRUCTURE_AUTHORITY_PROOF_NO_DOCUMENT_VERIFICATION",
    }
