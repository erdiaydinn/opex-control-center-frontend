from __future__ import annotations

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
