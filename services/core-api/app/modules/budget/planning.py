from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .permissions import BudgetUnitOfWork
from .schemas import BudgetLineCreate, CostCenterCreate, ForecastCreate, PeriodCreate, PlanCreate


def _row(row) -> dict[str, object]:
    return dict(row._mapping)


async def create_plan(uow: BudgetUnitOfWork, body: PlanCreate) -> dict[str, object]:
    result = await uow.session.execute(
        text("""INSERT INTO budget_plan(tenant_id,name,fiscal_year,base_currency,created_by)
                VALUES (:tenant,:name,:year,:currency,:actor) RETURNING *"""),
        {"tenant": uow.tenant_id, "name": body.name.strip(), "year": body.fiscal_year,
         "currency": body.base_currency, "actor": uow.actor},
    )
    return _row(result.one())


async def activate_plan(uow: BudgetUnitOfWork, plan_id: UUID) -> dict[str, object]:
    counts = await uow.session.execute(
        text("""SELECT
          (SELECT COUNT(*) FROM fiscal_period WHERE tenant_id=:tenant AND plan_id=:id) periods,
          (SELECT COUNT(*) FROM budget_line WHERE tenant_id=:tenant AND plan_id=:id) lines"""),
        {"tenant": uow.tenant_id, "id": plan_id},
    )
    current = counts.one()
    if current.periods < 1 or current.lines < 1:
        raise HTTPException(status_code=409, detail="Plan requires period and Budget Line")
    result = await uow.session.execute(
        text("""UPDATE budget_plan SET status='ACTIVE',activated_by=:actor,activated_at=now()
                 WHERE tenant_id=:tenant AND id=:id AND status='DRAFT' RETURNING *"""),
        {"tenant": uow.tenant_id, "id": plan_id, "actor": uow.actor},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=409, detail="Budget Plan is not activatable")
    return _row(row)


async def create_period(uow: BudgetUnitOfWork, body: PeriodCreate) -> dict[str, object]:
    plan = await uow.session.execute(
        text("SELECT status FROM budget_plan WHERE tenant_id=:tenant AND id=:id FOR UPDATE"),
        {"tenant": uow.tenant_id, "id": body.plan_id},
    )
    row = plan.first()
    if row is None or row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Period requires DRAFT plan")
    result = await uow.session.execute(
        text("""INSERT INTO fiscal_period(tenant_id,plan_id,code,starts_on,ends_on)
                VALUES (:tenant,:plan,:code,:starts,:ends) RETURNING *"""),
        {"tenant": uow.tenant_id, "plan": body.plan_id, "code": body.code.strip(),
         "starts": body.starts_on, "ends": body.ends_on},
    )
    return _row(result.one())


async def create_cost_center(uow: BudgetUnitOfWork, body: CostCenterCreate) -> dict[str, object]:
    result = await uow.session.execute(
        text("""INSERT INTO cost_center(tenant_id,code,name,store_code,created_by)
                VALUES (:tenant,:code,:name,:store,:actor) RETURNING *"""),
        {"tenant": uow.tenant_id, "code": body.code.strip().upper(), "name": body.name.strip(),
         "store": body.store_code, "actor": uow.actor},
    )
    return _row(result.one())


async def create_line(uow: BudgetUnitOfWork, body: BudgetLineCreate) -> dict[str, object]:
    plan = await uow.session.execute(
        text("SELECT status FROM budget_plan WHERE tenant_id=:tenant AND id=:id FOR UPDATE"),
        {"tenant": uow.tenant_id, "id": body.plan_id},
    )
    row = plan.first()
    if row is None or row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Budget Line requires DRAFT plan")
    result = await uow.session.execute(
        text("""INSERT INTO budget_line(
          tenant_id,plan_id,fiscal_period_id,cost_center_id,category,supplier_id,supplier_name,
          store_code,budget_base_amount,created_by)
          VALUES (:tenant,:plan,:period,:center,:category,:supplier_id,:supplier_name,:store,:amount,:actor)
          RETURNING *"""),
        {"tenant": uow.tenant_id, "plan": body.plan_id, "period": body.fiscal_period_id,
         "center": body.cost_center_id, "category": body.category.strip(), "supplier_id": body.supplier_id,
         "supplier_name": body.supplier_name, "store": body.store_code,
         "amount": body.budget_base_amount, "actor": uow.actor},
    )
    return _row(result.one())


async def create_forecast(uow: BudgetUnitOfWork, body: ForecastCreate) -> dict[str, object]:
    result = await uow.session.execute(
        text("""INSERT INTO forecast(tenant_id,budget_line_id,fiscal_period_id,cost_center_id,
                 forecast_base_amount,as_of,created_by)
                 VALUES (:tenant,:line,:period,:center,:amount,:as_of,:actor) RETURNING *"""),
        {"tenant": uow.tenant_id, "line": body.budget_line_id, "period": body.fiscal_period_id,
         "center": body.cost_center_id, "amount": body.forecast_base_amount,
         "as_of": body.as_of, "actor": uow.actor},
    )
    return _row(result.one())


async def close_period(uow: BudgetUnitOfWork, period_id: UUID) -> dict[str, object]:
    result = await uow.session.execute(
        text("""UPDATE fiscal_period SET status='CLOSED',closed_by=:actor,closed_at=now()
                 WHERE tenant_id=:tenant AND id=:id AND status='OPEN' RETURNING *"""),
        {"tenant": uow.tenant_id, "id": period_id, "actor": uow.actor},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=409, detail="Fiscal period is not closable")
    return _row(row)
