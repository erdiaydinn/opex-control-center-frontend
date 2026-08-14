import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.core.permission_catalog import is_known_permission
from app.core.security import (
    Principal,
    ROLE_PLATFORM_ADMIN,
    ROLE_SUPER_ADMIN,
    get_current_principal,
    normalize_principal_roles,
)


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
