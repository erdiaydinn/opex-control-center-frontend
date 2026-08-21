"""Production runtime authority for request-level recruitment evidence.

Planned-departure/resignation evidence follows the same encrypted object-storage
truth boundary as candidate evidence. Production never writes or serves these
bytes from the local filesystem.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

from app.modules.workforce import persistence
from .candidate_evidence_storage import EvidenceStorageError, S3KmsEnvelopeEvidenceStore


class RecruitmentEvidenceRuntimeError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _production() -> bool:
    return os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"


def _validate_content(content_type: str, content: bytes) -> None:
    if not content or len(content) > 10 * 1024 * 1024:
        raise RecruitmentEvidenceRuntimeError("Belge boş olamaz ve 10 MB sınırını aşamaz.")
    if content_type not in {"application/pdf", "image/jpeg", "image/png"}:
        raise RecruitmentEvidenceRuntimeError("Yalnızca PDF, JPG veya PNG istifa belgesi yüklenebilir.")
    from .service import RecruitmentRuleError, _validate_candidate_document_bytes

    try:
        _validate_candidate_document_bytes(content_type, content)
    except RecruitmentRuleError as error:
        raise RecruitmentEvidenceRuntimeError(str(error)) from error


def _store_for(metadata: dict | None = None) -> S3KmsEnvelopeEvidenceStore:
    if not persistence.ENABLED or (persistence.schema_version() or 0) < 40:
        raise RecruitmentEvidenceRuntimeError(
            "Şifreli işe alım kanıt otoritesi PostgreSQL V40 olmadan kullanılamaz."
        )
    try:
        store = S3KmsEnvelopeEvidenceStore.from_environment()
    except EvidenceStorageError as error:
        raise RecruitmentEvidenceRuntimeError(str(error)) from error
    if metadata is not None:
        if metadata.get("storage_bucket") != store.bucket:
            raise RecruitmentEvidenceRuntimeError("İşe alım kanıt storage bucket otoritesi eşleşmiyor.")
        if metadata.get("kms_key_id") != store.kms_key_id:
            raise RecruitmentEvidenceRuntimeError("İşe alım kanıt KMS anahtar otoritesi eşleşmiyor.")
        if metadata.get("encryption_scheme") != "AES-256-GCM+AWS-KMS-DATA-KEY":
            raise RecruitmentEvidenceRuntimeError("İşe alım kanıt şifreleme sözleşmesi geçersiz.")
        if int(metadata.get("envelope_version") or 0) != 1:
            raise RecruitmentEvidenceRuntimeError("İşe alım kanıt zarf sürümü desteklenmiyor.")
    return store


def _object_key(tenant_id: str, request_id: str) -> str:
    request_binding = sha256(request_id.encode("utf-8")).hexdigest()[:40]
    return f"quarantine/{tenant_id}/request-{request_binding}"


def secure_request_evidence_upload(
    request_id: str,
    *,
    filename: str,
    content_type: str,
    content: bytes,
    actor: str,
) -> dict:
    """Atomically bind one immutable encrypted evidence object to a request.

    The database request row is locked before the S3 write. A commit/network
    ambiguity can be retried because the object key is deterministically bound
    to the request and S3 conditional-create accepts only exact-byte recovery.
    """
    _validate_content(content_type, content)
    store = _store_for()
    digest = sha256(content).hexdigest()
    uploaded_at = _now()
    retention_days = max(1, int(os.getenv("RECRUITMENT_EVIDENCE_RETENTION_DAYS", "365")))
    retention_until = uploaded_at + timedelta(days=retention_days)

    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        tenant_id = persistence.tenant_id()
        cursor.execute(
            """SELECT payload,revision
               FROM recruitment_requests
               WHERE tenant_id=%s AND id=%s
               FOR UPDATE""",
            (tenant_id, request_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentEvidenceRuntimeError("Talep bulunamadı.")
        record, revision = row
        if not record.get("evidence_required"):
            raise RecruitmentEvidenceRuntimeError(
                "Bu işe alım talebi için ayrılış kanıtı beklenmiyor."
            )
        if record.get("evidence") is not None:
            raise RecruitmentEvidenceRuntimeError(
                "Production ayrılış kanıtı değiştirilemez; yeni talep/kanıt akışı oluşturulmalıdır."
            )
        if record.get("status") != "EVIDENCE_REQUIRED":
            raise RecruitmentEvidenceRuntimeError("Talep artık kanıt kabul eden aşamada değil.")

        object_key = _object_key(tenant_id, request_id)
        try:
            manifest = store.put(
                tenant_id=tenant_id,
                object_key=object_key,
                plaintext=content,
                expected_sha256=digest,
                retention_until=retention_until,
            )
        except EvidenceStorageError as error:
            database.rollback()
            raise RecruitmentEvidenceRuntimeError(str(error)) from error

        metadata = {
            "original_name": Path(filename).name[:240],
            "content_type": content_type,
            "size": len(content),
            "sha256": digest,
            "stored_name": object_key,
            "uploaded_at": uploaded_at.isoformat(),
            "uploaded_by": actor,
            "retention_until": retention_until.isoformat(),
            "content_safety_state": "STATIC_FORMAT_ACCEPTED_INTERNAL_HR",
            "content_safety_truth_boundary": "STATIC_FORMAT_GATE_ONLY_NOT_MALWARE_CLEARED",
            **manifest,
        }
        next_revision = int(revision) + 1
        record["evidence"] = metadata
        record["status"] = "PENDING_APPROVAL"
        record.setdefault("history", []).append(
            {
                "at": uploaded_at.isoformat(),
                "action": "EVIDENCE_UPLOADED_ENCRYPTED",
                "actor": actor,
                "sha256": digest,
                "storage_backend": "S3_KMS_ENVELOPE",
            }
        )
        record["revision"] = next_revision
        cursor.execute(
            """UPDATE recruitment_requests
               SET status=%s,revision=%s,payload=%s::jsonb
               WHERE tenant_id=%s AND id=%s AND revision=%s""",
            (
                record["status"],
                next_revision,
                json.dumps(record, ensure_ascii=False, default=str),
                tenant_id,
                request_id,
                revision,
            ),
        )
        if cursor.rowcount != 1:
            database.rollback()
            raise RecruitmentEvidenceRuntimeError(
                "İşe alım kaydı eşzamanlı olarak değiştirildi."
            )
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_EVIDENCE_UPLOADED_ENCRYPTED",
            actor,
            {
                "record_id": request_id,
                "sha256": digest,
                "content_type": content_type,
                "size": len(content),
                "storage_backend": "S3_KMS_ENVELOPE",
            },
        )
        database.commit()
        return record


def read_request_evidence(request_id: str) -> tuple[bytes, dict]:
    from .service import list_requests

    record = next((row for row in list_requests() if row.get("id") == request_id), None)
    metadata = (record or {}).get("evidence")
    if metadata is None:
        raise RecruitmentEvidenceRuntimeError("İstifa belgesi bulunamadı.")
    backend = str(metadata.get("storage_backend") or "LEGACY_LOCAL").strip().upper()
    if backend == "S3_KMS_ENVELOPE":
        store = _store_for(metadata)
        try:
            plaintext = store.get(
                tenant_id=persistence.tenant_id(),
                object_key=str(metadata.get("stored_name") or ""),
                expected_sha256=str(metadata.get("sha256") or ""),
            )
        except EvidenceStorageError as error:
            raise RecruitmentEvidenceRuntimeError(str(error)) from error
        if sha256(plaintext).hexdigest() != metadata.get("sha256"):
            raise RecruitmentEvidenceRuntimeError("İşe alım kanıt exact-byte bütünlüğü bozuldu.")
        return plaintext, metadata

    if backend != "LEGACY_LOCAL":
        raise RecruitmentEvidenceRuntimeError("İşe alım kanıt storage backend desteklenmiyor.")
    if _production():
        raise RecruitmentEvidenceRuntimeError(
            "Production işe alım kanıtı plaintext yerel depodan okunamaz."
        )
    from .service import evidence_path

    try:
        path, legacy_metadata = evidence_path(request_id)
    except Exception as error:
        raise RecruitmentEvidenceRuntimeError(str(error)) from error
    plaintext = path.read_bytes()
    if sha256(plaintext).hexdigest() != legacy_metadata.get("sha256"):
        raise RecruitmentEvidenceRuntimeError("İşe alım kanıt exact-byte bütünlüğü bozuldu.")
    return plaintext, legacy_metadata


def purge_expired_encrypted_request_evidence(*, now: datetime | None = None) -> dict:
    from .service import list_requests

    cutoff = (now or _now()).astimezone(UTC)
    deleted = 0
    for record in list_requests():
        metadata = record.get("evidence")
        if not metadata or str(metadata.get("storage_backend") or "").upper() != "S3_KMS_ENVELOPE":
            continue
        retention_value = metadata.get("retention_until")
        if not retention_value:
            raise RecruitmentEvidenceRuntimeError(
                "Şifreli işe alım kanıtında retention_until eksik."
            )
        try:
            retention_until = datetime.fromisoformat(str(retention_value)).astimezone(UTC)
        except ValueError as error:
            raise RecruitmentEvidenceRuntimeError(
                "Şifreli işe alım kanıt retention tarihi geçersiz."
            ) from error
        if retention_until > cutoff:
            continue
        store = _store_for(metadata)
        try:
            store.delete_after_retention(
                tenant_id=persistence.tenant_id(),
                object_key=str(metadata.get("stored_name") or ""),
                expected_sha256=str(metadata.get("sha256") or ""),
                retention_until=retention_until,
                now=cutoff,
            )
        except EvidenceStorageError as error:
            raise RecruitmentEvidenceRuntimeError(str(error)) from error
        deleted += 1
    return {"encrypted_request_objects_deleted": deleted}
