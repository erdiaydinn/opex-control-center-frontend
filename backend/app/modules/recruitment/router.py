from __future__ import annotations

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.modules.workforce.authorization import is_action_allowed
from .schemas import RecruitmentDecision, RecruitmentHireActivate, RecruitmentRequestCreate, RecruitmentSettingsUpdate, StaffingNormPatch
from .service import (
    RecruitmentRuleError,
    add_evidence,
    activate_hire,
    create_request,
    dashboard,
    decide_request,
    dispatch_email,
    evidence_path,
    evaluate,
    get_settings,
    list_norms,
    list_outbox,
    list_requests,
    update_settings,
    upsert_norm,
)


router = APIRouter(prefix="/recruitment", tags=["Recruitment"])


def _require(role: str, permissions: str, action: str) -> None:
    normalized = role.strip().lower().replace("-", "_").replace(" ", "_")
    role_actions = {
        "warehouse_manager": {"viewRecruitment", "createRecruitmentRequest"},
        "manager": {"viewRecruitment", "createRecruitmentRequest"},
        "regional_executive": {"viewRecruitment", "createRecruitmentRequest"},
        "regional_manager": {"viewRecruitment", "createRecruitmentRequest"},
        "by": {"viewRecruitment", "createRecruitmentRequest"},
        "hr": {
            "viewRecruitment", "createRecruitmentRequest", "approveRecruitmentRequest",
            "viewRecruitmentEvidence", "manageRecruitmentNorms",
            "manageRecruitmentSettings", "manageRecruitmentNotifications",
        },
    }
    if action in role_actions.get(normalized, set()):
        return
    if not is_action_allowed(role, permissions, action):
        raise HTTPException(status_code=403, detail=f"Bu işlem için {action} yetkisi gerekir.")


def _identity(request: Request) -> tuple[str, str]:
    identity = getattr(request.state, "identity", None)
    return (getattr(identity, "subject", "unknown"), getattr(identity, "name", "Unknown User"))


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "module": "recruitment", "norm_engine": True, "evidence": True, "email_outbox": True}


@router.get("/bootstrap")
def bootstrap(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    from app.modules.workforce.service import list_warehouses, list_people
    return {
        "dashboard": dashboard(), "requests": list_requests(), "norms": list_norms(),
        "settings": get_settings(), "email_outbox": list_outbox(),
        "warehouses": list_warehouses(), "people": list_people(False),
    }


@router.get("/evaluate")
def evaluate_request(
    warehouse_id: str, position_code: str, quantity: int = 1,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createRecruitmentRequest")
    try:
        return evaluate(warehouse_id, position_code, quantity)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def add_request(
    payload: RecruitmentRequestCreate, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "createRecruitmentRequest")
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
    actor, _ = _identity(request)
    try:
        return add_evidence(request_id, file.filename or "document", file.content_type or "application/octet-stream", await file.read(), actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/evidence")
def download_evidence(
    request_id: str,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
):
    _require(x_opex_role, x_opex_permissions, "viewRecruitmentEvidence")
    try:
        path, metadata = evidence_path(request_id)
        return FileResponse(path, media_type=metadata["content_type"], filename=metadata["original_name"])
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/requests/{request_id}/decision")
def decide(
    request_id: str, payload: RecruitmentDecision, request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
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
    actor, _ = _identity(request)
    try:
        return activate_hire(request_id, payload.model_dump(mode="json"), actor)
    except RecruitmentRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
