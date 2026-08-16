from __future__ import annotations

from app.core.authorization import resolve_permission_scope
from app.core.security import Principal

from .schemas import FieldScope


def require_field_permission(principal: Principal, permission_key: str) -> FieldScope:
    """Translate Core-authoritative scope into the Field domain view.

    Field Intelligence no longer reads raw principal permission assignments or
    decides what constitutes an unrestricted grant.  Core owns that authority;
    this adapter only maps canonical dimensions to Field terminology.
    """
    scope = resolve_permission_scope(principal, permission_key)
    return FieldScope(
        unrestricted=scope.unrestricted,
        regions=scope.values("regions"),
        location_ids=scope.values("warehouses") | scope.values("locations"),
    )
