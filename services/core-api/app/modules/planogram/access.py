from __future__ import annotations

from fastapi import HTTPException, status

from app.core.authorization import resolve_permission_scope
from app.core.security import Principal
from app.modules.planogram.store_dna import normalize_store_code

PLANOGRAM_STORE_SCOPE_DIMENSIONS = ("warehouses", "locations")


def ensure_planogram_store_scope(
    principal: Principal,
    permission_key: str,
    store_code: str,
    *,
    conceal: bool = False,
) -> str:
    """Bind a Planogram action to DB-authoritative store assignments."""
    canonical = normalize_store_code(store_code)
    scope = resolve_permission_scope(principal, permission_key)
    if scope.unrestricted:
        return canonical

    allowed: set[str] = set()
    for dimension in PLANOGRAM_STORE_SCOPE_DIMENSIONS:
        for value in scope.values(dimension):
            allowed.add(normalize_store_code(value))

    if canonical in allowed:
        return canonical

    if conceal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planogram resource is unavailable",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Planogram permission scope does not cover this store",
    )
