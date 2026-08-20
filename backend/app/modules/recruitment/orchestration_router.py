"""API surface for governed recruitment orchestration."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.modules.workforce.router import _require_rows_in_scope
from .orchestration import (
    RecruitmentOrchestrationError,
    append_candidate_note,
    assign_pipeline,
    candidate_orchestration_summary,
    create_offer,
    create_pipeline_template,
    decide_offer_with_capability,
    funnel_analytics,
    get_offer_by_capability,
    issue_offer_decision_capability,
    list_pipeline_templates,
    require_hire_ready,
    submit_scorecard,
    transition_stage,
    update_onboarding_task,
)
from .router import _identity, _request_row, _require
from .schemas import RecruitmentHireActivate
from .service import RecruitmentRuleError, activate_hire


router = APIRouter(prefix="/recruitment", tags=["Recruitment Orchestration"])
public_router = APIRouter(prefix="/public/recruitment", tags=["Candidate Offer"])


class PipelineStageInput(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    sla_hours: int = Field(default=72, ge=1, le=24 * 60)
    min_scorecards: int = Field(default=0, ge=0, le=20)
    min_average_score: float | None = Field(default=None, ge=0, le=100)
    allow_skip: bool = False


class PipelineTemplateInput(BaseModel):
    template_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    stages: list[PipelineStageInput] = Field(min_length=2, max_length=20)


class PipelineAssignmentInput(BaseModel):
    template_id: str = Field(min_length=36, max_length=36)


class PipelineTransitionInput(BaseModel):
    to_stage: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=2000)


class ScorecardInput(BaseModel):
    competencies: dict[str, float] = Field(min_length=1, max_length=20)
    recommendation: str = Field(min_length=1, max_length=32)
    conflict_declared: bool = False


class CandidateNoteInput(BaseModel):
    note_type: str = Field(pattern=r"^(INTERVIEW|PROCESS|RISK|FOLLOW_UP)$")
    visibility: str = Field(pattern=r"^(RECRUITMENT_TEAM|HR_ONLY)$")
    body: str = Field(min_length=1, max_length=4000)


class OfferInput(BaseModel):
    package: dict[str, Any]
    expires_in_hours: int = Field(default=168, ge=1, le=24 * 30)


class OfferCapabilityInput(BaseModel):
    expires_in_hours: int = Field(default=168, ge=1, le=24 * 30)


class CandidateOfferCapabilityInput(BaseModel):
    capability: str = Field(min_length=40, max_length=256)


class CandidateOfferDecisionInput(CandidateOfferCapabilityInput):
    decision: str = Field(pattern=r"^(ACCEPTED|DECLINED)$")


class OnboardingTaskUpdate(BaseModel):
    status: str = Field(pattern=r"^(IN_PROGRESS|BLOCKED|COMPLETED|WAIVED)$")
    note: str = Field(default="", max_length=2000)


def _guard_candidate_scope(request_id: str, request: Request, role: str) -> None:
    _require_rows_in_scope(request, role, [_request_row(request_id)])


@router.get("/orchestration/pipelines")
def get_pipeline_templates(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    try:
        return list_pipeline_templates()
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/orchestration/pipelines", status_code=status.HTTP_201_CREATED)
def add_pipeline_template(
    payload: PipelineTemplateInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "manageRecruitmentSettings")
    actor, _ = _identity(request)
    try:
        return create_pipeline_template(
            template_key=payload.template_key,
            name=payload.name,
            stages=[stage.model_dump() for stage in payload.stages],
            actor=actor,
        )
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/pipeline", status_code=status.HTTP_201_CREATED)
def attach_pipeline(
    request_id: str,
    candidate_id: str,
    payload: PipelineAssignmentInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _guard_candidate_scope(request_id, request, x_opex_role)
    actor, _ = _identity(request)
    try:
        return assign_pipeline(request_id, candidate_id, payload.template_id, actor)
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/pipeline/transition")
def move_pipeline_stage(
    request_id: str,
    candidate_id: str,
    payload: PipelineTransitionInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _guard_candidate_scope(request_id, request, x_opex_role)
    actor, _ = _identity(request)
    try:
        return transition_stage(request_id, candidate_id, payload.to_stage, payload.reason, actor)
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/interviews/scorecards", status_code=status.HTTP_201_CREATED)
def add_scorecard(
    request_id: str,
    candidate_id: str,
    payload: ScorecardInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _guard_candidate_scope(request_id, request, x_opex_role)
    actor, _ = _identity(request)
    try:
        return submit_scorecard(
            request_id,
            candidate_id,
            competencies=payload.competencies,
            recommendation=payload.recommendation,
            conflict_declared=payload.conflict_declared,
            interviewer_id=actor,
        )
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/notes", status_code=status.HTTP_201_CREATED)
def add_candidate_note(
    request_id: str,
    candidate_id: str,
    payload: CandidateNoteInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _guard_candidate_scope(request_id, request, x_opex_role)
    actor, _ = _identity(request)
    try:
        return append_candidate_note(
            request_id,
            candidate_id,
            note_type=payload.note_type,
            visibility=payload.visibility,
            body=payload.body,
            actor=actor,
        )
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/candidates/{candidate_id}/offers", status_code=status.HTTP_201_CREATED)
def add_offer(
    request_id: str,
    candidate_id: str,
    payload: OfferInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _guard_candidate_scope(request_id, request, x_opex_role)
    actor, _ = _identity(request)
    try:
        return create_offer(
            request_id,
            candidate_id,
            package=payload.package,
            expires_in_hours=payload.expires_in_hours,
            actor=actor,
        )
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/offers/{offer_id}/decision-capabilities", status_code=status.HTTP_201_CREATED)
def create_offer_capability(
    offer_id: str,
    payload: OfferCapabilityInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    actor, _ = _identity(request)
    try:
        return issue_offer_decision_capability(
            offer_id, expires_in_hours=payload.expires_in_hours, actor=actor
        )
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/onboarding/tasks/{task_id}")
def change_onboarding_task(
    task_id: str,
    payload: OnboardingTaskUpdate,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    actor, _ = _identity(request)
    try:
        return update_onboarding_task(task_id, status=payload.status, note=payload.note, actor=actor)
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/candidates/{candidate_id}/orchestration")
def get_candidate_orchestration(
    request_id: str,
    candidate_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    _guard_candidate_scope(request_id, request, x_opex_role)
    try:
        return candidate_orchestration_summary(request_id, candidate_id)
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/orchestration/analytics")
def get_orchestration_analytics(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    try:
        return funnel_analytics()
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/requests/{request_id}/hires", status_code=status.HTTP_201_CREATED)
def orchestrated_hire_and_activate(
    request_id: str,
    payload: RecruitmentHireActivate,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    """Priority hire route: no activation before pipeline+offer+onboarding readiness."""
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _guard_candidate_scope(request_id, request, x_opex_role)
    actor, _ = _identity(request)
    try:
        readiness = require_hire_ready(request_id, payload.candidate_id)
        result = activate_hire(request_id, payload.model_dump(mode="json"), actor)
        return {**result, "orchestration_readiness": readiness}
    except (RecruitmentOrchestrationError, RecruitmentRuleError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@public_router.post("/offer")
def candidate_offer_view(payload: CandidateOfferCapabilityInput) -> dict:
    """Capability-only candidate offer view; token is carried in the request body, not URL/logs."""
    try:
        return get_offer_by_capability(payload.capability)
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=404, detail="Offer capability geçersiz veya süresi dolmuş.") from error


@public_router.post("/offer/decision")
def candidate_offer_decision(payload: CandidateOfferDecisionInput) -> dict:
    """Single-use candidate decision. This is not represented as a qualified e-signature."""
    try:
        return decide_offer_with_capability(payload.capability, payload.decision)
    except RecruitmentOrchestrationError as error:
        raise HTTPException(status_code=409, detail="Offer decision capability geçersiz veya süresi dolmuş.") from error
