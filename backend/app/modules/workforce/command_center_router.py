"""Read-only API surface for the Workforce intraday command center."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status

from .authorization import is_action_allowed
from .command_center import CommandCenterError, build_command_center
from .command_center_repository import CommandCenterAuthorityError
from .router import _canonical_warehouse_id, _warehouse_scope


router = APIRouter(tags=["Workforce Command Center"])


def _require_read(role: str, permissions: str) -> None:
    allowed = (
        "workforce.pressure.read",
        "workforce.schedule.read",
        "createShift",
    )
    if any(is_action_allowed(role, permissions, action) for action in allowed):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Workforce pressure veya schedule okuma yetkisi gerekir.",
    )


def _location_in_scope(request: Request, role: str, location_id: str) -> str:
    canonical = _canonical_warehouse_id(location_id)
    if canonical is None:
        raise HTTPException(status_code=404, detail="Depo/lokasyon bulunamadı.")
    scope = _warehouse_scope(request, role)
    if scope is not None and canonical not in scope:
        raise HTTPException(status_code=403, detail="Lokasyon yetkili depo kapsamınızın dışında.")
    return canonical


@router.get("/command-center/{location_id}")
def command_center(
    location_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require_read(x_opex_role, x_opex_permissions)
    canonical = _location_in_scope(request, x_opex_role, location_id)
    try:
        return build_command_center(canonical)
    except CommandCenterError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except CommandCenterAuthorityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
