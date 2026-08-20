"""Hiring state-machine bridge for authorized official-document M2M verification."""
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from app.modules.workforce import persistence
from .candidate_evidence_runtime import (
    CandidateEvidenceRuntimeError,
    locate_candidate_evidence,
)
from .evidence_release_authority import (
    EvidenceReleaseAuthorityError,
    require_candidate_evidence_released,
)
from .official_document_m2m import AuthorizedOfficialM2MAdapter, OfficialM2MError


class OfficialM2MVerificationRequest(BaseModel):
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_type: str = Field(
        pattern=(
            r"^(CRIMINAL_RECORD|RESIDENCE|SGK_SERVICE|MILITARY_STATUS|"
            r"EDUCATION|CIVIL_REGISTRY)$"
        )
    )
    barcode: str = Field(min_length=1, max_length=512)
    subject_reference: str = Field(min_length=1, max_length=512)
    note: str = Field(min_length=1, max_length=2000)


class OfficialM2MRuntimeError(ValueError):
    pass


def verify_authorized_candidate_document(
    request_id: str,
    candidate_id: str,
    payload: OfficialM2MVerificationRequest,
    *,
    actor: str,
    correlation_id: str,
    adapter: AuthorizedOfficialM2MAdapter | None = None,
) -> dict[str, Any]:
    """Call an authorized provider and seal its result into the Hiring aggregate.

    ``subject_reference`` and the raw barcode are transport-only inputs and are
    deliberately not copied into the Hiring aggregate or audit record. In
    production the exact evidence must first be released by the V42 append-only
    scanner authority; aggregate JSON alone can never authorize an external call.
    """
    try:
        _, _, evidence = locate_candidate_evidence(
            request_id,
            candidate_id,
            payload.evidence_sha256,
        )
    except CandidateEvidenceRuntimeError as error:
        raise OfficialM2MRuntimeError(str(error)) from error

    production = os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"
    if production:
        if not persistence.ENABLED or (persistence.schema_version() or 0) < persistence.SCHEMA_VERSION:
            raise OfficialM2MRuntimeError(
                "Production resmî M2M doğrulaması current PostgreSQL security schema olmadan kullanılamaz."
            )
        if str(evidence.get("storage_backend") or "").upper() != "S3_KMS_ENVELOPE":
            raise OfficialM2MRuntimeError(
                "Production resmî M2M doğrulaması plaintext/legacy evidence üzerinde çalışamaz."
            )
        if evidence.get("encryption_scheme") != "AES-256-GCM+AWS-KMS-DATA-KEY":
            raise OfficialM2MRuntimeError(
                "Production resmî M2M evidence encryption contract geçersiz."
            )

    if evidence.get("document_type") != payload.document_type:
        raise OfficialM2MRuntimeError(
            "Yetkili M2M belge türü yüklenen evidence ile eşleşmiyor."
        )
    if not evidence.get("requires_official_verification"):
        raise OfficialM2MRuntimeError("Bu belge türü resmî M2M doğrulamasına uygun değil.")
    if evidence.get("official_verification") is not None:
        raise OfficialM2MRuntimeError(
            "Belge için resmî doğrulama zaten kaydedilmiş; replay reddedildi."
        )
    if evidence.get("content_safety_state") != "MALWARE_CLEARED":
        raise OfficialM2MRuntimeError(
            "İçerik güvenliği temizlenmeden dış resmî doğrulama çağrısı yapılamaz."
        )

    if production:
        try:
            require_candidate_evidence_released(request_id, candidate_id, evidence)
        except EvidenceReleaseAuthorityError as error:
            raise OfficialM2MRuntimeError(
                "Exact evidence append-only scanner authority tarafından serbest bırakılmadı."
            ) from error

    try:
        authority = adapter or AuthorizedOfficialM2MAdapter.from_environment()
        result = authority.verify_document(
            evidence_sha256=payload.evidence_sha256,
            document_type=payload.document_type,
            barcode=payload.barcode,
            subject_reference=payload.subject_reference,
            correlation_id=correlation_id,
        )
    except (OfficialM2MError, ValueError, OSError, RuntimeError) as error:
        raise OfficialM2MRuntimeError(str(error)) from error

    if not result.get("provider_signature_verified"):
        raise OfficialM2MRuntimeError("Yetkili M2M provider imza kanıtı eksik.")
    if result.get("verification_method") != "AUTHORIZED_OFFICIAL_API":
        raise OfficialM2MRuntimeError("Yetkili M2M verification method otoritesi geçersiz.")
    if result.get("truth_boundary") != "AUTHORIZED_MACHINE_TO_MACHINE":
        raise OfficialM2MRuntimeError("Yetkili M2M truth boundary geçersiz.")

    from .service import RecruitmentRuleError, record_candidate_document_verification

    service_payload = {
        "evidence_sha256": payload.evidence_sha256,
        "result": result["result"],
        "subject_match": result["subject_match"],
        "document_type": payload.document_type,
        "official_receipt_id": result["official_receipt_id"],
        "official_response_sha256": result["official_response_sha256"],
        "issued_at": result.get("issued_at"),
        "note": payload.note,
    }
    try:
        return record_candidate_document_verification(
            request_id,
            candidate_id,
            service_payload,
            actor,
            verification_method="AUTHORIZED_OFFICIAL_API",
            provider_signature_verified=True,
        )
    except RecruitmentRuleError as error:
        raise OfficialM2MRuntimeError(str(error)) from error
