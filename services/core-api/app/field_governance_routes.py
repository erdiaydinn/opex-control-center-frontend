from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.field_intelligence.authorization import require_field_permission
from app.modules.field_intelligence.governance import (
    FieldGovernanceError,
    create_recurrence_rule,
    decide_export,
    exempt_target,
    list_recurrence_rules,
    preview_server_targeting,
    request_export,
    retire_template_version,
)
from app.modules.field_intelligence.repository import list_locations

router = APIRouter(prefix="/v1/field/governance", tags=["field-governance"])
FieldViewer = Annotated[
    Principal,
    Depends(require_permission("module:field_intelligence:view")),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecurrenceCreate(StrictModel):
    cadence: Literal["daily", "weekly", "monthly"]
    interval_count: int = Field(default=1, ge=1, le=52)
    timezone: str = Field(min_length=1, max_length=80)
    window_minutes: int = Field(default=120, ge=5, le=10080)
    effective_from: datetime
    effective_until: datetime | None = None


class ExemptionCreate(StrictModel):
    reason_code: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    reason: str = Field(min_length=2, max_length=1000)
    evidence_ref: str | None = Field(default=None, max_length=500)


class ExportCreate(StrictModel):
    format: Literal["csv", "xlsx", "json"]
    mission_id: UUID | None = None


class ExportDecision(StrictModel):
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=1000)


async def _allowed_locations(principal: Principal, permission: str) -> frozenset[str]:
    scope = require_field_permission(principal, permission)
    locations = await list_locations(str(principal.tenant_id), scope)
    return frozenset(str(item["location_id"]) for item in locations)


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/templates/{template_id}/{template_version}/retire")
async def post_retire_template(
    template_id: str,
    template_version: int,
    principal: FieldViewer,
) -> dict[str, object]:
    require_field_permission(principal, "action:field_intelligence:manageTemplates")
    try:
        return await retire_template_version(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            template_id=template_id,
            template_version=template_version,
        )
    except FieldGovernanceError as exc:
        raise _bad_request(exc) from exc


@router.get("/missions/{mission_id}/recurrence")
async def get_recurrence_rules(
    mission_id: UUID,
    principal: FieldViewer,
) -> dict[str, object]:
    allowed = await _allowed_locations(principal, "action:field_intelligence:manageRecurrence")
    try:
        items = await list_recurrence_rules(
            tenant_id=str(principal.tenant_id),
            mission_id=str(mission_id),
            allowed_location_ids=allowed,
        )
    except FieldGovernanceError as exc:
        raise _bad_request(exc) from exc
    return {"count": len(items), "items": items}


@router.post("/missions/{mission_id}/recurrence", status_code=status.HTTP_201_CREATED)
async def post_recurrence_rule(
    mission_id: UUID,
    payload: RecurrenceCreate,
    principal: FieldViewer,
) -> dict[str, object]:
    allowed = await _allowed_locations(principal, "action:field_intelligence:manageRecurrence")
    try:
        return await create_recurrence_rule(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            mission_id=str(mission_id),
            cadence=payload.cadence,
            interval_count=payload.interval_count,
            timezone_name=payload.timezone,
            window_minutes=payload.window_minutes,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            allowed_location_ids=allowed,
        )
    except FieldGovernanceError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "/missions/{mission_id}/targets/{location_id}/exempt", status_code=status.HTTP_201_CREATED
)
async def post_target_exemption(
    mission_id: UUID,
    location_id: str,
    payload: ExemptionCreate,
    principal: FieldViewer,
) -> dict[str, object]:
    allowed = await _allowed_locations(principal, "action:field_intelligence:exemptTarget")
    try:
        return await exempt_target(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            mission_id=str(mission_id),
            location_id=location_id,
            reason_code=payload.reason_code,
            reason=payload.reason,
            evidence_ref=payload.evidence_ref,
            allowed_location_ids=allowed,
        )
    except FieldGovernanceError as exc:
        raise _bad_request(exc) from exc


@router.get("/targeting/{criterion}")
async def get_governed_target_preview(
    criterion: Literal["field.overdue", "field.rework", "field.unseen"],
    principal: FieldViewer,
) -> dict[str, object]:
    allowed = await _allowed_locations(principal, "feature:field_intelligence:targeting")
    try:
        return await preview_server_targeting(
            tenant_id=str(principal.tenant_id),
            allowed_location_ids=allowed,
            criterion=criterion,
        )
    except FieldGovernanceError as exc:
        raise _bad_request(exc) from exc


@router.post("/exports", status_code=status.HTTP_201_CREATED)
async def post_export_request(
    payload: ExportCreate,
    principal: FieldViewer,
) -> dict[str, object]:
    allowed = await _allowed_locations(principal, "action:field_intelligence:exportResults")
    try:
        return await request_export(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            format_name=payload.format,
            mission_id=str(payload.mission_id) if payload.mission_id else None,
            allowed_location_ids=allowed,
        )
    except FieldGovernanceError as exc:
        raise _bad_request(exc) from exc


@router.post("/exports/{export_request_id}/decision")
async def post_export_decision(
    export_request_id: UUID,
    payload: ExportDecision,
    principal: FieldViewer,
) -> dict[str, object]:
    require_field_permission(principal, "action:field_intelligence:approveExport")
    try:
        return await decide_export(
            tenant_id=str(principal.tenant_id),
            actor_subject=principal.subject,
            export_request_id=str(export_request_id),
            decision=payload.decision,
            reason=payload.reason,
        )
    except FieldGovernanceError as exc:
        raise _bad_request(exc) from exc
