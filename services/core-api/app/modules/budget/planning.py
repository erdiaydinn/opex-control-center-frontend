from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .evidence import emit_financial_event
from .permissions import BudgetUnitOfWork
from .schemas import BudgetLineCreate, CostCenterCreate, ForecastCreate, PeriodCreate, PlanCreate


def _row(row) -> dict[str, object]:
    return dict(row._mapping)


async def create_plan(uow: BudgetUnitOfWork, body: PlanCreate) -> dict[str, object]:
    result = await uow.session.execute(text("""INSERT INTO budget_plan(tenant_id,name,fiscal_year,base_currency,created_by) VALUES (:tenant,:name,:year,:currency,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "name": body.name.strip(), "year": body.fiscal_year, "currency": body.base_currency, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="BUDGET_PLAN_CREATED", aggregate_type="budget_plan", aggregate_id=item["id"], payload=item)
    return item


async def activate_plan(uow: BudgetUnitOfWork, plan_id: UUID) -> dict[str, object]:
    plan_result = await uow.session.execute(text("SELECT * FROM budget_plan WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": plan_id})
    plan = plan_result.first()
    if plan is None or plan.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Budget Plan is not activatable")
    if plan.created_by == uow.actor:
        raise HTTPException(status_code=409, detail="Budget Plan activation requires a second actor")
    counts = await uow.session.execute(text("""SELECT (SELECT COUNT(*) FROM fiscal_period WHERE tenant_id=:tenant AND plan_id=:id) periods, (SELECT COUNT(*) FROM budget_line WHERE tenant_id=:tenant AND plan_id=:id) lines"""), {"tenant": uow.tenant_id, "id": plan_id})
    current = counts.one()
    if current.periods < 1 or current.lines < 1:
        raise HTTPException(status_code=409, detail="Plan requires period and Budget Line")
    result = await uow.session.execute(text("""UPDATE budget_plan SET status='ACTIVE',activated_by=:actor,activated_at=now() WHERE tenant_id=:tenant AND id=:id AND status='DRAFT' RETURNING *"""), {"tenant": uow.tenant_id, "id": plan_id, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="BUDGET_PLAN_ACTIVATED", aggregate_type="budget_plan", aggregate_id=item["id"], payload=item)
    return item


async def create_period(uow: BudgetUnitOfWork, body: PeriodCreate) -> dict[str, object]:
    await uow.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"budget-period:{uow.tenant_id}:{body.plan_id}"})
    plan = await uow.session.execute(text("SELECT status FROM budget_plan WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": body.plan_id})
    row = plan.first()
    if row is None or row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Period requires DRAFT plan")
    overlap = await uow.session.execute(text("""SELECT EXISTS(SELECT 1 FROM fiscal_period WHERE tenant_id=:tenant AND plan_id=:plan AND daterange(starts_on,ends_on,'[]') && daterange(:starts,:ends,'[]'))"""), {"tenant": uow.tenant_id, "plan": body.plan_id, "starts": body.starts_on, "ends": body.ends_on})
    if overlap.scalar_one():
        raise HTTPException(status_code=409, detail="Fiscal period overlaps an existing period")
    result = await uow.session.execute(text("""INSERT INTO fiscal_period(tenant_id,plan_id,code,starts_on,ends_on) VALUES (:tenant,:plan,:code,:starts,:ends) RETURNING *"""), {"tenant": uow.tenant_id, "plan": body.plan_id, "code": body.code.strip(), "starts": body.starts_on, "ends": body.ends_on})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="FISCAL_PERIOD_CREATED", aggregate_type="fiscal_period", aggregate_id=item["id"], payload=item)
    return item


async def create_cost_center(uow: BudgetUnitOfWork, body: CostCenterCreate) -> dict[str, object]:
    result = await uow.session.execute(text("""INSERT INTO cost_center(tenant_id,code,name,store_code,created_by) VALUES (:tenant,:code,:name,:store,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "code": body.code.strip().upper(), "name": body.name.strip(), "store": body.store_code, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="COST_CENTER_CREATED", aggregate_type="cost_center", aggregate_id=item["id"], cost_center_id=item["id"], payload=item)
    return item


async def create_line(uow: BudgetUnitOfWork, body: BudgetLineCreate) -> dict[str, object]:
    plan = await uow.session.execute(text("SELECT status FROM budget_plan WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": body.plan_id})
    row = plan.first()
    if row is None or row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Budget Line requires DRAFT plan")
    period = await uow.session.execute(text("SELECT 1 FROM fiscal_period WHERE tenant_id=:tenant AND id=:period AND plan_id=:plan"), {"tenant": uow.tenant_id, "period": body.fiscal_period_id, "plan": body.plan_id})
    if period.first() is None:
        raise HTTPException(status_code=409, detail="Budget Line period does not belong to plan")
    result = await uow.session.execute(text("""INSERT INTO budget_line(tenant_id,plan_id,fiscal_period_id,cost_center_id,category,supplier_id,supplier_name,store_code,budget_base_amount,created_by) VALUES (:tenant,:plan,:period,:center,:category,:supplier_id,:supplier_name,:store,:amount,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "plan": body.plan_id, "period": body.fiscal_period_id, "center": body.cost_center_id, "category": body.category.strip(), "supplier_id": body.supplier_id, "supplier_name": body.supplier_name, "store": body.store_code, "amount": body.budget_base_amount, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="BUDGET_LINE_CREATED", aggregate_type="budget_line", aggregate_id=item["id"], cost_center_id=item["cost_center_id"], payload=item)
    return item


async def create_forecast(uow: BudgetUnitOfWork, body: ForecastCreate) -> dict[str, object]:
    result = await uow.session.execute(text("""INSERT INTO forecast(tenant_id,budget_line_id,fiscal_period_id,cost_center_id,forecast_base_amount,as_of,created_by) VALUES (:tenant,:line,:period,:center,:amount,:as_of,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "line": body.budget_line_id, "period": body.fiscal_period_id, "center": body.cost_center_id, "amount": body.forecast_base_amount, "as_of": body.as_of, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="FORECAST_CREATED", aggregate_type="forecast", aggregate_id=item["id"], cost_center_id=item["cost_center_id"], payload=item)
    return item


async def close_period(uow: BudgetUnitOfWork, period_id: UUID) -> dict[str, object]:
    period = await uow.session.execute(text("SELECT * FROM fiscal_period WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": period_id})
    current = period.first()
    if current is None or current.status != "OPEN":
        raise HTTPException(status_code=409, detail="Fiscal period is not closable")
    blockers = await uow.session.execute(text("""SELECT (SELECT COUNT(*) FROM purchase_request r WHERE r.tenant_id=:tenant AND r.fiscal_period_id=:id AND r.status IN ('SUBMITTED','APPROVED')) + (SELECT COUNT(*) FROM purchase_order p WHERE p.tenant_id=:tenant AND p.fiscal_period_id=:id AND p.status='RECONCILIATION_HOLD') + (SELECT COUNT(*) FROM commitment c WHERE c.tenant_id=:tenant AND c.fiscal_period_id=:id AND c.status='OPEN' AND c.remaining_base_amount>0) + (SELECT COUNT(*) FROM invoice i WHERE i.tenant_id=:tenant AND i.fiscal_period_id=:id AND i.status='HOLD') + (SELECT COUNT(*) FROM reconciliation_issue x JOIN purchase_order p ON x.tenant_id=p.tenant_id AND x.entity_type='PURCHASE_ORDER' AND x.entity_id=p.id WHERE x.tenant_id=:tenant AND p.fiscal_period_id=:id AND x.status='OPEN') + (SELECT COUNT(*) FROM reconciliation_issue x JOIN invoice i ON x.tenant_id=i.tenant_id AND x.entity_type='INVOICE' AND x.entity_id=i.id WHERE x.tenant_id=:tenant AND i.fiscal_period_id=:id AND x.status='OPEN') AS count"""), {"tenant": uow.tenant_id, "id": period_id})
    if blockers.scalar_one() > 0:
        raise HTTPException(status_code=409, detail="Fiscal period has unresolved financial work")
    result = await uow.session.execute(text("""UPDATE fiscal_period SET status='CLOSED',closed_by=:actor,closed_at=now() WHERE tenant_id=:tenant AND id=:id AND status='OPEN' RETURNING *"""), {"tenant": uow.tenant_id, "id": period_id, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="FISCAL_PERIOD_CLOSED", aggregate_type="fiscal_period", aggregate_id=item["id"], payload=item)
    return item
