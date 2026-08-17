"""Canonical API for roadmap 16/60 manager override learning evidence."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .authorization import is_action_allowed
from .override_learning_repository import (
    get_learning_summary,
    record_manager_override,
    record_override_outcome,
)


router = APIRouter(tags=["Workforce Override Learning"])


class ManagerOverrideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str = Field(min_length=1, max_length=128)
    optimizer_proposal_fingerprint: str = Field(min_length=64, max_length=64)
    decision: str
    reason_code: str = Field(min_length=1, max_length=128)
    reason_note: str | None = Field(default=None, max_length=1000)
    observed_action_type: str = Field(min_length=1, max_length=128)


class OverrideOutcomeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worked: bool
    post_kpi_context_ref: str = Field(min_length=1, max_length=500)
    kpi_deltas: dict[str, Decimal]
    source_ref: str = Field(min_length=1, max_length=500)


def _require(role: str, permissions: str, action: str) -> None:
    if is_action_allowed(role, permissions, action):
        return
    raise HTTPException(status_code=403, detail=f"{action} yetkisi gerekir.")


def _canonical_location_in_scope(request: Request, role: str, location_id: str) -> str:
    from .router import _canonical_warehouse_id, _warehouse_scope

    canonical = _canonical_warehouse_id(location_id)
    if canonical is None:
        raise HTTPException(status_code=404, detail="Depo/lokasyon bulunamadı.")
    scope = _warehouse_scope(request, role)
    if scope is not None and canonical not in scope:
        raise HTTPException(status_code=403, detail="Lokasyon yetkili depo kapsamınızın dışında.")
    return canonical


@router.post("/optimizer-overrides")
def create_manager_override(
    payload: ManagerOverrideCreate,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require(x_opex_role, x_opex_permissions, "workforce.schedule.override")
    location_id = _canonical_location_in_scope(request, x_opex_role, payload.location_id)
    return record_manager_override(
        location_id=location_id,
        optimizer_proposal_fingerprint=payload.optimizer_proposal_fingerprint,
        decision=payload.decision,
        reason_code=payload.reason_code,
        reason_note=payload.reason_note,
        observed_action_type=payload.observed_action_type,
        actor_subject=x_opex_user,
    )


@router.post("/optimizer-overrides/{override_id}/outcome")
def create_override_outcome(
    override_id: str,
    payload: OverrideOutcomeCreate,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require(x_opex_role, x_opex_permissions, "workforce.schedule.override")
    return record_override_outcome(
        override_id=override_id,
        worked=payload.worked,
        post_kpi_context_ref=payload.post_kpi_context_ref,
        kpi_deltas=dict(payload.kpi_deltas),
        source_ref=payload.source_ref,
        actor_subject=x_opex_user,
    )


@router.get("/learning")
def learning_summary(
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require(x_opex_role, x_opex_permissions, "workforce.pressure.read")
    return get_learning_summary()
