"""Core API boundary for preview-only commercial merchandising optimization."""

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
def _load_commercial_optimizer() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "commercial_merchandising.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Commercial merchandising optimizer is unavailable")
    return _module_from_root("commercial_merchandising", root)


def generate_commercial_merchandising_preview(
    *,
    products: list[dict[str, Any]],
    category_capacity_cm: dict[str, Any] | None = None,
    total_shelf_width_cm: float | None = None,
    substitution_edges: list[dict[str, Any]] | None = None,
    objective_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    optimizer = _load_commercial_optimizer()
    function = getattr(optimizer, "optimize_commercial_merchandising", None)
    if not callable(function):
        raise PlanogramEngineUnavailable("Commercial merchandising entrypoint is unavailable")
    result = function(
        products=products,
        category_capacity_cm=category_capacity_cm,
        total_shelf_width_cm=total_shelf_width_cm,
        substitution_edges=substitution_edges,
        objective_weights=objective_weights,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Commercial merchandising optimizer returned invalid data")
    if result.get("production_authority") not in (False, None):
        raise PlanogramEngineUnavailable(
            "Commercial merchandising preview violated authority boundary"
        )
    return {**result, "production_authority": False, "assortment_authority": False}
