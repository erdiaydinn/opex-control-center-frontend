"""Fail-closed release checks backed by append-only scanner authorities.

Production aggregate JSON is descriptive state only. A document can be read or
approved only when the exact immutable evidence binding has a latest CLEAN
cryptographic scanner receipt in PostgreSQL authority tables.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.workforce import persistence


class EvidenceReleaseAuthorityError(ValueError):
    pass


def _binding(evidence: dict) -> tuple[UUID, str]:
    if str(evidence.get("storage_backend") or "").upper() != "S3_KMS_ENVELOPE":
        raise EvidenceReleaseAuthorityError("Production evidence encrypted authority ile eşleşmiyor.")
    try:
        evidence_id = UUID(str(evidence.get("id") or ""))
    except (TypeError, ValueError) as error:
        raise EvidenceReleaseAuthorityError("Production evidence scanner identity geçersiz.") from error
    digest = str(evidence.get("sha256") or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise EvidenceReleaseAuthorityError("Production evidence SHA-256 binding geçersiz.")
    if evidence.get("content_safety_state") != "MALWARE_CLEARED":
        raise EvidenceReleaseAuthorityError("Evidence malware karantinasından çıkmadı.")
    if evidence.get("content_safety_truth_boundary") != "CRYPTOGRAPHIC_SCANNER_RECEIPT":
        raise EvidenceReleaseAuthorityError("Evidence cryptographic scanner truth boundary taşımıyor.")
    receipt = evidence.get("content_safety_receipt") or {}
    if (
        receipt.get("signature_verified") is not True
        or receipt.get("result") != "CLEAN"
        or str(receipt.get("evidence_sha256") or "").lower() != digest
    ):
        raise EvidenceReleaseAuthorityError("Evidence scanner receipt aggregate binding geçersiz.")
    return evidence_id, digest


def _require_v42() -> None:
    if not persistence.ENABLED or (persistence.schema_version() or 0) < 42:
        raise EvidenceReleaseAuthorityError("PostgreSQL evidence release authority V42 hazır değil.")


def require_candidate_evidence_released(
    request_id: str,
    candidate_id: str,
    evidence: dict,
) -> None:
    _require_v42()
    evidence_id, digest = _binding(evidence)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT recruitment.candidate_evidence_release_authorized(%s,%s,%s,%s,%s)",
            (
                persistence.tenant_id(),
                request_id,
                candidate_id,
                evidence_id,
                bytes.fromhex(digest),
            ),
        )
        released = bool(cursor.fetchone()[0])
        database.rollback()
    if not released:
        raise EvidenceReleaseAuthorityError(
            "Aday kanıtı append-only scanner authority tarafından CLEAN olarak serbest bırakılmadı."
        )


def require_request_evidence_released(request_id: str, evidence: dict) -> None:
    _require_v42()
    evidence_id, digest = _binding(evidence)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT recruitment.request_evidence_release_authorized(%s,%s,%s,%s)",
            (
                persistence.tenant_id(),
                request_id,
                evidence_id,
                bytes.fromhex(digest),
            ),
        )
        released = bool(cursor.fetchone()[0])
        database.rollback()
    if not released:
        raise EvidenceReleaseAuthorityError(
            "İstifa/ayrılış kanıtı append-only scanner authority tarafından CLEAN olarak serbest bırakılmadı."
        )
