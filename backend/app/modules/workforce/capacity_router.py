"""Canonical Workforce API surface for roadmap 12/60 effective capacity."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from . import persistence
from .authorization import is_action_allowed
from .capacity_authority import (
    CapacityWorker,
    EffectiveCapacityRequest,
    build_effective_capacity_snapshot,
)
from .capacity_repository import get_latest_capacity_snapshot, persist_capacity_snapshot
from .command_center_router import router as command_center_router
from .dpi_router import router as dpi_router
from .optimizer_router import router as optimizer_router
from .override_learning_router import router as override_learning_router
from .replan_router import router as replan_router
from .skill_capacity import SkillDemand
from .work_activity_capacity_runtime import build_scheduled_capacity_plan
from .work_activity_runtime import WorkActivityRuntimeError
from .work_activity_schemas import WorkActivityDemandPreviewRequest


router = APIRouter(prefix="/workforce", tags=["Workforce Capacity"])


class CapacityWorkerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str = Field(min_length=1, max_length=128)
    scheduled_hours: Decimal = Field(ge=0)
    absence_hours: Decimal = Field(default=Decimal("0"), ge=0)
    break_hours: Decimal = Field(default=Decimal("0"), ge=0)
    unavailable_hours: Decimal = Field(default=Decimal("0"), ge=0)
    skills: list[str] = Field(min_length=1)
    source_ref: str = Field(min_length=1, max_length=500)


class CapacitySnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str = Field(min_length=1, max_length=128)
    interval_start: datetime
    interval_minutes: int
    model_version: str = Field(min_length=1, max_length=128)
    workers: list[CapacityWorkerInput]
    source_refs: list[str] = Field(min_length=1)
    skill_demand: dict[str, Decimal] | None = None
    productivity_factor: Decimal = Field(default=Decimal("1"), gt=0, le=Decimal("1.5"))


def _require_any(role: str, permissions: str, *actions: str) -> None:
    if any(is_action_allowed(role, permissions, action) for action in actions):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Bu işlem için şu yetkilerden biri gerekir: {', '.join(actions)}.",
    )


def _canonical_location_in_scope(request: Request, role: str, location_id: str) -> str:
    # Reuse the existing Workforce warehouse/scope authority. This route does not
    # create a competing browser-owned location scope.
    from .router import _canonical_warehouse_id, _warehouse_scope

    canonical = _canonical_warehouse_id(location_id)
    if canonical is None:
        raise HTTPException(status_code=404, detail="Depo/lokasyon bulunamadı.")
    scope = _warehouse_scope(request, role)
    if scope is not None and canonical not in scope:
        raise HTTPException(status_code=403, detail="Lokasyon yetkili depo kapsamınızın dışında.")
    return canonical


@router.post("/capacity-snapshots")
def create_capacity_snapshot(
    payload: CapacitySnapshotCreate,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require_any(x_opex_role, x_opex_permissions, "workforce.model.manage")
    location_id = _canonical_location_in_scope(request, x_opex_role, payload.location_id)
    tenant_id = persistence.tenant_id()
    skill_demand = (
        SkillDemand(required_hours=dict(payload.skill_demand))
        if payload.skill_demand is not None
        else None
    )
    capacity_request = EffectiveCapacityRequest(
        tenant_id=tenant_id,
        location_id=location_id,
        interval_start=payload.interval_start,
        interval_minutes=payload.interval_minutes,
        model_version=payload.model_version,
        workers=tuple(
            CapacityWorker(
                employee_id=worker.employee_id,
                scheduled_hours=worker.scheduled_hours,
                absence_hours=worker.absence_hours,
                break_hours=worker.break_hours,
                unavailable_hours=worker.unavailable_hours,
                skills=frozenset(skill.strip() for skill in worker.skills if skill.strip()),
                source_ref=worker.source_ref,
            )
            for worker in payload.workers
        ),
        source_refs=tuple(payload.source_refs),
        skill_demand=skill_demand,
        productivity_factor=payload.productivity_factor,
    )
    snapshot = build_effective_capacity_snapshot(capacity_request)
    receipt = persist_capacity_snapshot(snapshot, actor_subject=x_opex_user)
    response = snapshot.as_record()
    response["id"] = receipt["id"]
    response["idempotent_replay"] = receipt["idempotent_replay"]
    # Numeric API convenience while preserving exact decimal components above.
    response["effective_capacity"] = float(snapshot.effective_capacity)
    response["scheduled_fte"] = float(snapshot.scheduled_fte)
    return response


@router.post("/activity-capacity-preview")
def activity_capacity_preview(
    payload: WorkActivityDemandPreviewRequest,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    """Compare governed demand with canonical scheduled capability capacity."""
    _require_any(x_opex_role, x_opex_permissions, "manageStaffingNorms")
    location_id = _canonical_location_in_scope(request, x_opex_role, payload.worksite_id)
    try:
        plan = build_scheduled_capacity_plan(
            worksite_id=location_id,
            interval_start=payload.interval_start,
            interval_minutes=payload.interval_minutes,
            model_version=payload.model_version,
            signals=[row.model_dump(mode="json") for row in payload.signals],
        )
    except WorkActivityRuntimeError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    response = plan.as_record()
    response["capacity_mode"] = "SCHEDULED_CAPABILITY"
    return response


@router.get("/depots/{location_id}/capacity/latest")
def latest_capacity_snapshot(
    location_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require_any(
        x_opex_role,
        x_opex_permissions,
        "workforce.pressure.read",
        "workforce.schedule.read",
    )
    canonical = _canonical_location_in_scope(request, x_opex_role, location_id)
    snapshot = get_latest_capacity_snapshot(canonical)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Capacity snapshot bulunamadı.")
    result = dict(snapshot)
    result["effective_capacity"] = float(snapshot["effective_capacity"])
    result["scheduled_fte"] = float(snapshot["scheduled_fte"])
    return result


router.include_router(command_center_router)
router.include_router(dpi_router)
router.include_router(optimizer_router)
router.include_router(replan_router)
router.include_router(override_learning_router)
