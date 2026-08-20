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
    locate_candidate_evidence,
    purge_expired_encrypted_candidate_evidence,
    read_candidate_evidence,
)
from .candidate_scan_authority import CandidateScanAuthorityError, record_verified_scan
from .evidence_release_authority import (
    EvidenceReleaseAuthorityError,
    require_candidate_evidence_released,
    require_request_evidence_released,
)
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
from .schemas import (
    RecruitmentCandidateDecision,
    RecruitmentCandidateDocumentAttestation,
    RecruitmentCandidateDocumentVerification,
    RecruitmentDecision,
)
from .service import (
    RecruitmentRuleError,
    add_evidence,
    attest_candidate_document_verification,
    decide_candidate,
    decide_request,
    purge_expired_recruitment_data,
    record_candidate_document_verification,
)


router = APIRouter(prefix="/recruitment", tags=["Recruitment"])
_OFFICIAL_DOCUMENT_PORTAL = "https://www.turkiye.gov.tr/belge-dogrulama"


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
    if not (_encrypted_mode() and record.get("evidence_required")):
        return
    evidence = record.get("evidence") or {}
    require_request_evidence_released(str(record.get("id") or ""), evidence)


def _require_candidate_evidence_clean(
    request_id: str,
    candidate_id: str,
    candidate: dict,
) -> None:
    if not _encrypted_mode():
        return
    evidence_rows = list(candidate.get("evidence") or [])
    if not evidence_rows:
        raise EvidenceReleaseAuthorityError("Aday evidence authority bulunamadı.")
    for evidence in evidence_rows:
        require_candidate_evidence_released(request_id, candidate_id, evidence)


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


@router.post("/requests/{request_id}/evidence/quarantine/retry", include_in_schema=False)
def retry_request_evidence_quarantine(
    request_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Idempotently recover a committed encrypted object whose quarantine seal was interrupted."""
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentSettings")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return seal_request_evidence_quarantine(request_id, actor=actor)
    except RequestEvidenceQuarantineError as error:
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
    except (
        RecruitmentEvidenceRuntimeError,
        RecruitmentRuleError,
        EvidenceReleaseAuthorityError,
    ) as error:
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
    except (RecruitmentRuleError, EvidenceReleaseAuthorityError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/decision")
def secure_candidate_decision(
    request_id: str,
    candidate_id: str,
    payload: RecruitmentCandidateDecision,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    record = _request_row(request_id)
    _require_rows_in_scope(request, x_opex_role, [record])
    actor, _ = _identity(request)
    candidate = next(
        (row for row in record.get("candidates", []) if row.get("id") == candidate_id),
        None,
    )
    try:
        if candidate is None:
            raise RecruitmentRuleError("Aday bulunamadı.")
        if payload.decision == "APPROVED":
            _require_candidate_evidence_clean(request_id, candidate_id, candidate)
        return decide_candidate(request_id, candidate_id, payload.decision, payload.note, actor)
    except (RecruitmentRuleError, EvidenceReleaseAuthorityError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/candidates/{candidate_id}/evidence/{digest}")
def secure_candidate_evidence_download(
    request_id: str,
    candidate_id: str,
    digest: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
):
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    record = _request_row(request_id)
    _require_rows_in_scope(request, x_opex_role, [record])
    try:
        _, candidate, evidence = locate_candidate_evidence(request_id, candidate_id, digest)
        if _encrypted_mode():
            require_candidate_evidence_released(request_id, candidate_id, evidence)
        content, metadata = read_candidate_evidence(request_id, candidate_id, digest)
        actor, _ = _identity(request)
        persistence.append_audit(
            "RECRUITMENT_CANDIDATE_EVIDENCE_ACCESSED",
            actor,
            record_id=request_id,
            candidate_id=candidate.get("id"),
            evidence_sha256=metadata.get("sha256"),
            storage_backend=metadata.get("storage_backend", "LEGACY_LOCAL"),
        )
        filename = quote(str(metadata.get("original_name") or "candidate-evidence")[:240])
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
    except (CandidateEvidenceRuntimeError, EvidenceReleaseAuthorityError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/requests/{request_id}/candidates/{candidate_id}/document-verifications/assist")
def official_document_human_assist(
    request_id: str,
    candidate_id: str,
    evidence_sha256: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Return a credential-free launch contract for the official human portal.

    EAY never receives an e-Devlet password, OTP, browser cookie, session token,
    CAPTCHA answer, or authenticated browser state. The resulting human witness
    record still requires the existing exact-SHA verification route and a second
    authorized attestation before candidate approval.
    """
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    record = _request_row(request_id)
    _require_rows_in_scope(request, x_opex_role, [record])
    try:
        _, _, evidence = locate_candidate_evidence(
            request_id, candidate_id, evidence_sha256
        )
        if not evidence.get("requires_official_verification"):
            raise RecruitmentRuleError("Bu belge için resmî doğrulama gerekmiyor.")
        if _encrypted_mode():
            require_candidate_evidence_released(
                request_id, candidate_id, evidence
            )
        actor, _ = _identity(request)
        persistence.append_audit(
            "RECRUITMENT_OFFICIAL_DOCUMENT_HUMAN_ASSIST_LAUNCHED",
            actor,
            record_id=request_id,
            candidate_id=candidate_id,
            evidence_sha256=evidence.get("sha256"),
            document_type=evidence.get("document_type"),
            credential_capture=False,
            browser_automation=False,
        )
        return {
            "mode": "HR_ASSISTED_OFFICIAL_PORTAL",
            "launch_url": _OFFICIAL_DOCUMENT_PORTAL,
            "document_type": evidence.get("document_type"),
            "evidence_sha256": evidence.get("sha256"),
            "credential_capture": False,
            "browser_automation": False,
            "captcha_automation": False,
            "session_import": False,
            "truth_boundary": "HUMAN_WITNESSED_OFFICIAL_PORTAL_PENDING_ATTESTATION",
            "record_result_via": (
                f"/api/recruitment/requests/{request_id}/candidates/"
                f"{candidate_id}/document-verifications"
            ),
            "attest_via": (
                f"/api/recruitment/requests/{request_id}/candidates/"
                f"{candidate_id}/document-verifications/attest"
            ),
        }
    except (
        CandidateEvidenceRuntimeError,
        EvidenceReleaseAuthorityError,
        RecruitmentRuleError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/document-verifications")
def secure_human_document_verification(
    request_id: str,
    candidate_id: str,
    payload: RecruitmentCandidateDocumentVerification,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Record a human-witnessed result only after the exact file was scanner-released."""
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    record = _request_row(request_id)
    _require_rows_in_scope(request, x_opex_role, [record])
    actor, _ = _identity(request)
    try:
        _, _, evidence = locate_candidate_evidence(
            request_id, candidate_id, payload.evidence_sha256
        )
        if _encrypted_mode():
            require_candidate_evidence_released(request_id, candidate_id, evidence)
        return record_candidate_document_verification(
            request_id,
            candidate_id,
            payload.model_dump(mode="json"),
            actor,
            verification_method="HR_ASSISTED_OFFICIAL_PORTAL",
        )
    except (
        CandidateEvidenceRuntimeError,
        EvidenceReleaseAuthorityError,
        RecruitmentRuleError,
    ) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/document-verifications/attest")
def secure_human_document_attestation(
    request_id: str,
    candidate_id: str,
    payload: RecruitmentCandidateDocumentAttestation,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Apply four-eyes attestation only while scanner release remains CLEAN."""
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    record = _request_row(request_id)
    _require_rows_in_scope(request, x_opex_role, [record])
    actor, _ = _identity(request)
    try:
        _, _, evidence = locate_candidate_evidence(
            request_id, candidate_id, payload.evidence_sha256
        )
        if _encrypted_mode():
            require_candidate_evidence_released(request_id, candidate_id, evidence)
        return attest_candidate_document_verification(
            request_id,
            candidate_id,
            payload.evidence_sha256,
            payload.note,
            actor,
        )
    except (
        CandidateEvidenceRuntimeError,
        EvidenceReleaseAuthorityError,
        RecruitmentRuleError,
    ) as error:
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
