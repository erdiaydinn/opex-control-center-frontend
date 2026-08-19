from __future__ import annotations

from dataclasses import dataclass

from app.core.authorization import resolve_permission_scope
from app.core.security import Principal


@dataclass(frozen=True)
class AuditScope:
    unrestricted: bool
    regions: frozenset[str]
    location_ids: frozenset[str]


def require_audit_scope(principal: Principal, permission_key: str) -> AuditScope:
    """Map Core-authoritative scope dimensions to Audit terminology.

    Audit never parses raw role grants itself. Core owns permission resolution;
    this adapter only maps canonical scope dimensions to region/location IDs.
    """

    scope = resolve_permission_scope(principal, permission_key)
    return AuditScope(
        unrestricted=scope.unrestricted,
        regions=frozenset(scope.values("regions")),
        location_ids=frozenset(scope.values("locations") | scope.values("warehouses")),
    )


def scope_allows_location(
    scope: AuditScope,
    *,
    location_id: str,
    region: str | None,
) -> bool:
    if scope.unrestricted:
        return True
    if location_id in scope.location_ids:
        return True
    return bool(region and region in scope.regions)
