"""Read-only canonical Workforce API surface for roadmap 13/60 DPI."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from .authorization import is_action_allowed
from .dpi_repository import get_latest_dpi_snapshot


router = APIRouter(tags=["Workforce DPI"])


def _require_read(role: str, permissions: str) -> None:
    if is_action_allowed(role, permissions, "workforce.pressure.read"):
        return
    raise HTTPException(status_code=403, detail="workforce.pressure.read yetkisi gerekir.")


def _canonical_location_in_scope(request: Request, role: str, location_id: str) -> str:
    from .router import _canonical_warehouse_id, _warehouse_scope

    canonical = _canonical_warehouse_id(location_id)
    if canonical is None:
        raise HTTPException(status_code=404, detail="Depo/lokasyon bulunamadı.")
    scope = _warehouse_scope(request, role)
    if scope is not None and canonical not in scope:
        raise HTTPException(status_code=403, detail="Lokasyon yetkili depo kapsamınızın dışında.")
    return canonical


@router.get("/depots/{location_id}/dpi/latest")
def latest_dpi(
    location_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require_read(x_opex_role, x_opex_permissions)
    canonical = _canonical_location_in_scope(request, x_opex_role, location_id)
    snapshot = get_latest_dpi_snapshot(canonical)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="DPI snapshot bulunamadı.")
    result = dict(snapshot)
    result["demand_pressure_index"] = float(snapshot["demand_pressure_index"])
    result["capacity_gap_man_hours"] = float(snapshot["capacity_gap_man_hours"])
    result["required_man_hours"] = float(snapshot["required_man_hours"])
    result["effective_man_hours"] = float(snapshot["effective_man_hours"])
    return result
