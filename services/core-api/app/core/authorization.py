import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.permission_catalog import is_known_permission
from app.core.security import (
    ROLE_PLATFORM_ADMIN,
    ROLE_SUPER_ADMIN,
    Principal,
    get_current_principal,
    normalize_principal_roles,
)

# Existing Budget assignments predate the canonical {"type":"all"} scope form.
# Compatibility is intentionally centralized here so product modules never
# reinterpret raw permission assignments themselves. New scope formats must use
# canonical string-list dimensions or the exact {"type":"all"} grant.
LEGACY_UNRESTRICTED_FLAGS = frozenset({"all_cost_centers"})


class ResolvedPermissionScope(BaseModel):
    """Canonical DB-derived scope for one permission.

    Modules may interpret named dimensions (for example warehouses, regions,
    cost_centers), but they must not reconstruct permission assignments or
    accept scope authority from browser/request payloads.
    """

    permission_key: str
    unrestricted: bool = False
    dimensions: dict[str, frozenset[str]] = Field(default_factory=dict)
    role_keys: frozenset[str] = frozenset()

    @property
    def empty(self) -> bool:
        return not self.unrestricted and not any(self.dimensions.values())

    def values(self, dimension: str) -> frozenset[str]:
        return self.dimensions.get(str(dimension).strip(), frozenset())


def _invalid_scope() -> HTTPException:
    # A malformed DB-authoritative scope is an infrastructure/configuration
    # fault. Never reinterpret it permissively inside a product module.
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authorization scope is invalid",
    )


def resolve_permission_scope(
    principal: Principal,
    permission_key: str,
) -> ResolvedPermissionScope:
    normalized = str(permission_key or "").strip()
    if not normalized or not is_known_permission(normalized):
        raise RuntimeError(f"Unknown permission scope: {normalized!r}")

    if normalized not in principal.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "You do not have permission to perform this action",
                "required_permission": normalized,
            },
        )

    assignments = tuple(
        assignment
        for assignment in principal.permission_assignments
        if assignment.key == normalized
    )
    if not assignments:
        # principal.permissions is itself derived from assignments. If these
        # ever disagree, fail closed rather than inventing an unscoped grant.
        raise _invalid_scope()

    unrestricted = False
    dimensions: dict[str, set[str]] = {}
    role_keys: set[str] = set()

    for assignment in assignments:
        role_keys.add(assignment.role_key)
        scope = assignment.scope
        if not isinstance(scope, dict):
            raise _invalid_scope()

        if "type" in scope:
            if scope != {"type": "all"}:
                raise _invalid_scope()
            unrestricted = True
            continue

        for legacy_flag in LEGACY_UNRESTRICTED_FLAGS:
            if legacy_flag not in scope:
                continue
            legacy_value = scope[legacy_flag]
            if not isinstance(legacy_value, bool):
                raise _invalid_scope()
            if legacy_value:
                unrestricted = True

        for raw_dimension, raw_values in scope.items():
            dimension = str(raw_dimension or "").strip()
            if dimension in LEGACY_UNRESTRICTED_FLAGS:
                continue
            if not dimension or not isinstance(raw_values, list):
                raise _invalid_scope()

            bucket = dimensions.setdefault(dimension, set())
            for raw_value in raw_values:
                if not isinstance(raw_value, str):
                    raise _invalid_scope()
                value = raw_value.strip()
                if value:
                    bucket.add(value)

    resolved = ResolvedPermissionScope(
        permission_key=normalized,
        unrestricted=unrestricted,
        dimensions={
            key: frozenset(values)
            for key, values in sorted(dimensions.items())
            if values
        },
        role_keys=frozenset(role_keys),
    )
    if resolved.empty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Permission has no authorized resource scope",
                "required_permission": normalized,
            },
        )
    return resolved


def require_permission(permission_key: str):
    """Require one DB-authoritative permission resolved for the current tenant."""
    normalized = str(permission_key or "").strip()
    if not normalized or not is_known_permission(normalized):
        raise RuntimeError(f"Unknown permission dependency: {normalized!r}")

    async def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if normalized not in principal.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "You do not have permission to perform this action",
                    "required_permission": normalized,
                },
            )
        return principal

    return dependency


def _control_plane_tenant_id() -> UUID:
    raw = os.getenv("OPEX_PLATFORM_CONTROL_TENANT_ID", "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform control-plane authority is not configured",
        )
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform control-plane authority is invalid",
        ) from exc


async def require_control_plane_admin(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    """
    EAY-internal control-plane authority.

    A customer tenant can never become platform security authority merely by
    receiving a similarly named role. Both the EAY control tenant and the
    platform/super-admin role must match.
    """
    roles = normalize_principal_roles(principal)
    if roles.isdisjoint({ROLE_PLATFORM_ADMIN, ROLE_SUPER_ADMIN}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="EAY platform administrator authority is required",
        )

    if principal.tenant_id != _control_plane_tenant_id():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This tenant is not the EAY platform control plane",
        )

    return principal
