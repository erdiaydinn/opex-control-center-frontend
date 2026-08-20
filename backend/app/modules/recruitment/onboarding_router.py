"""Cross-functional onboarding inbox and owner-action routes."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.modules.workforce.authorization import is_action_allowed
from app.modules.workforce.router import _require_rows_in_scope, _scoped_rows
from .onboarding_inbox import OnboardingInboxError, list_owner_tasks
from .orchestration import RecruitmentOrchestrationError, update_onboarding_task
from .orchestration_scope import RecruitmentScopeError, onboarding_task_scope
from .router import _identity, _request_row


router = APIRouter(prefix="/recruitment/onboarding", tags=["Recruitment Onboarding"])

_OWNER_ROLES = {
    "HR": {"hr", "recruitment_hr"},
    "IT": {"it", "it_admin", "identity_admin", "platform_admin"},
    "ADMIN": {"asset_admin", "facility_admin", "platform_admin"},
    "ACADEMY": {"academy_admin", "learning_admin", "trainer", "platform_admin"},
    "OPERATIONS": {"warehouse_manager", "manager", "regional_executive", "regional_manager", "by", "operations_manager"},
}


class OwnerTaskUpdate(BaseModel):
    status: str = Field(pattern=r"^(IN_PROGRESS|BLOCKED|COMPLETED)$")
    note: str = Field(default="", max_length=2000)


class WaiveTaskInput(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


def _normalized_role(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _allowed_owner_roles(role: str, permissions: str) -> set[str]:
    if is_action_allowed(role, permissions, "manageRecruitmentOnboarding"):
        return set(_OWNER_ROLES)
    normalized = _normalized_role(role)
    allowed = {owner for owner, roles in _OWNER_ROLES.items() if normalized in roles}
    allowed.update(
        owner
        for owner in _OWNER_ROLES
        if is_action_allowed(role, permissions, f"completeRecruitmentOnboarding:{owner}")
    )
    return allowed


def _guard_task_scope(task_id: str, request: Request, role: str) -> tuple[str, str]:
    request_id, owner_role = onboarding_task_scope(task_id)
    _require_rows_in_scope(request, role, [_request_row(request_id)])
    return request_id, owner_role


def _require_owner(role: str, permissions: str, owner_role: str) -> None:
    if owner_role in _allowed_owner_roles(role, permissions):
        return
    raise HTTPException(status_code=403, detail=f"Bu onboarding görevi {owner_role} ekibine aittir.")


@router.get("/tasks")
def my_onboarding_tasks(
    request: Request,
    include_terminal: bool = False,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    owners = _allowed_owner_roles(x_opex_role, x_opex_permissions)
    if not owners:
        # Empty work is not an authorization error. This keeps the global My Tasks
        # launcher useful for every authenticated employee without revealing data.
        return []
    try:
        rows = list_owner_tasks(owners, include_terminal=include_terminal)
        return _scoped_rows(request, x_opex_role, rows)
    except OnboardingInboxError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/tasks/{task_id}")
def update_my_onboarding_task(
    task_id: str,
    payload: OwnerTaskUpdate,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Owner action endpoint. Required tasks cannot be waived here."""
    try:
        _, owner_role = _guard_task_scope(task_id, request, x_opex_role)
        _require_owner(x_opex_role, x_opex_permissions, owner_role)
        if payload.status == "BLOCKED" and not payload.note.strip():
            raise HTTPException(status_code=422, detail="Blocked onboarding görevi için açıklama zorunludur.")
        actor, _ = _identity(request)
        return update_onboarding_task(
            task_id,
            status=payload.status,
            note=payload.note.strip(),
            actor=actor,
        )
    except (RecruitmentOrchestrationError, RecruitmentScopeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/tasks/{task_id}/waive")
def waive_onboarding_task(
    task_id: str,
    payload: WaiveTaskInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Exceptional governance action; ordinary task owners cannot self-waive."""
    if not is_action_allowed(x_opex_role, x_opex_permissions, "manageRecruitmentOnboarding"):
        raise HTTPException(status_code=403, detail="Required onboarding task waiver için merkezi onboarding yönetim yetkisi gerekir.")
    try:
        _guard_task_scope(task_id, request, x_opex_role)
        actor, _ = _identity(request)
        return update_onboarding_task(task_id, status="WAIVED", note=payload.note.strip(), actor=actor)
    except (RecruitmentOrchestrationError, RecruitmentScopeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
