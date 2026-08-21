from __future__ import annotations

from fastapi import HTTPException

from app.core.security import normalize_principal_roles

from .permissions import BudgetUnitOfWork

FINANCE_ADMIN_ROLES = frozenset({"super_admin", "platform_admin"})
FINANCE_OPERATOR_ROLES = frozenset({"super_admin", "platform_admin", "operator"})


def require_finance_admin(uow: BudgetUnitOfWork) -> None:
    if normalize_principal_roles(uow.principal).isdisjoint(FINANCE_ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="Finance administrator role required")


def require_finance_operator(uow: BudgetUnitOfWork) -> None:
    if normalize_principal_roles(uow.principal).isdisjoint(FINANCE_OPERATOR_ROLES):
        raise HTTPException(status_code=403, detail="Finance operator role required")


def require_all_cost_centers(uow: BudgetUnitOfWork) -> None:
    if not uow.scope.all_cost_centers:
        raise HTTPException(status_code=403, detail="All-cost-center Budget scope required")


def require_cost_center(uow: BudgetUnitOfWork, cost_center_id) -> None:
    if uow.scope.all_cost_centers:
        return
    if cost_center_id not in uow.scope.cost_center_ids:
        raise HTTPException(status_code=403, detail="Cost center outside Budget scope")
