"""Priority Hiring security routes.

Mounted before the legacy recruitment router so production evidence upload,
read, decision, scanner callbacks, retention, and live-authority preflight share
one fail-closed security boundary.
"""
from __future__ import annotations

import os
from urllib.parse import quote

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.modules.workforce import persistence
from app.modules.workforce.router import _require_rows_in_scope
from .candidate_evidence_runtime import (
    CandidateEvidenceRuntimeError,
    purge_expired_encrypted_candidate_evidence,
)
from .candidate_scan_authority import CandidateScanAuthorityError, record_verified_scan
from .production_authority_preflight import (
    ProductionAuthorityPreflightError,
    run_live_preflight,
)
from .recruitment_evidence_runtime import (
    RecruitmentEvidenceRuntimeError,
    purge_expired_encrypted_request_evidence,
    read_request_evidence,
    secure_request_evidence_upload,
)
from .request_evidence_quarantine import (
    RequestEvidenceQuarantineError,
    seal_request_evidence_quarantine,
)
from .request_evidence_scan_authority import (
    RequestEvidenceScanAuthorityError,
    record_verified_request_scan,
)
from .router import _identity, _read_upload_limited, _request_row, _require
from .schemas import RecruitmentDecision
from .service import (
    RecruitmentRuleError,
    add_evidence,
    decide_request,
    purge_expired_recruitment_data,
)


router = APIRouter(prefix="/recruitment", tags=["Recruitment"])


class ScannerReceiptEnvelope(BaseModel):
    payload: dict[str, str]
    signature: str = Field(min_length=1, max_length=256)


def _encrypted_mode() -> bool:
    return (
        os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"
        or os.getenv("RECRUITMENT_EVIDENCE_STORAGE_MODE", "disabled").strip().lower()
        == "s3-kms-envelope"
    )


def _require_request_evidence_clean(record: dict) -> None:
    evidence = record.get("evidence") or {}
    if (
        _encrypted_mode()
        and record.get("evidence_required")
        and evidence.get("storage_backend") == "S3_KMS_ENVELOPE"
        and evidence.get("content_safety_state") != "MALWARE_CLEARED"
    ):
        raise RecruitmentRuleError(
            "Planlı ayrılış kanıtı kriptografik scanner receipt ile temizlenmeden görüntülenemez/onaylanamaz."
        )


@router.post("/requests/{request_id}/evidence")
async def upload_request_evidence(
    request_id: str,
    request: Request,
    file: UploadFile = File(...),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        content = await _read_upload_limited(file)
        content_type = file.content_type or "application/octet-stream"
        if _encrypted_mode():
            secure_request_evidence_upload(
                request_id,
                filename=file.filename or "document",
                content_type=content_type,
                content=content,
                actor=actor,
            )
            return seal_request_evidence_quarantine(request_id, actor=actor)
        return add_evidence(
            request_id,
            file.filename or "document",
            content_type,
            content,
            actor,
        )
    except (
        RecruitmentRuleError,
        RecruitmentEvidenceRuntimeError,
        RequestEvidenceQuarantineError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/evidence")
def download_request_evidence(
    request_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
):
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    record = _request_row(request_id)
    _require_rows_in_scope(request, x_opex_role, [record])
    try:
        _require_request_evidence_clean(record)
        content, metadata = read_request_evidence(request_id)
        actor, _ = _identity(request)
        persistence.append_audit(
            "RECRUITMENT_EVIDENCE_ACCESSED",
            actor,
            record_id=request_id,
            evidence_sha256=metadata.get("sha256"),
            storage_backend=metadata.get("storage_backend", "LEGACY_LOCAL"),
        )
        filename = quote(str(metadata.get("original_name") or "recruitment-evidence")[:240])
        return Response(
            content=content,
            media_type=metadata["content_type"],
            headers={
                "Cache-Control": "no-store, private",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            },
        )
    except (RecruitmentEvidenceRuntimeError, RecruitmentRuleError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/requests/{request_id}/decision")
def secure_request_decision(
    request_id: str,
    payload: RecruitmentDecision,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    record = _request_row(request_id)
    _require_rows_in_scope(request, x_opex_role, [record])
    actor, actor_name = _identity(request)
    try:
        if payload.decision == "APPROVED":
            _require_request_evidence_clean(record)
        return decide_request(request_id, payload.decision, payload.note, actor, actor_name)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/candidate-evidence/scanner-receipts", include_in_schema=False)
def candidate_scanner_receipt(envelope: ScannerReceiptEnvelope) -> dict:
    """Cryptographic service callback; KMS signature is the result authority."""
    try:
        evidence = record_verified_scan(
            envelope.payload,
            envelope.signature,
            actor="recruitment-scanner",
        )
        return {
            "accepted": True,
            "evidence_id": evidence.get("id"),
            "content_safety_state": evidence.get("content_safety_state"),
        }
    except CandidateScanAuthorityError as error:
        raise HTTPException(status_code=409, detail="Scanner receipt reddedildi.") from error


@router.post("/requests/{request_id}/evidence/scanner-receipts", include_in_schema=False)
def request_scanner_receipt(
    request_id: str,
    envelope: ScannerReceiptEnvelope,
) -> dict:
    """Signed scanner callback for encrypted planned-departure evidence."""
    try:
        evidence = record_verified_request_scan(
            request_id,
            envelope.payload,
            envelope.signature,
        )
        return {
            "accepted": True,
            "evidence_id": evidence.get("id"),
            "content_safety_state": evidence.get("content_safety_state"),
        }
    except RequestEvidenceScanAuthorityError as error:
        raise HTTPException(status_code=409, detail="Scanner receipt reddedildi.") from error


@router.post("/production-authorities/preflight")
def production_authority_preflight(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Perform live infrastructure authority checks without submitting a document."""
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentSettings")
    actor, _ = _identity(request)
    try:
        result = run_live_preflight()
    except ProductionAuthorityPreflightError as error:
        persistence.append_audit(
            "RECRUITMENT_PRODUCTION_AUTHORITY_PREFLIGHT_FAILED",
            actor,
            reason=str(error),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PRODUCTION_AUTHORITY_PREFLIGHT_FAILED", "message": str(error)},
        ) from error
    persistence.append_audit(
        "RECRUITMENT_PRODUCTION_AUTHORITY_PREFLIGHT_PASSED",
        actor,
        truth_boundary=result["truth_boundary"],
    )
    return result


@router.post("/retention/purge")
def purge_recruitment_retention(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentSettings")
    actor, _ = _identity(request)
    try:
        candidate_storage = purge_expired_encrypted_candidate_evidence()
        request_storage = purge_expired_encrypted_request_evidence()
    except (CandidateEvidenceRuntimeError, RecruitmentEvidenceRuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ENCRYPTED_EVIDENCE_RETENTION_FAILED",
                "message": str(error),
            },
        ) from error
    metadata = purge_expired_recruitment_data(actor)
    return {**metadata, **candidate_storage, **request_storage}
