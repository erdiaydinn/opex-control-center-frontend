"""Canonical what-if API for roadmap 15/60.

Callers may submit hypothetical shocks only. Tenant, baseline truth, KPI
sensitivities, cost rates and execution authority remain server-side.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .authorization import is_action_allowed
from .replan_authority import ScenarioShock
from .replan_repository import get_latest_replan_scenario
from .replan_service import compute_and_persist_replan_scenario


router = APIRouter(tags=["Workforce Replan"])


class ScenarioShockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shock_id: str = Field(min_length=1, max_length=128)
    shock_type: str
    demand_delta_man_hours: Decimal = Field(default=Decimal("0"), ge=0)
    capacity_loss_man_hours: Decimal = Field(default=Decimal("0"), ge=0)
    source_ref: str = Field(min_length=1, max_length=500)


class ReplanScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    shocks: list[ScenarioShockInput] = Field(min_length=1, max_length=12)


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


@router.post("/scenarios")
def create_replan_scenario(
    payload: ReplanScenarioCreate,
    request: Request,
    x_opex_user: str = Header(default="unknown", alias="X-OPEX-User"),
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require(x_opex_role, x_opex_permissions, "workforce.schedule.propose")
    location_id = _canonical_location_in_scope(request, x_opex_role, payload.location_id)
    shocks = tuple(
        ScenarioShock(
            shock_id=item.shock_id,
            shock_type=item.shock_type,
            demand_delta_man_hours=item.demand_delta_man_hours,
            capacity_loss_man_hours=item.capacity_loss_man_hours,
            source_ref=item.source_ref,
        )
        for item in payload.shocks
    )
    scenario, receipt = compute_and_persist_replan_scenario(
        location_id=location_id,
        model_version=payload.model_version,
        shocks=shocks,
        actor_subject=x_opex_user,
    )
    result = scenario.as_record()
    result.update(receipt)
    result["baseline_required_man_hours"] = float(scenario.baseline_required_man_hours)
    result["baseline_effective_man_hours"] = float(scenario.baseline_effective_man_hours)
    result["scenario_required_man_hours"] = float(scenario.scenario_required_man_hours)
    result["scenario_effective_man_hours"] = float(scenario.scenario_effective_man_hours)
    result["scenario_gap_man_hours"] = float(scenario.scenario_gap_man_hours)
    result["dpi_delta"] = float(scenario.dpi_delta)
    result["predicted_kpi_deltas"] = {
        key: float(value) for key, value in scenario.predicted_kpi_deltas.items()
    }
    return result


@router.get("/depots/{location_id}/scenarios/latest")
def latest_replan_scenario(
    location_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require(x_opex_role, x_opex_permissions, "workforce.schedule.read")
    canonical = _canonical_location_in_scope(request, x_opex_role, location_id)
    scenario = get_latest_replan_scenario(canonical)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Replan scenario bulunamadı.")
    result = dict(scenario)
    for key in (
        "baseline_required_man_hours",
        "baseline_effective_man_hours",
        "scenario_required_man_hours",
        "scenario_effective_man_hours",
        "baseline_gap_man_hours",
        "scenario_gap_man_hours",
        "gap_delta_man_hours",
        "baseline_dpi",
        "scenario_dpi",
        "dpi_delta",
    ):
        result[key] = float(scenario[key])
    return result
