from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import resolve_permission_scope
from app.core.security import Principal, get_current_principal
from app.db.session import TenantSessionFactory, apply_tenant_context

BUDGET_VIEW = "module:budget:view"
BUDGET_CREATE_PLAN = "action:budget:createPlan"
BUDGET_ACTIVATE_PLAN = "action:budget:activatePlan"
BUDGET_MANAGE_PERIODS = "action:budget:managePeriods"
BUDGET_MANAGE_COST_CENTERS = "action:budget:manageCostCenters"
BUDGET_MANAGE_LINES = "action:budget:manageBudgetLines"
BUDGET_CREATE_REQUEST = "action:budget:createRequest"
BUDGET_APPROVE_REQUEST = "action:budget:approveRequest"
BUDGET_CREATE_PO = "action:budget:createPO"
BUDGET_POST_INVOICE = "action:budget:postInvoice"
BUDGET_CREATE_FORECAST = "action:budget:createForecast"
BUDGET_IMPORT = "action:budget:import"
BUDGET_RECONCILE = "action:budget:resolveReconciliation"
BUDGET_CLOSE_PERIOD = "action:budget:closePeriod"
BUDGET_EXPORT = "action:budget:export"
BUDGET_VIEW_AUDIT = "action:budget:viewAudit"


@dataclass(frozen=True)
class BudgetScope:
    all_cost_centers: bool
    cost_center_ids: frozenset[UUID]


@dataclass
class BudgetUnitOfWork:
    principal: Principal
    scope: BudgetScope
    session: AsyncSession

    @property
    def actor(self) -> str:
        return self.principal.subject

    @property
    def tenant_id(self) -> UUID:
        return self.principal.tenant_id


def _resolve_scope(principal: Principal, permission: str) -> BudgetScope:
    authority = resolve_permission_scope(principal, permission)
    centers: set[UUID] = set()
    for raw in authority.values("cost_center_ids") | authority.values("cost_centers"):
        try:
            centers.add(UUID(raw))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Invalid Budget cost-center authority") from exc

    scope = BudgetScope(authority.unrestricted, frozenset(centers))
    if not scope.all_cost_centers and not scope.cost_center_ids:
        raise HTTPException(status_code=403, detail="Budget cost-center scope required")
    return scope


def require_budget(permission: str, *, all_cost_centers: bool = False):
    async def dependency(principal: Annotated[Principal, Depends(get_current_principal)]):
        scope = _resolve_scope(principal, permission)
        if all_cost_centers and not scope.all_cost_centers:
            raise HTTPException(status_code=403, detail="All-cost-center Budget scope required")
        encoded_scope = "__all__" if scope.all_cost_centers else ",".join(sorted(str(item) for item in scope.cost_center_ids))
        async with TenantSessionFactory() as session, session.begin():
            await apply_tenant_context(session, principal)
            await session.execute(text("SELECT set_config('app.budget_cost_center_ids', :scope, true)"), {"scope": encoded_scope})
            yield BudgetUnitOfWork(principal=principal, scope=scope, session=session)
    return dependency
