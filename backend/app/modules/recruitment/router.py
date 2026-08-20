from __future__ import annotations

import os

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.modules.workforce.authorization import is_action_allowed
from app.modules.workforce import persistence
from app.modules.workforce.router import _require_rows_in_scope, _scoped_rows
from .hr_actual import build_dashboard, enrich_evaluation, import_snapshot, snapshot_summary
from .schemas import (
    RecruitmentCandidateCreate, RecruitmentCandidateDecision, RecruitmentCandidateDocumentAttestation,
    RecruitmentCandidateUploadCapabilityCreate,
    RecruitmentCandidateDocumentVerification, RecruitmentDecision,
    RecruitmentHireActivate, RecruitmentHrActualImport, RecruitmentRequestCreate,
    RecruitmentSettingsUpdate, StaffingNormPatch,
)
from .service import (
    RecruitmentRuleError,
    _EVIDENCE_DIR,
    add_candidate_evidence,
    add_evidence,
    activate_hire,
    candidate_evidence_path,
    create_request,
    decide_request,
    decide_candidate,
    dispatch_email,
    evidence_path,
    evaluate,
    get_settings,
    list_norms,
    list_outbox,
    list_requests,
    purge_expired_recruitment_data,
    register_candidate,
    issue_candidate_upload_capability,
    consume_candidate_upload_capability,
    attest_candidate_document_verification,
    record_candidate_document_verification,
    _validate_candidate_document_bytes,
    update_settings,
    upsert_norm,
)


router = APIRouter(prefix="/recruitment", tags=["Recruitment"])


async def _read_upload_limited(file: UploadFile, limit: int = 10 * 1024 * 1024) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(min(1024 * 1024, limit + 1 - size))
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > limit:
            raise RecruitmentRuleError("Aday kanıtı 10 MB sınırını aşıyor.")
        chunks.append(chunk)


def _require_candidate_upload_authority_runtime() -> None:
    environment = os.getenv("DOCKOS_ENV", "development").strip().lower()
    mode = os.getenv("RECRUITMENT_CANDIDATE_UPLOAD_AUTHORITY_MODE", "disabled").strip().lower()
    postgres_ready = mode == "postgres" and persistence.ENABLED and persistence.schema_version() >= 39
    legacy_ready = environment != "production" and mode == "legacy-development"
    if not (postgres_ready or legacy_ready):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CANDIDATE_UPLOAD_AUTHORITY_NOT_READY",
                "message": "Aday yükleme otoritesi atomik PostgreSQL finalize olmadan etkinleştirilemez.",
            },
        )

_HR_ACTIONS = {
    "viewRecruitment", "createRecruitmentRequest", "approveRecruitmentRequest",
    "viewRecruitmentEvidence", "manageRecruitmentNorms", "manageRecruitmentActuals",
    "manageRecruitmentSettings", "manageRecruitmentNotifications",
}


def _require(role: str, permissions: str, action: str) -> None:
    normalized = role.strip().lower().replace("-", "_").replace(" ", "_")
    role_actions = {
        "warehouse_manager": {"viewRecruitment", "createRecruitmentRequest"},
        "manager": {"viewRecruitment", "createRecruitmentRequest"},
        "regional_executive": {"viewRecruitment", "createRecruitmentRequest"},
        "regional_manager": {"viewRecruitment", "createRecruitmentRequest"},
        "by": {"viewRecruitment", "createRecruitmentRequest"},
        "hr": _HR_ACTIONS,
        "recruitment_hr": _HR_ACTIONS,
    }
    if action in role_actions.get(normalized, set()):
        return
    if not is_action_allowed(role, permissions, action):
        raise HTTPException(status_code=403, detail=f"Bu işlem için {action} yetkisi gerekir.")


def _identity(request: Request) -> tuple[str, str]:
    identity = getattr(request.state, "identity", None)
    return (getattr(identity, "subject", "unknown"), getattr(identity, "name", "Unknown User"))


def _is_recruitment_admin(role: str, permissions: str) -> bool:
    normalized = role.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {
        "super_admin", "superadmin", "admin", "administrator", "hr", "recruitment_hr",
    }:
        return True
    return any(
        is_action_allowed(role, permissions, action)
        for action in {
            "manageRecruitmentActuals", "manageRecruitmentSettings",
            "manageRecruitmentNotifications", "viewRecruitmentEvidence",
        }
    )


def _request_row(request_id: str) -> dict:
    row = next((item for item in list_requests() if item.get("id") == request_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Talep bulunamadı.")
    return row


def _without_evidence_metadata(row: dict) -> dict:
    sanitized = {**row, "evidence_present": bool(row.get("evidence"))}
    sanitized.pop("evidence", None)
    sanitized["candidates"] = [
        {
            **candidate,
            "evidence_count": len(candidate.get("evidence", [])),
            "evidence": [],
        }
        for candidate in row.get("candidates", [])
    ]
    return sanitized


def _current_staffing(row: dict) -> dict | None:
    warehouse_id = row.get("warehouse_id") or row.get("warehouse_name")
    position_code = row.get("position_code")
    if not warehouse_id or not position_code:
        return None
    try:
        return enrich_evaluation(
            evaluate(
                str(warehouse_id),
                str(position_code),
                max(1, int(row.get("quantity", 1))),
                row.get("planned_departure"),
                row.get("id"),
            )
        )
    except (RecruitmentRuleError, KeyError, TypeError, ValueError):
        return None


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok", "module": "recruitment", "norm_engine": True,
        "hr_actual": True, "evidence": True, "email_outbox": True,
    }


@router.get("/bootstrap")
def bootstrap(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    from app.modules.workforce.service import list_warehouses, list_people

    is_admin = _is_recruitment_admin(x_opex_role, x_opex_permissions)
    requests = _scoped_rows(request, x_opex_role, list_requests())
    requests = [{**row, "current_staffing": _current_staffing(row)} for row in requests]
    if not is_admin:
        requests = [_without_evidence_metadata(row) for row in requests]
    norms = _scoped_rows(
        request, x_opex_role,
        [{**row, "warehouse_id": row.get("warehouse")} for row in list_norms()],
    )
    warehouses = _scoped_rows(request, x_opex_role, list_warehouses())
    people = _scoped_rows(request, x_opex_role, list_people(False))
    summary = build_dashboard(norms, requests)
    return {
        "dashboard": summary, "requests": requests, "norms": norms,
        "settings": get_settings() if is_admin else None,
        "actual_snapshot": snapshot_summary() if is_admin else None,
        "email_outbox": list_outbox() if is_admin else [],
        "warehouses": warehouses, "people": people,
    }


@router.get("/evaluate")
def evaluate_request(
    warehouse_id: str, position_code: str, request: Request, quantity: int = 1,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [{"warehouse_id": warehouse_id}])
    try:
        return enrich_evaluation(evaluate(warehouse_id, position_code, quantity))
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/hr-actual/latest")
def get_hr_actual(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentActuals")
    return snapshot_summary() or {
        "source_name": None, "source_sha256": None, "as_of": None,
        "source_rows": 0, "active_rows": 0, "active_fte": 0,
        "matched_rows": 0, "unmatched_rows": 0, "match_rate": 0,
    }


@router.post("/hr-actual/import", status_code=status.HTTP_201_CREATED)
def import_hr_actual(
    payload: RecruitmentHrActualImport, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentActuals")
    actor, _ = _identity(request)
    try:
        return import_snapshot(payload.model_dump(mode="json"), actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def add_request(
    payload: RecruitmentRequestCreate, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [{"warehouse_id": payload.warehouse_id}])
    actor, actor_name = _identity(request)
    try:
        return create_request(payload.model_dump(mode="json"), actor, actor_name)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/evidence")
async def upload_evidence(
    request_id: str, request: Request, file: UploadFile = File(...),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return add_evidence(request_id, file.filename or "document", file.content_type or "application/octet-stream", await file.read(), actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/evidence")
def download_evidence(
    request_id: str, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
):
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    try:
        path, metadata = evidence_path(request_id)
        actor, _ = _identity(request)
        from app.modules.workforce import persistence
        persistence.append_audit(
            "RECRUITMENT_EVIDENCE_ACCESSED", actor, record_id=request_id,
            evidence_sha256=metadata.get("sha256"),
        )
        return FileResponse(
            path, media_type=metadata["content_type"], filename=metadata["original_name"],
            headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
        )
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/requests/{request_id}/decision")
def decide(
    request_id: str, payload: RecruitmentDecision, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, actor_name = _identity(request)
    try:
        return decide_request(request_id, payload.decision, payload.note, actor, actor_name)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/hires", status_code=status.HTTP_201_CREATED)
def hire_and_activate(
    request_id: str, payload: RecruitmentHireActivate, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return activate_hire(request_id, payload.model_dump(mode="json"), actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates", status_code=status.HTTP_201_CREATED)
def add_candidate(
    request_id: str, payload: RecruitmentCandidateCreate, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return register_candidate(request_id, payload.model_dump(), actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/evidence")
async def upload_candidate_evidence(
    request_id: str, candidate_id: str, request: Request, file: UploadFile = File(...),
    document_type: str = Form(default="OTHER"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return add_candidate_evidence(
            request_id, candidate_id, file.filename or "document",
            file.content_type or "application/octet-stream", await _read_upload_limited(file), actor,
            document_type=document_type,
        )
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/upload-capabilities", status_code=status.HTTP_201_CREATED)
def create_candidate_upload_capability(
    request_id: str, candidate_id: str, payload: RecruitmentCandidateUploadCapabilityCreate,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_candidate_upload_authority_runtime()
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return issue_candidate_upload_capability(
            request_id, candidate_id, payload.document_type, payload.expires_in_minutes, actor,
        )
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/candidate-upload/evidence", status_code=status.HTTP_201_CREATED)
async def upload_candidate_evidence_with_capability(
    file: UploadFile = File(...), document_type: str = Form(...),
    x_eay_upload_capability: str = Header(default="", alias="X-EAY-Upload-Capability"),
) -> dict:
    """Candidate-only upload boundary; grants no read, listing, or internal API access."""
    _require_candidate_upload_authority_runtime()
    try:
        content = await _read_upload_limited(file)
        content_type = file.content_type or "application/octet-stream"
        if content_type not in {"application/pdf", "image/jpeg", "image/png"}:
            raise RecruitmentRuleError("Aday kanıtı PDF/JPG/PNG olmalıdır.")
        _validate_candidate_document_bytes(content_type, content)
        if os.getenv("RECRUITMENT_CANDIDATE_UPLOAD_AUTHORITY_MODE", "disabled").strip().lower() == "postgres":
            from app.modules.recruitment import candidate_upload_authority

            try:
                evidence = candidate_upload_authority.finalize(
                    x_eay_upload_capability, document_type.strip().upper(),
                    file.filename or "document", content_type, content, _EVIDENCE_DIR,
                    retention_days=max(1, int(os.getenv("RECRUITMENT_EVIDENCE_RETENTION_DAYS", "365"))),
                )
            except candidate_upload_authority.CandidateUploadAuthorityError as error:
                raise RecruitmentRuleError(str(error)) from error
            return {
                "accepted": True, "receipt": evidence["sha256"],
                "document_type": evidence["document_type"],
                "content_safety_state": evidence["content_safety_state"],
            }
        request_id, candidate_id, capability_id = consume_candidate_upload_capability(
            x_eay_upload_capability, document_type,
        )
        candidate = add_candidate_evidence(
            request_id, candidate_id, file.filename or "document",
            content_type, content,
            f"candidate-capability:{capability_id}", document_type=document_type,
        )
        evidence = candidate["evidence"][-1]
        return {
            "accepted": True, "receipt": evidence["sha256"],
            "document_type": evidence["document_type"],
            "content_safety_state": evidence["content_safety_state"],
        }
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/document-verifications")
def verify_candidate_document(
    request_id: str, candidate_id: str, payload: RecruitmentCandidateDocumentVerification,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Record a human-witnessed result from the official e-Devlet portal.

    This endpoint deliberately cannot claim an automated official API result.
    Such authority must arrive through a separately authenticated service adapter.
    """
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return record_candidate_document_verification(
            request_id, candidate_id, payload.model_dump(mode="json"), actor,
            verification_method="HR_ASSISTED_OFFICIAL_PORTAL",
        )
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/document-verifications/attest")
def attest_candidate_document(
    request_id: str, candidate_id: str, payload: RecruitmentCandidateDocumentAttestation,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return attest_candidate_document_verification(
            request_id, candidate_id, payload.evidence_sha256, payload.note, actor,
        )
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/decision")
def candidate_decision(
    request_id: str, candidate_id: str, payload: RecruitmentCandidateDecision, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    actor, _ = _identity(request)
    try:
        return decide_candidate(request_id, candidate_id, payload.decision, payload.note, actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/candidates/{candidate_id}/evidence/{digest}")
def download_candidate_evidence(
    request_id: str, candidate_id: str, digest: str, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
):
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    try:
        path, metadata = candidate_evidence_path(request_id, candidate_id, digest)
        actor, _ = _identity(request)
        from app.modules.workforce import persistence
        persistence.append_audit(
            "RECRUITMENT_CANDIDATE_EVIDENCE_ACCESSED", actor, record_id=request_id,
            candidate_id=candidate_id, evidence_sha256=metadata.get("sha256"),
        )
        return FileResponse(
            path, media_type=metadata["content_type"], filename=metadata["original_name"],
            headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
        )
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.put("/settings")
def save_settings(
    payload: RecruitmentSettingsUpdate, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentSettings")
    actor, _ = _identity(request)
    return update_settings(payload.model_dump(), actor)


@router.put("/norms")
def save_norm(
    payload: StaffingNormPatch, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentNorms")
    _require_rows_in_scope(request, x_opex_role, [{"warehouse_id": payload.warehouse}])
    actor, _ = _identity(request)
    return upsert_norm(payload.model_dump(), actor)


@router.post("/email-outbox/{outbox_id}/retry")
def retry_email(
    outbox_id: str, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentNotifications")
    actor, _ = _identity(request)
    try:
        return dispatch_email(outbox_id, actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/retention/purge")
def purge_retention(
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentSettings")
    actor, _ = _identity(request)
    return purge_expired_recruitment_data(actor)
