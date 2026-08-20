"""Cross-functional onboarding inbox routes."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.modules.workforce.authorization import is_action_allowed
from app.modules.workforce.router import _scoped_rows
from .onboarding_inbox import OnboardingInboxError, list_owner_tasks


router = APIRouter(prefix="/recruitment/onboarding", tags=["Recruitment Onboarding"])

_OWNER_ROLES = {
    "HR": {"hr", "recruitment_hr"},
    "IT": {"it", "it_admin", "identity_admin", "platform_admin"},
    "ADMIN": {"asset_admin", "facility_admin", "platform_admin"},
    "ACADEMY": {"academy_admin", "learning_admin", "trainer", "platform_admin"},
    "OPERATIONS": {"warehouse_manager", "manager", "regional_executive", "regional_manager", "by", "operations_manager"},
}


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


@router.get("/tasks")
def my_onboarding_tasks(
    request: Request,
    include_terminal: bool = False,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    owners = _allowed_owner_roles(x_opex_role, x_opex_permissions)
    if not owners:
        raise HTTPException(status_code=403, detail="Bu kullanıcıya atanmış onboarding görev alanı bulunmuyor.")
    try:
        rows = list_owner_tasks(owners, include_terminal=include_terminal)
        return _scoped_rows(request, x_opex_role, rows)
    except OnboardingInboxError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
