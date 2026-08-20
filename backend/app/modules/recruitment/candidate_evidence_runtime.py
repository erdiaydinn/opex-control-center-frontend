"""Runtime access boundary for candidate evidence.

Production candidate evidence is never resolved to a plaintext filesystem path.
Authorized reads decrypt the immutable S3/KMS envelope in memory after malware
clearance and exact metadata checks. Direct HR uploads reuse the same one-time
PostgreSQL capability authority instead of writing a local file.
"""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path

from app.modules.workforce import persistence
from . import candidate_upload_authority
from .candidate_evidence_storage import EvidenceStorageError, S3KmsEnvelopeEvidenceStore


class CandidateEvidenceRuntimeError(ValueError):
    pass


def _production() -> bool:
    return os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"


def _records() -> list[dict]:
    # Lazy import avoids turning the service/authority imports into a cycle.
    from .service import list_requests

    return list_requests()


def locate_candidate_evidence(
    request_id: str,
    candidate_id: str,
    digest: str,
) -> tuple[dict, dict, dict]:
    normalized_digest = str(digest or "").strip().lower()
    if len(normalized_digest) != 64 or any(ch not in "0123456789abcdef" for ch in normalized_digest):
        raise CandidateEvidenceRuntimeError("Aday kanıt özeti geçersiz.")
    record = next((row for row in _records() if row.get("id") == request_id), None)
    candidate = next(
        (item for item in (record or {}).get("candidates", []) if item.get("id") == candidate_id),
        None,
    )
    evidence = next(
        (
            item
            for item in (candidate or {}).get("evidence", [])
            if str(item.get("sha256", "")).lower() == normalized_digest
        ),
        None,
    )
    if record is None or candidate is None or evidence is None:
        raise CandidateEvidenceRuntimeError("Aday kanıtı bulunamadı.")
    return record, candidate, evidence


def _encrypted_store_for(evidence: dict) -> S3KmsEnvelopeEvidenceStore:
    if not persistence.ENABLED or (persistence.schema_version() or 0) < 40:
        raise CandidateEvidenceRuntimeError(
            "Şifreli aday kanıt otoritesi V40 olmadan kullanılamaz."
        )
    try:
        store = S3KmsEnvelopeEvidenceStore.from_environment()
    except EvidenceStorageError as error:
        raise CandidateEvidenceRuntimeError(str(error)) from error
    if evidence.get("storage_bucket") != store.bucket:
        raise CandidateEvidenceRuntimeError("Aday kanıt storage bucket otoritesi eşleşmiyor.")
    if evidence.get("kms_key_id") != store.kms_key_id:
        raise CandidateEvidenceRuntimeError("Aday kanıt KMS anahtar otoritesi eşleşmiyor.")
    if evidence.get("encryption_scheme") != "AES-256-GCM+AWS-KMS-DATA-KEY":
        raise CandidateEvidenceRuntimeError("Aday kanıt şifreleme sözleşmesi geçersiz.")
    if int(evidence.get("envelope_version") or 0) != 1:
        raise CandidateEvidenceRuntimeError("Aday kanıt zarf sürümü desteklenmiyor.")
    return store


def read_candidate_evidence(
    request_id: str,
    candidate_id: str,
    digest: str,
) -> tuple[bytes, dict]:
    _, _, evidence = locate_candidate_evidence(request_id, candidate_id, digest)
    if evidence.get("content_safety_state") != "MALWARE_CLEARED":
        raise CandidateEvidenceRuntimeError(
            "Aday kanıtı içerik güvenliği karantinasından çıkmadı."
        )

    backend = str(evidence.get("storage_backend") or "LEGACY_LOCAL").strip().upper()
    if backend == "S3_KMS_ENVELOPE":
        store = _encrypted_store_for(evidence)
        try:
            plaintext = store.get(
                tenant_id=persistence.tenant_id(),
                object_key=str(evidence.get("stored_name") or evidence.get("object_key") or ""),
                expected_sha256=str(evidence["sha256"]),
            )
        except EvidenceStorageError as error:
            raise CandidateEvidenceRuntimeError(str(error)) from error
        if sha256(plaintext).hexdigest() != evidence["sha256"]:
            raise CandidateEvidenceRuntimeError("Aday kanıt exact-byte bütünlüğü bozuldu.")
        return plaintext, evidence

    if backend != "LEGACY_LOCAL":
        raise CandidateEvidenceRuntimeError("Aday kanıt storage backend desteklenmiyor.")
    if _production():
        raise CandidateEvidenceRuntimeError(
            "Production aday kanıtı plaintext yerel depodan okunamaz."
        )

    from .service import _EVIDENCE_DIR

    stored = Path(str(evidence.get("stored_name") or ""))
    if stored.is_absolute() or ".." in stored.parts:
        raise CandidateEvidenceRuntimeError("Aday kanıt arşiv anahtarı geçersiz.")
    path = _EVIDENCE_DIR / stored
    if not path.is_file():
        raise CandidateEvidenceRuntimeError("Aday kanıt dosyası arşivde bulunamadı.")
    plaintext = path.read_bytes()
    if sha256(plaintext).hexdigest() != evidence["sha256"]:
        raise CandidateEvidenceRuntimeError("Aday kanıt exact-byte bütünlüğü bozuldu.")
    return plaintext, evidence


def secure_hr_candidate_upload(
    request_id: str,
    candidate_id: str,
    *,
    filename: str,
    content_type: str,
    content: bytes,
    document_type: str,
    actor: str,
) -> dict:
    """Use the same one-time authority for authenticated HR uploads in production."""
    if not persistence.ENABLED or (persistence.schema_version() or 0) < 40:
        raise CandidateEvidenceRuntimeError(
            "Şifreli aday kanıt otoritesi V40 migration olmadan kullanılamaz."
        )
    try:
        issued = candidate_upload_authority.issue(
            request_id,
            candidate_id,
            document_type,
            5,
            actor,
        )
        candidate_upload_authority.finalize(
            issued["capability"],
            document_type,
            filename,
            content_type,
            content,
            Path("/non-production-placeholder"),
            retention_days=max(
                1,
                int(os.getenv("RECRUITMENT_EVIDENCE_RETENTION_DAYS", "365")),
            ),
        )
    except (candidate_upload_authority.CandidateUploadAuthorityError, ValueError) as error:
        raise CandidateEvidenceRuntimeError(str(error)) from error

    record = next((row for row in _records() if row.get("id") == request_id), None)
    candidate = next(
        (item for item in (record or {}).get("candidates", []) if item.get("id") == candidate_id),
        None,
    )
    if candidate is None:
        raise CandidateEvidenceRuntimeError("Aday kanıt finalize sonrası bulunamadı.")
    return candidate


def purge_expired_encrypted_candidate_evidence(
    *,
    now: datetime | None = None,
) -> dict:
    """Delete expired encrypted objects before aggregate metadata is purged.

    The subsequent DB metadata purge is intentionally separate. If it fails,
    retrying this phase after retention is idempotent for an already-missing
    exact object, allowing metadata cleanup without leaking an orphan object.
    """
    cutoff = (now or datetime.now(UTC)).astimezone(UTC)
    deleted = 0
    for record in _records():
        for candidate in record.get("candidates", []):
            for evidence in candidate.get("evidence", []):
                if str(evidence.get("storage_backend") or "").upper() != "S3_KMS_ENVELOPE":
                    continue
                retention_value = evidence.get("retention_until")
                if not retention_value:
                    raise CandidateEvidenceRuntimeError(
                        "Şifreli aday kanıtında retention_until eksik."
                    )
                try:
                    retention_until = datetime.fromisoformat(str(retention_value)).astimezone(UTC)
                except ValueError as error:
                    raise CandidateEvidenceRuntimeError(
                        "Şifreli aday kanıt retention tarihi geçersiz."
                    ) from error
                if retention_until > cutoff:
                    continue
                store = _encrypted_store_for(evidence)
                try:
                    store.delete_after_retention(
                        tenant_id=persistence.tenant_id(),
                        object_key=str(evidence.get("stored_name") or evidence.get("object_key") or ""),
                        expected_sha256=str(evidence["sha256"]),
                        retention_until=retention_until,
                        now=cutoff,
                    )
                except EvidenceStorageError as error:
                    raise CandidateEvidenceRuntimeError(str(error)) from error
                deleted += 1
    return {"encrypted_objects_deleted": deleted, "cutoff": cutoff.isoformat()}
