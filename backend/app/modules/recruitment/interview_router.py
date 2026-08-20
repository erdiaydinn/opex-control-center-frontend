"""Authenticated HR and capability-only candidate interview scheduling routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.modules.workforce.router import _require_rows_in_scope
from .interview_scheduling import (
    InterviewSchedulingError,
    create_schedule,
    issue_booking_capability,
    list_candidate_schedules,
    mutate_candidate_booking,
    schedule_scope,
    update_schedule_status,
    view_candidate_schedule,
)
from .router import _identity, _request_row, _require


router = APIRouter(prefix="/recruitment", tags=["Recruitment Interviews"])
public_router = APIRouter(prefix="/public/recruitment", tags=["Candidate Interview"])


class InterviewSlotInput(BaseModel):
    starts_at: datetime
    ends_at: datetime | None = None
    capacity: int = Field(default=1, ge=1, le=20)


class InterviewScheduleInput(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    timezone: str = Field(min_length=1, max_length=80)
    meeting_mode: str = Field(pattern=r"^(ONSITE|REMOTE|PHONE)$")
    location_label: str = Field(default="", max_length=500)
    instructions: str = Field(default="", max_length=2000)
    duration_minutes: int = Field(default=45, ge=10, le=480)
    slots: list[InterviewSlotInput] = Field(min_length=1, max_length=40)


class InterviewCapabilityInput(BaseModel):
    expires_in_hours: int = Field(default=168, ge=1, le=24 * 30)


class InterviewScheduleStatusInput(BaseModel):
    status: str = Field(pattern=r"^(OPEN|CLOSED|CANCELLED)$")


class CandidateInterviewCapabilityInput(BaseModel):
    capability: str = Field(min_length=40, max_length=256)


class CandidateInterviewMutationInput(CandidateInterviewCapabilityInput):
    action: str = Field(pattern=r"^(BOOK|RESCHEDULE|CANCEL)$")
    slot_id: str | None = Field(default=None, max_length=36)


def _scope(request_id: str, request: Request, role: str) -> None:
    _require_rows_in_scope(request, role, [_request_row(request_id)])


def _schedule_scope(schedule_id: str, request: Request, role: str) -> str:
    request_id = schedule_scope(schedule_id)
    _scope(request_id, request, role)
    return request_id


@router.post("/requests/{request_id}/candidates/{candidate_id}/interviews", status_code=status.HTTP_201_CREATED)
def add_interview_schedule(
    request_id: str,
    candidate_id: str,
    payload: InterviewScheduleInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _scope(request_id, request, x_opex_role)
    actor, _ = _identity(request)
    try:
        return create_schedule(
            request_id,
            candidate_id,
            title=payload.title,
            timezone=payload.timezone,
            meeting_mode=payload.meeting_mode,
            location_label=payload.location_label,
            instructions=payload.instructions,
            duration_minutes=payload.duration_minutes,
            slots=[slot.model_dump() for slot in payload.slots],
            actor=actor,
        )
    except InterviewSchedulingError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/requests/{request_id}/candidates/{candidate_id}/interviews")
def get_interview_schedules(
    request_id: str,
    candidate_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> list[dict]:
    _require(x_opex_role, x_opex_permissions, "viewRecruitment")
    _scope(request_id, request, x_opex_role)
    try:
        return list_candidate_schedules(request_id, candidate_id)
    except InterviewSchedulingError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/interviews/{schedule_id}/status")
def set_interview_schedule_status(
    schedule_id: str,
    payload: InterviewScheduleStatusInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    try:
        _schedule_scope(schedule_id, request, x_opex_role)
        actor, _ = _identity(request)
        return update_schedule_status(schedule_id, payload.status, actor)
    except InterviewSchedulingError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/requests/{request_id}/candidates/{candidate_id}/interviews/{schedule_id}/booking-capabilities",
    status_code=status.HTTP_201_CREATED,
)
def create_interview_capability(
    request_id: str,
    candidate_id: str,
    schedule_id: str,
    payload: InterviewCapabilityInput,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict:
    _require(x_opex_role, x_opex_permissions, "approveRecruitmentRequest")
    _scope(request_id, request, x_opex_role)
    try:
        if schedule_scope(schedule_id) != request_id:
            raise InterviewSchedulingError("Interview schedule request scope ile eşleşmiyor.")
        actor, _ = _identity(request)
        return issue_booking_capability(
            schedule_id,
            candidate_id,
            expires_in_hours=payload.expires_in_hours,
            actor=actor,
        )
    except InterviewSchedulingError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@public_router.post("/interview")
def candidate_interview_view(payload: CandidateInterviewCapabilityInput) -> dict:
    try:
        return view_candidate_schedule(payload.capability)
    except InterviewSchedulingError as error:
        raise HTTPException(status_code=404, detail="Interview bağlantısı geçersiz veya süresi dolmuş.") from error


@public_router.post("/interview/decision")
def candidate_interview_mutation(payload: CandidateInterviewMutationInput) -> dict:
    try:
        return mutate_candidate_booking(payload.capability, payload.action, payload.slot_id)
    except InterviewSchedulingError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
