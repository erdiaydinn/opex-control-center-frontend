from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from .commands import run_command
from .permissions import (
    BUDGET_ACTIVATE_PLAN,
    BUDGET_MANAGE_LINES,
    BUDGET_VIEW,
    BudgetUnitOfWork,
    require_budget,
)
from .planning_engine import (
    add_allocation_rule,
    add_assumption,
    add_driver_line,
    create_scenario,
    get_activation_snapshot,
    list_scenarios,
    publish_scenario,
)
from .planning_engine_schemas import (
    PlanningAllocationCreate,
    PlanningAssumptionCreate,
    PlanningDriverLineCreate,
    PlanningScenarioCreate,
)

router = APIRouter(prefix="/v1/budget/planning", tags=["budget-planning"])
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=160),
]
ViewSession = Annotated[
    BudgetUnitOfWork,
    Depends(require_budget(BUDGET_VIEW, all_cost_centers=True)),
]
ManageSession = Annotated[
    BudgetUnitOfWork,
    Depends(require_budget(BUDGET_MANAGE_LINES, all_cost_centers=True)),
]
PublishSession = Annotated[
    BudgetUnitOfWork,
    Depends(require_budget(BUDGET_ACTIVATE_PLAN, all_cost_centers=True)),
]


@router.post("/scenarios", status_code=201)
async def post_scenario(
    body: PlanningScenarioCreate,
    key: IdempotencyKey,
    uow: ManageSession,
):
    return await run_command(
        uow,
        key=key,
        operation="budget.planning.scenario.create",
        payload=body,
        perform=lambda: create_scenario(uow, body),
    )


@router.post("/scenarios/{scenario_id}/assumptions", status_code=201)
async def post_assumption(
    scenario_id: UUID,
    body: PlanningAssumptionCreate,
    key: IdempotencyKey,
    uow: ManageSession,
):
    return await run_command(
        uow,
        key=key,
        operation="budget.planning.assumption.create",
        payload={"scenario_id": scenario_id, "body": body},
        perform=lambda: add_assumption(uow, scenario_id, body),
    )


@router.post("/scenarios/{scenario_id}/driver-lines", status_code=201)
async def post_driver_line(
    scenario_id: UUID,
    body: PlanningDriverLineCreate,
    key: IdempotencyKey,
    uow: ManageSession,
):
    return await run_command(
        uow,
        key=key,
        operation="budget.planning.driver_line.create",
        payload={"scenario_id": scenario_id, "body": body},
        perform=lambda: add_driver_line(uow, scenario_id, body),
    )


@router.post("/scenarios/{scenario_id}/allocations", status_code=201)
async def post_allocation(
    scenario_id: UUID,
    body: PlanningAllocationCreate,
    key: IdempotencyKey,
    uow: ManageSession,
):
    return await run_command(
        uow,
        key=key,
        operation="budget.planning.allocation.create",
        payload={"scenario_id": scenario_id, "body": body},
        perform=lambda: add_allocation_rule(uow, scenario_id, body),
    )


@router.post("/scenarios/{scenario_id}/publish")
async def post_publish_scenario(
    scenario_id: UUID,
    key: IdempotencyKey,
    uow: PublishSession,
):
    return await run_command(
        uow,
        key=key,
        operation="budget.planning.scenario.publish",
        payload={"scenario_id": scenario_id},
        perform=lambda: publish_scenario(uow, scenario_id),
    )


@router.get("/plans/{plan_id}/snapshot")
async def get_plan_snapshot(plan_id: UUID, uow: ViewSession):
    return await get_activation_snapshot(uow, plan_id)


@router.get("/plans/{plan_id}/scenarios")
async def get_plan_scenarios(plan_id: UUID, uow: ViewSession):
    items = await list_scenarios(uow, plan_id)
    return {"count": len(items), "items": items}
