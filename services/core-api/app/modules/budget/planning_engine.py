from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .evidence import emit_financial_event
from .permissions import BudgetUnitOfWork
from .planning_engine_schemas import (
    PlanningAllocationCreate,
    PlanningAssumptionCreate,
    PlanningDriverLineCreate,
    PlanningScenarioCreate,
)


def _row(row) -> dict[str, object]:
    return dict(row._mapping)


async def create_scenario(
    uow: BudgetUnitOfWork,
    body: PlanningScenarioCreate,
) -> dict[str, object]:
    plan = await uow.session.execute(
        text("SELECT id FROM budget_plan WHERE tenant_id=:tenant AND id=:plan"),
        {"tenant": uow.tenant_id, "plan": body.plan_id},
    )
    if plan.first() is None:
        raise HTTPException(status_code=404, detail="Budget plan not found")
    if body.parent_scenario_id is not None:
        parent = await uow.session.execute(
            text(
                "SELECT id FROM budget_scenario WHERE tenant_id=:tenant "
                "AND id=:parent AND plan_id=:plan AND status='PUBLISHED'"
            ),
            {
                "tenant": uow.tenant_id,
                "parent": body.parent_scenario_id,
                "plan": body.plan_id,
            },
        )
        if parent.first() is None:
            raise HTTPException(
                status_code=409,
                detail="Parent scenario must be published and belong to the same plan",
            )
    result = await uow.session.execute(
        text(
            """INSERT INTO budget_scenario(
                tenant_id,plan_id,parent_scenario_id,name,scenario_type,
                version,as_of,created_by
            ) VALUES(
                :tenant,:plan,:parent,:name,:type,:version,:as_of,:actor
            ) RETURNING *"""
        ),
        {
            "tenant": uow.tenant_id,
            "plan": body.plan_id,
            "parent": body.parent_scenario_id,
            "name": body.name.strip(),
            "type": body.scenario_type,
            "version": body.version,
            "as_of": body.as_of,
            "actor": uow.actor,
        },
    )
    item = _row(result.one())
    await emit_financial_event(
        uow,
        event_type="BUDGET_SCENARIO_CREATED",
        aggregate_type="budget_scenario",
        aggregate_id=item["id"],
        payload={
            "scenario_type": item["scenario_type"],
            "version": item["version"],
        },
    )
    return item


async def add_assumption(
    uow: BudgetUnitOfWork,
    scenario_id: UUID,
    body: PlanningAssumptionCreate,
) -> dict[str, object]:
    result = await uow.session.execute(
        text(
            """INSERT INTO budget_scenario_assumption(
                tenant_id,scenario_id,assumption_key,assumption_value,unit,
                source,effective_on,created_by
            ) SELECT
                :tenant,s.id,:key,CAST(:value AS jsonb),:unit,:source,
                :effective_on,:actor
            FROM budget_scenario s
            WHERE s.tenant_id=:tenant AND s.id=:scenario AND s.status='DRAFT'
            RETURNING *"""
        ),
        {
            "tenant": uow.tenant_id,
            "scenario": scenario_id,
            "key": body.assumption_key.strip(),
            "value": json.dumps(body.assumption_value),
            "unit": body.unit,
            "source": body.source.strip(),
            "effective_on": body.effective_on,
            "actor": uow.actor,
        },
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="Assumption requires DRAFT scenario",
        )
    return _row(row)


async def add_driver_line(
    uow: BudgetUnitOfWork,
    scenario_id: UUID,
    body: PlanningDriverLineCreate,
) -> dict[str, object]:
    amount = (Decimal(body.quantity) * Decimal(body.rate)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    result = await uow.session.execute(
        text(
            """INSERT INTO budget_scenario_line(
                tenant_id,scenario_id,budget_line_id,fiscal_period_id,
                cost_center_id,driver_key,quantity,rate,calculated_base_amount,
                unit,formula,provenance,created_by
            ) SELECT
                :tenant,s.id,l.id,l.fiscal_period_id,l.cost_center_id,:driver,
                :quantity,:rate,:amount,:unit,'quantity * rate',
                CAST(:provenance AS jsonb),:actor
            FROM budget_scenario s
            JOIN budget_line l
              ON l.tenant_id=s.tenant_id AND l.plan_id=s.plan_id
             AND l.id=:line AND l.fiscal_period_id=:period
             AND l.cost_center_id=:center
            WHERE s.tenant_id=:tenant AND s.id=:scenario AND s.status='DRAFT'
            RETURNING *"""
        ),
        {
            "tenant": uow.tenant_id,
            "scenario": scenario_id,
            "line": body.budget_line_id,
            "period": body.fiscal_period_id,
            "center": body.cost_center_id,
            "driver": body.driver_key.strip(),
            "quantity": body.quantity,
            "rate": body.rate,
            "amount": amount,
            "unit": body.unit,
            "provenance": json.dumps(body.provenance, sort_keys=True),
            "actor": uow.actor,
        },
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="Driver line requires DRAFT scenario and exact Budget scope",
        )
    return _row(row)


async def add_allocation_rule(
    uow: BudgetUnitOfWork,
    scenario_id: UUID,
    body: PlanningAllocationCreate,
) -> dict[str, object]:
    result = await uow.session.execute(
        text(
            """INSERT INTO budget_allocation_rule(
                tenant_id,scenario_id,source_budget_line_id,target_budget_line_id,
                target_fiscal_period_id,target_cost_center_id,weight,basis,
                provenance,created_by
            ) SELECT
                :tenant,s.id,source.id,target.id,target.fiscal_period_id,
                target.cost_center_id,:weight,:basis,CAST(:provenance AS jsonb),:actor
            FROM budget_scenario s
            JOIN budget_line source
              ON source.tenant_id=s.tenant_id AND source.plan_id=s.plan_id
             AND source.id=:source
            JOIN budget_line target
              ON target.tenant_id=s.tenant_id AND target.plan_id=s.plan_id
             AND target.id=:target AND target.fiscal_period_id=:period
             AND target.cost_center_id=:center
            WHERE s.tenant_id=:tenant AND s.id=:scenario AND s.status='DRAFT'
            RETURNING *"""
        ),
        {
            "tenant": uow.tenant_id,
            "scenario": scenario_id,
            "source": body.source_budget_line_id,
            "target": body.target_budget_line_id,
            "period": body.target_fiscal_period_id,
            "center": body.target_cost_center_id,
            "weight": body.weight,
            "basis": body.basis.strip(),
            "provenance": json.dumps(body.provenance, sort_keys=True),
            "actor": uow.actor,
        },
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="Allocation requires DRAFT scenario and exact source/target scope",
        )
    return _row(row)


async def publish_scenario(
    uow: BudgetUnitOfWork,
    scenario_id: UUID,
) -> dict[str, object]:
    current = await uow.session.execute(
        text(
            "SELECT * FROM budget_scenario WHERE tenant_id=:tenant "
            "AND id=:scenario FOR UPDATE"
        ),
        {"tenant": uow.tenant_id, "scenario": scenario_id},
    )
    row = current.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Budget scenario not found")
    if row.status != "DRAFT" or row.created_by == uow.actor:
        raise HTTPException(
            status_code=409,
            detail="Scenario publication requires DRAFT state and independent actor",
        )
    counts = await uow.session.execute(
        text(
            """SELECT
                (SELECT COUNT(*) FROM budget_scenario_assumption
                 WHERE tenant_id=:tenant AND scenario_id=:scenario) assumptions,
                (SELECT COUNT(*) FROM budget_scenario_line
                 WHERE tenant_id=:tenant AND scenario_id=:scenario) lines"""
        ),
        {"tenant": uow.tenant_id, "scenario": scenario_id},
    )
    c = counts.one()
    if c.assumptions < 1 or c.lines < 1:
        raise HTTPException(
            status_code=409,
            detail="Scenario requires assumption and driver line",
        )
    result = await uow.session.execute(
        text(
            "UPDATE budget_scenario SET status='PUBLISHED',published_by=:actor "
            "WHERE tenant_id=:tenant AND id=:scenario AND status='DRAFT' RETURNING *"
        ),
        {"tenant": uow.tenant_id, "scenario": scenario_id, "actor": uow.actor},
    )
    item = _row(result.one())
    await emit_financial_event(
        uow,
        event_type="BUDGET_SCENARIO_PUBLISHED",
        aggregate_type="budget_scenario",
        aggregate_id=item["id"],
        payload={
            "fingerprint_sha256": item["fingerprint_sha256"],
            "scenario_type": item["scenario_type"],
            "version": item["version"],
        },
    )
    return item


async def get_activation_snapshot(
    uow: BudgetUnitOfWork,
    plan_id: UUID,
) -> dict[str, object]:
    result = await uow.session.execute(
        text(
            "SELECT s.*,p.status AS plan_status,p.activation_snapshot_sha256 "
            "FROM budget_plan_snapshot s JOIN budget_plan p "
            "ON p.tenant_id=s.tenant_id AND p.id=s.plan_id "
            "WHERE s.tenant_id=:tenant AND s.plan_id=:plan"
        ),
        {"tenant": uow.tenant_id, "plan": plan_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Budget activation snapshot not found",
        )
    return _row(row)


async def list_scenarios(
    uow: BudgetUnitOfWork,
    plan_id: UUID,
) -> list[dict[str, object]]:
    result = await uow.session.execute(
        text(
            "SELECT * FROM budget_scenario WHERE tenant_id=:tenant "
            "AND plan_id=:plan ORDER BY name,version,id"
        ),
        {"tenant": uow.tenant_id, "plan": plan_id},
    )
    return [_row(row) for row in result.fetchall()]
