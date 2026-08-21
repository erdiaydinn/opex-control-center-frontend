"""Priority governance/read projections for Hiring V47 lifecycle authority."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.modules.workforce.authorization import is_action_allowed
from app.modules.workforce.router import _require_rows_in_scope
from .lifecycle_authority import (
    RecruitmentLifecycleError,
    claim_candidate_communications,
    close_offboarding_case,
    offer_approval_summary,
    update_offboarding_task,
)
from .lifecycle_projection import (
    list_communication_outbox,
    list_offer_approval_workflows,
    offboarding_task_authority,
)
from .lifecycle_reminders import plan_due_reminders
from .lifecycle_router import CommunicationClaimInput, OffboardingTaskInput
from .orchestration import RecruitmentOrchestrationError, candidate_orchestration_summary
from .router import _identity, _request_row, _require


router = APIRouter(prefix="/recruitment", tags=["Recruitment Lifecycle Governance"])


def _allowed(role: str, permissions: str, action: str) -> bool:
    return is_action_allowed(role, permissions, action)


def _actor(request: Request) -> str:
    return _identity(request)[0]


def _require_delivery_worker(role: str, permissions: str) -> None:
    if not _allowed(role, permissions, "deliverRecruitmentCommunication"):
        raise HTTPException(status_code=403, detail="Recruitment communication delivery worker yetkisi gerekli.")


def _require_offboarding_task_authority(role: str, permissions: str, owner_role: str, target_status: str) -> None:
    if target_status == "WAIVED":
        if not _allowed(role, permissions, "waiveRecruitmentOffboarding"):
            raise HTTPException(status_code=403, detail="Required offboarding task waiver için merkezi waiver yetkisi gerekli.")
        return
    if _allowed(role, permissions, "manageRecruitmentOffboarding"):
        return
    owner_action = f"completeRecruitmentOffboarding:{owner_role}"
    if not _allowed(role, permissions, owner_action):
        raise HTTPException(status_code=403, detail=f"{owner_role} offboarding task yetkisi gerekli.")


@router.get("/requests/{request_id}/candidates/{candidate_id}/orchestration")
def governed_candidate_orchestration(
    request_id: str,
    candidate_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Priority shadow: V47 draft offers expose approval truth instead of a null offer state."""
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    _require_rows_in_scope(request, x_opex_role, [_request_row(request_id)])
    try:
        result = candidate_orchestration_summary(request_id, candidate_id)
        for offer in result.get("offers", []):
            try:
                approval = offer_approval_summary(offer["offer_id"])
            except RecruitmentLifecycleError:
                offer["approval_status"] = None
                offer["approval_count"] = None
                offer["required_approvals"] = None
                continue
            offer["approval_status"] = approval["status"]
            offer["approval_count"] = len([row for row in approval["approvals"] if row["decision"] == "APPROVED"])
            offer["required_approvals"] = approval["required_approvals"]
            offer["candidate_delivery_allowed"] = approval["candidate_delivery_allowed"]
            if not offer.get("state"):
                offer["state"] = "PENDING" if approval["status"] == "PENDING" else approval["status"]
        return result
    except (RecruitmentLifecycleError, RecruitmentOrchestrationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/offers/approvals")
def list_offer_approvals(
    status: str | None = None,
    limit: int = 100,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    try:
        return list_offer_approval_workflows(status=status, limit=limit)
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/communications")
def list_communications(
    status: str | None = None,
    limit: int = 100,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    try:
        return list_communication_outbox(status=status, limit=limit)
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/communications/claim")
def governed_communication_claim(
    payload: CommunicationClaimInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Planner+claim is one governed worker operation; no external scheduler is required."""
    _require_delivery_worker(x_opex_role, x_opex_permissions)
    try:
        planned = plan_due_reminders()
        messages = claim_candidate_communications(worker=_actor(request), limit=payload.limit)
        return {"planned": planned, "messages": messages}
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/offboarding/tasks/{task_id}")
def governed_offboarding_task_update(
    task_id: str,
    payload: OffboardingTaskInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    try:
        authority = offboarding_task_authority(task_id)
        _require_offboarding_task_authority(
            x_opex_role,
            x_opex_permissions,
            authority["owner_role"],
            payload.status,
        )
        return update_offboarding_task(
            task_id,
            status=payload.status,
            note=payload.note,
            actor=_actor(request),
        )
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/offboarding/{case_id}/close")
def governed_offboarding_close(
    case_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    if not _allowed(x_opex_role, x_opex_permissions, "closeRecruitmentOffboarding"):
        raise HTTPException(status_code=403, detail="Offboarding case kapatma yetkisi gerekli.")
    try:
        return close_offboarding_case(case_id, actor=_actor(request))
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
