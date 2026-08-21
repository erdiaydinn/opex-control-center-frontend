"""Priority API router for Hiring V47 lifecycle governance."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.modules.workforce.authorization import is_action_allowed
from app.modules.workforce.router import _require_rows_in_scope
from .lifecycle_authority import (
    RecruitmentLifecycleError,
    add_to_talent_pool,
    claim_candidate_communications,
    close_offboarding_case,
    create_offboarding_case,
    create_offer_for_approval,
    decide_offer_approval,
    issue_approved_offer_capability,
    list_candidate_communications,
    list_offboarding_cases,
    list_talent_pool,
    offer_approval_summary,
    queue_candidate_communication,
    settle_candidate_communication,
    update_offboarding_task,
    withdraw_talent_pool_membership,
)
from .orchestration_scope import RecruitmentScopeError, offer_request_id
from .router import _identity, _request_row, _require


router = APIRouter(prefix="/recruitment", tags=["Recruitment Lifecycle"])


class GovernedOfferInput(BaseModel):
    package: dict[str, Any]
    expires_in_hours: int = Field(default=168, ge=1, le=24 * 30)


class OfferApprovalInput(BaseModel):
    decision: str = Field(pattern=r"^(APPROVED|REJECTED)$")
    reason: str = Field(default="", max_length=2000)


class OfferCapabilityInput(BaseModel):
    expires_in_hours: int = Field(default=168, ge=1, le=24 * 30)


class CommunicationInput(BaseModel):
    message_type: str = Field(pattern=r"^(INTERVIEW_INVITE|INTERVIEW_REMINDER|OFFER_READY|OFFER_REMINDER|ONBOARDING_REMINDER|PROCESS_UPDATE|TALENT_POOL_REENGAGE)$")
    channel: str = Field(pattern=r"^(EMAIL|SMS|IN_APP)$")
    locale: str = Field(default="tr-TR", min_length=2, max_length=20)
    template_key: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=160)
    available_at: datetime | None = None


class CommunicationClaimInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class CommunicationSettleInput(BaseModel):
    delivered: bool
    failure_code: str = Field(default="", max_length=200)


class TalentPoolInput(BaseModel):
    pool_key: str = Field(min_length=1, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=20)
    consent_basis: str = Field(pattern=r"^(EXPLICIT_CANDIDATE_CONSENT|LEGITIMATE_INTEREST_REVIEWED)$")
    consent_record_ref: str = Field(min_length=1, max_length=240)
    consent_days: int = Field(default=365, ge=1, le=730)


class OffboardingCreateInput(BaseModel):
    employee_id: str = Field(min_length=1, max_length=80)
    effective_at: datetime
    reason_code: str = Field(pattern=r"^(RESIGNATION|TERMINATION|TRANSFER|CONTRACT_END|OTHER)$")
    note: str = Field(default="", max_length=2000)


class OffboardingTaskInput(BaseModel):
    status: str = Field(pattern=r"^(IN_PROGRESS|BLOCKED|COMPLETED|WAIVED)$")
    note: str = Field(default="", max_length=2000)


def _candidate_scope(request_id: str, request: Request, role: str) -> None:
    _require_rows_in_scope(request, role, [_request_row(request_id)])


def _actor(request: Request) -> str:
    return _identity(request)[0]


def _require_delivery_worker(role: str, permissions: str) -> None:
    if not is_action_allowed(role, permissions, "deliverRecruitmentCommunication"):
        raise HTTPException(status_code=403, detail="Recruitment communication delivery worker yetkisi gerekli.")


@router.post("/requests/{request_id}/candidates/{candidate_id}/offers", status_code=status.HTTP_201_CREATED)
def create_governed_offer(
    request_id: str,
    candidate_id: str,
    payload: GovernedOfferInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Priority shadow: offer package is a draft until independent approval quorum."""
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _candidate_scope(request_id, request, x_opex_role)
    try:
        return create_offer_for_approval(
            request_id,
            candidate_id,
            package=payload.package,
            expires_in_hours=payload.expires_in_hours,
            actor=_actor(request),
        )
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/offers/{offer_id}/approvals")
def approve_governed_offer(
    offer_id: str,
    payload: OfferApprovalInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentOffer")
    try:
        request_id = offer_request_id(offer_id)
        _candidate_scope(request_id, request, x_opex_role)
        return decide_offer_approval(offer_id, decision=payload.decision, reason=payload.reason, actor=_actor(request))
    except (RecruitmentLifecycleError, RecruitmentScopeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/offers/{offer_id}/approvals")
def get_offer_approvals(
    offer_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    try:
        request_id = offer_request_id(offer_id)
        _candidate_scope(request_id, request, x_opex_role)
        return offer_approval_summary(offer_id)
    except (RecruitmentLifecycleError, RecruitmentScopeError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/offers/{offer_id}/decision-capabilities", status_code=status.HTTP_201_CREATED)
def issue_governed_offer_capability(
    offer_id: str,
    payload: OfferCapabilityInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Priority shadow: no candidate offer token before approval quorum."""
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    try:
        request_id = offer_request_id(offer_id)
        _candidate_scope(request_id, request, x_opex_role)
        return issue_approved_offer_capability(offer_id, expires_in_hours=payload.expires_in_hours, actor=_actor(request))
    except (RecruitmentLifecycleError, RecruitmentScopeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/communications", status_code=status.HTTP_201_CREATED)
def queue_communication(
    request_id: str,
    candidate_id: str,
    payload: CommunicationInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentCommunications")
    _candidate_scope(request_id, request, x_opex_role)
    try:
        return queue_candidate_communication(
            request_id,
            candidate_id,
            message_type=payload.message_type,
            channel=payload.channel,
            locale=payload.locale,
            template_key=payload.template_key,
            payload=payload.payload,
            idempotency_key=payload.idempotency_key,
            available_at=payload.available_at,
            actor=_actor(request),
        )
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/candidates/{candidate_id}/communications")
def get_communications(
    request_id: str,
    candidate_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    _candidate_scope(request_id, request, x_opex_role)
    try:
        return list_candidate_communications(request_id, candidate_id)
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/communications/claim")
def claim_communications(
    payload: CommunicationClaimInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require_delivery_worker(x_opex_role, x_opex_permissions)
    try:
        return claim_candidate_communications(worker=_actor(request), limit=payload.limit)
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/communications/{message_id}/settle")
def settle_communication(
    message_id: str,
    payload: CommunicationSettleInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require_delivery_worker(x_opex_role, x_opex_permissions)
    try:
        return settle_candidate_communication(
            message_id, delivered=payload.delivered, failure_code=payload.failure_code, worker=_actor(request)
        )
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/talent-pool", status_code=status.HTTP_201_CREATED)
def add_candidate_to_pool(
    request_id: str,
    candidate_id: str,
    payload: TalentPoolInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentTalentPool")
    _candidate_scope(request_id, request, x_opex_role)
    try:
        return add_to_talent_pool(
            request_id,
            candidate_id,
            pool_key=payload.pool_key,
            tags=payload.tags,
            consent_basis=payload.consent_basis,
            consent_record_ref=payload.consent_record_ref,
            consent_days=payload.consent_days,
            actor=_actor(request),
        )
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/talent-pool")
def get_talent_pool(
    pool_key: str | None = None,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    try:
        return list_talent_pool(pool_key)
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/talent-pool/{membership_id}/withdraw")
def withdraw_pool_member(
    membership_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentTalentPool")
    try:
        return withdraw_talent_pool_membership(membership_id, actor=_actor(request))
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/offboarding", status_code=status.HTTP_201_CREATED)
def create_offboarding(
    payload: OffboardingCreateInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentOffboarding")
    try:
        return create_offboarding_case(
            payload.employee_id,
            effective_at=payload.effective_at,
            reason_code=payload.reason_code,
            note=payload.note,
            actor=_actor(request),
        )
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/offboarding")
def get_offboarding(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    try:
        return list_offboarding_cases()
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/offboarding/tasks/{task_id}")
def change_offboarding_task(
    task_id: str,
    payload: OffboardingTaskInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentOffboarding")
    try:
        return update_offboarding_task(task_id, status=payload.status, note=payload.note, actor=_actor(request))
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/offboarding/{case_id}/close")
def close_offboarding(
    case_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentOffboarding")
    try:
        return close_offboarding_case(case_id, actor=_actor(request))
    except RecruitmentLifecycleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
