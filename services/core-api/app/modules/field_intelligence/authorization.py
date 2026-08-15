from __future__ import annotations

from fastapi import HTTPException, status

from app.core.security import Principal

from .schemas import FieldScope


def require_field_permission(principal: Principal, permission_key: str) -> FieldScope:
    if permission_key not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Field Intelligence permission is required",
        )

    assignments = [
        assignment
        for assignment in principal.permission_assignments
        if assignment.key == permission_key
    ]
    unrestricted = False
    regions: set[str] = set()
    locations: set[str] = set()

    for assignment in assignments:
        scope = assignment.scope
        if scope.get("type") == "all" and set(scope) == {"type"}:
            unrestricted = True
            break
        for raw in scope.get("regions", ()) if isinstance(scope.get("regions"), list) else ():
            value = str(raw).strip()
            if value:
                regions.add(value)
        for raw in scope.get("warehouses", ()) if isinstance(scope.get("warehouses"), list) else ():
            value = str(raw).strip()
            if value:
                locations.add(value)

    field_scope = FieldScope(
        unrestricted=unrestricted,
        regions=frozenset(regions),
        location_ids=frozenset(locations),
    )
    if field_scope.empty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Field Intelligence permission has no authorized location scope",
        )
    return field_scope
