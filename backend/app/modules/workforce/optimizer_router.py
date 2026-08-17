"""Read-only canonical Workforce API surface for roadmap 14/60 optimizer."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from .authorization import is_action_allowed
from .optimizer_repository import get_latest_optimizer_proposal


router = APIRouter(tags=["Workforce Optimizer"])


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


@router.get("/depots/{location_id}/optimizer/latest")
def latest_optimizer_proposal(
    location_id: str,
    request: Request,
    x_opex_role: str = Header(default="viewer", alias="X-OPEX-Role"),
    x_opex_permissions: str = Header(default="", alias="X-OPEX-Permissions"),
) -> dict[str, object]:
    _require_read(x_opex_role, x_opex_permissions)
    canonical = _canonical_location_in_scope(request, x_opex_role, location_id)
    proposal = get_latest_optimizer_proposal(canonical)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Optimizer proposal bulunamadı.")
    result = dict(proposal)
    result["target_gap_man_hours"] = float(proposal["target_gap_man_hours"])
    result["covered_gap_man_hours"] = float(proposal["covered_gap_man_hours"])
    result["remaining_gap_man_hours"] = float(proposal["remaining_gap_man_hours"])
    return result
