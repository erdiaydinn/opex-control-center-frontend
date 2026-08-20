"""Priority routes that close plaintext request-evidence paths.

This router is mounted before the legacy recruitment router. It preserves the
public API while ensuring request-level evidence upload/read/retention uses the
production encrypted authority first.
"""
from __future__ import annotations

import os
from urllib.parse import quote

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from app.modules.workforce import persistence
from app.modules.workforce.router import _require_rows_in_scope
from .candidate_evidence_runtime import (
    CandidateEvidenceRuntimeError,
    purge_expired_encrypted_candidate_evidence,
)
from .recruitment_evidence_runtime import (
    RecruitmentEvidenceRuntimeError,
    purge_expired_encrypted_request_evidence,
    read_request_evidence,
    secure_request_evidence_upload,
)
from .router import _identity, _read_upload_limited, _request_row, _require
from .service import RecruitmentRuleError, add_evidence, purge_expired_recruitment_data


router = APIRouter(prefix="/recruitment", tags=["Recruitment"])


def _encrypted_mode() -> bool:
    return (
        os.getenv("DOCKOS_ENV", "development").strip().lower() == "production"
        or os.getenv("RECRUITMENT_EVIDENCE_STORAGE_MODE", "disabled").strip().lower()
        == "s3-kms-envelope"
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
            return secure_request_evidence_upload(
                request_id,
                filename=file.filename or "document",
                content_type=content_type,
                content=content,
                actor=actor,
            )
        return add_evidence(
            request_id,
            file.filename or "document",
            content_type,
            content,
            actor,
        )
    except (RecruitmentRuleError, RecruitmentEvidenceRuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/evidence")
def download_request_evidence(
    request_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
):
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    try:
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
    except RecruitmentEvidenceRuntimeError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
