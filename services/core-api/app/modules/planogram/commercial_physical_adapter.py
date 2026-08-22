"""Core boundary for commercial-to-physical Planogram convergence preview."""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import Any

from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    _load_modules,
    _module_from_root,
)


@lru_cache(maxsize=1)
def _load_convergence() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "commercial_physical_convergence.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Commercial-physical convergence is unavailable")
    return _module_from_root("commercial_physical_convergence", root)


def generate_commercial_physical_convergence_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    category_capacity_cm: dict[str, Any] | None = None,
    total_shelf_width_cm: float | None = None,
    substitution_edges: list[dict[str, Any]] | None = None,
    objective_weights: dict[str, Any] | None = None,
    mode: str = "HYBRID",
    require_images: bool = True,
) -> dict[str, Any]:
    module = _load_convergence()
    function = getattr(module, "converge_commercial_physical", None)
    if not callable(function):
        raise PlanogramEngineUnavailable(
            "Commercial-physical convergence entrypoint is unavailable"
        )
    result = function(
        products=products,
        layout=layout,
        store_dna=store_dna,
        category_capacity_cm=category_capacity_cm,
        total_shelf_width_cm=total_shelf_width_cm,
        substitution_edges=substitution_edges,
        objective_weights=objective_weights,
        mode=mode,
        require_images=require_images,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Commercial-physical convergence returned invalid data")
    for field in (
        "production_authority",
        "assortment_execution_authority",
        "installation_authority",
        "market_leadership_claim_allowed",
    ):
        if result.get(field) not in (False, None):
            raise PlanogramEngineUnavailable(
                f"Convergence preview violated authority boundary: {field}"
            )
    return {
        **result,
        "production_authority": False,
        "assortment_execution_authority": False,
        "installation_authority": False,
        "market_leadership_claim_allowed": False,
    }
