from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .permissions import BudgetUnitOfWork


def _row(row) -> dict[str, object]:
    return dict(row._mapping)


async def variance_summary(uow: BudgetUnitOfWork) -> dict[str, object]:
    result = await uow.session.execute(
        text("""SELECT l.id budget_line_id,c.code cost_center,l.category,l.supplier_id,l.supplier_name,
          l.store_code,l.budget_base_amount,COALESCE(a.amount,0) actual_base_amount,
          COALESCE(cm.amount,0) committed_base_amount,
          COALESCE(f.amount,COALESCE(a.amount,0)+COALESCE(cm.amount,0)) forecast_base_amount,
          l.budget_base_amount-COALESCE(f.amount,COALESCE(a.amount,0)+COALESCE(cm.amount,0)) variance_base_amount
          FROM budget_line l JOIN cost_center c ON c.tenant_id=l.tenant_id AND c.id=l.cost_center_id
          LEFT JOIN LATERAL (SELECT SUM(base_amount) amount FROM actual x
            WHERE x.tenant_id=l.tenant_id AND x.budget_line_id=l.id) a ON true
          LEFT JOIN LATERAL (SELECT SUM(remaining_base_amount) amount FROM commitment x
            WHERE x.tenant_id=l.tenant_id AND x.budget_line_id=l.id AND x.status='OPEN') cm ON true
          LEFT JOIN LATERAL (SELECT forecast_base_amount amount FROM forecast x
            WHERE x.tenant_id=l.tenant_id AND x.budget_line_id=l.id
            ORDER BY as_of DESC,created_at DESC LIMIT 1) f ON true
          WHERE l.tenant_id=:tenant ORDER BY c.code,l.category,l.id"""),
        {"tenant": uow.tenant_id},
    )
    items = [_row(row) for row in result]
    return {"tenant_id": str(uow.tenant_id), "count": len(items), "items": items}


async def financial_events(uow: BudgetUnitOfWork, limit: int) -> dict[str, object]:
    result = await uow.session.execute(
        text("""SELECT id,cost_center_id,chain_seq,event_type,aggregate_type,aggregate_id,
          actor_id,payload,prev_hash,event_hash,created_at FROM financial_event
          WHERE tenant_id=:tenant ORDER BY created_at DESC,chain_seq DESC LIMIT :limit"""),
        {"tenant": uow.tenant_id, "limit": max(1, min(limit, 500))},
    )
    items = [_row(row) for row in result]
    return {"count": len(items), "items": items}


async def plan_snapshot(
    uow: BudgetUnitOfWork,
    plan_id: UUID | None,
) -> dict[str, object]:
    """Return the all-cost-center Budget planning read model.

    This is intentionally the single reviewed SQL execution point for Master 28
    planning reads. Routes cannot bypass the all-cost-center dependency and no
    browser-authored tenant/cost-center selector participates in these queries.
    """

    if plan_id is None:
        plans_result = await uow.session.execute(
            text(
                """SELECT id,name,fiscal_year,base_currency,status,created_by,activated_by,
                          created_at,activated_at,planning_fingerprint,
                          planning_snapshot_at,planning_snapshot_provenance,
                          (planning_snapshot_provenance='ACTIVATION_TRIGGER')
                            AS activation_snapshot_attested
                   FROM budget_plan
                   WHERE tenant_id=:tenant
                   ORDER BY fiscal_year DESC,name,id"""
            ),
            {"tenant": uow.tenant_id},
        )
        centers_result = await uow.session.execute(
            text(
                """SELECT id,code,name,store_code,created_by,created_at
                   FROM cost_center
                   WHERE tenant_id=:tenant
                   ORDER BY code,id"""
            ),
            {"tenant": uow.tenant_id},
        )
        plans = [_row(row) for row in plans_result]
        centers = [_row(row) for row in centers_result]
        return {
            "tenant_id": str(uow.tenant_id),
            "plans": plans,
            "cost_centers": centers,
        }

    plan_result = await uow.session.execute(
        text(
            """SELECT id,name,fiscal_year,base_currency,status,created_by,activated_by,
                      created_at,activated_at,planning_snapshot,planning_fingerprint,
                      planning_snapshot_at,planning_snapshot_provenance,
                      (planning_snapshot_provenance='ACTIVATION_TRIGGER')
                        AS activation_snapshot_attested
               FROM budget_plan
               WHERE tenant_id=:tenant AND id=:plan"""
        ),
        {"tenant": uow.tenant_id, "plan": plan_id},
    )
    row = plan_result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Budget Plan not found")
    plan = _row(row)

    periods_result = await uow.session.execute(
        text(
            """SELECT id,code,starts_on,ends_on,status,closed_by,closed_at,created_at
               FROM fiscal_period
               WHERE tenant_id=:tenant AND plan_id=:plan
               ORDER BY starts_on,ends_on,code,id"""
        ),
        {"tenant": uow.tenant_id, "plan": plan_id},
    )
    periods = [_row(item) for item in periods_result]

    lines_result = await uow.session.execute(
        text(
            """SELECT l.id,l.plan_id,l.fiscal_period_id,l.cost_center_id,
                      p.code fiscal_period_code,c.code cost_center_code,
                      c.name cost_center_name,c.store_code cost_center_store_code,
                      l.category,l.supplier_id,l.supplier_name,l.store_code,
                      l.budget_base_amount,l.created_by,l.created_at,
                      f.forecast_base_amount latest_forecast_base_amount,
                      f.as_of latest_forecast_as_of
               FROM budget_line l
               JOIN fiscal_period p
                 ON p.tenant_id=l.tenant_id
                AND p.id=l.fiscal_period_id
                AND p.plan_id=l.plan_id
               JOIN cost_center c
                 ON c.tenant_id=l.tenant_id AND c.id=l.cost_center_id
               LEFT JOIN LATERAL (
                 SELECT forecast_base_amount,as_of
                 FROM forecast x
                 WHERE x.tenant_id=l.tenant_id
                   AND x.budget_line_id=l.id
                   AND x.fiscal_period_id=l.fiscal_period_id
                   AND x.cost_center_id=l.cost_center_id
                 ORDER BY x.as_of DESC,x.created_at DESC,x.id DESC
                 LIMIT 1
               ) f ON true
               WHERE l.tenant_id=:tenant AND l.plan_id=:plan
               ORDER BY p.starts_on,c.code,l.category,l.id"""
        ),
        {"tenant": uow.tenant_id, "plan": plan_id},
    )
    lines = [_row(item) for item in lines_result]
    return {
        "tenant_id": str(uow.tenant_id),
        "plan": plan,
        "periods": periods,
        "lines": lines,
    }


async def planning_catalog(uow: BudgetUnitOfWork) -> dict[str, object]:
    return await plan_snapshot(uow, None)


async def planning_workspace(uow: BudgetUnitOfWork, plan_id: UUID) -> dict[str, object]:
    return await plan_snapshot(uow, plan_id)
