"""Live, non-document production preflight for Hiring security authorities.

The preflight may contact AWS KMS/S3 and, only after an institutional agreement
is configured, the authorized official OAuth token endpoint. It never submits a
citizen document or claims an official verification.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path

from app.modules.workforce import persistence
from .candidate_evidence_storage import EvidenceStorageError, S3KmsEnvelopeEvidenceStore
from .official_document_m2m import AuthorizedOfficialM2MAdapter, OfficialM2MError, canonical_response_mapper
from .scanner_database_authority import ScannerDatabaseAuthorityError, live_preflight as scanner_db_preflight
from .scanner_key_authority import AwsKmsHmacKeyAuthority, ScannerKeyAuthorityError


class ProductionAuthorityPreflightError(RuntimeError):
    pass


_M2M_ENV = (
    "RECRUITMENT_OFFICIAL_M2M_ENDPOINT", "RECRUITMENT_OFFICIAL_M2M_TOKEN_URL",
    "RECRUITMENT_OFFICIAL_M2M_CLIENT_ID", "RECRUITMENT_OFFICIAL_M2M_CLIENT_SECRET",
    "RECRUITMENT_OFFICIAL_M2M_MTLS_CERT", "RECRUITMENT_OFFICIAL_M2M_MTLS_KEY",
    "RECRUITMENT_OFFICIAL_M2M_ALLOWED_HOSTS", "RECRUITMENT_OFFICIAL_M2M_CONTRACT_ID",
    "RECRUITMENT_OFFICIAL_M2M_SIGNATURE_PROFILE", "RECRUITMENT_OFFICIAL_M2M_PROVIDER_PUBLIC_KEY_FILE",
    "RECRUITMENT_OFFICIAL_M2M_RESPONSE_PROFILE",
)


def _official_m2m_state() -> str:
    present = [bool(os.getenv(name, "").strip()) for name in _M2M_ENV]
    if not any(present):
        return "EXTERNAL_AGREEMENT_PENDING"
    if not all(present):
        return "PARTIAL_CONFIGURATION_REJECTED"
    return "CONFIGURED"


def run_live_preflight() -> dict:
    checks: list[dict] = []
    schema = persistence.schema_version() if persistence.ENABLED else None
    database_ok = bool(persistence.ENABLED and (schema or 0) >= 47)
    checks.append({"key": "postgres_v47", "required": True, "ok": database_ok, "detail": f"schema={schema or 0}"})
    if not database_ok:
        raise ProductionAuthorityPreflightError("PostgreSQL V47 authority hazır değil.")

    try:
        storage = S3KmsEnvelopeEvidenceStore.from_environment()
        checks.append({"key": "aws_evidence_storage", "required": True, "ok": True, "detail": storage.preflight()})
    except EvidenceStorageError as error:
        raise ProductionAuthorityPreflightError(str(error)) from error
    try:
        scanner = AwsKmsHmacKeyAuthority.from_environment()
        checks.append({"key": "aws_scanner_hmac", "required": True, "ok": True, "detail": scanner.preflight()})
    except ScannerKeyAuthorityError as error:
        raise ProductionAuthorityPreflightError(str(error)) from error
    try:
        checks.append({"key": "scanner_postgres_role", "required": True, "ok": True, "detail": scanner_db_preflight()})
    except ScannerDatabaseAuthorityError as error:
        raise ProductionAuthorityPreflightError(str(error)) from error

    m2m_state = _official_m2m_state()
    if m2m_state == "EXTERNAL_AGREEMENT_PENDING":
        checks.append({"key": "official_m2m_transport", "required": False, "ok": None, "detail": {"state": m2m_state, "document_submitted": False, "blocking": False}})
    elif m2m_state == "PARTIAL_CONFIGURATION_REJECTED":
        raise ProductionAuthorityPreflightError("Yetkili e-Devlet M2M kısmi yapılandırması reddedildi; anlaşma sonrası tam credential seti gerekir.")
    else:
        try:
            adapter = AuthorizedOfficialM2MAdapter.from_environment()
            for certificate_path in (adapter.config.mtls_cert, adapter.config.mtls_key):
                if not Path(certificate_path).is_file():
                    raise OfficialM2MError("Yetkili M2M mTLS certificate/key dosyası bulunamadı.")
            canonical_response_mapper({})
            token = adapter._access_token()
            checks.append({"key": "official_m2m_transport", "required": False, "ok": True, "detail": {"state": "CONFIGURED_TRANSPORT_PROVEN", "contract_id": adapter.config.contract_id, "oauth_token_acquired": True, "token_fingerprint": sha256(token.encode()).hexdigest()[:16], "document_submitted": False, "blocking": False}})
        except (OfficialM2MError, OSError, RuntimeError, ValueError) as error:
            raise ProductionAuthorityPreflightError(str(error)) from error

    required_checks = [check for check in checks if check.get("required")]
    return {
        "ready": all(check["ok"] is True for check in required_checks),
        "checks": checks,
        "external_pending": [check["key"] for check in checks if check.get("required") is False and check.get("ok") is None],
        "truth_boundary": "LIVE_INFRASTRUCTURE_AUTHORITY_PROOF_NO_DOCUMENT_VERIFICATION",
    }
