"""Core boundary for experimental Planogram physical-layout search V5."""

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
def _load_physical_layout_optimizer() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "physical_layout_optimizer_v5.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable(
            "Experimental Planogram physical-layout optimizer V5 is unavailable"
        )
    return _module_from_root("physical_layout_optimizer_v5", root)


def generate_physical_layout_search_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    mode: str,
    max_layout_candidates: int = 16,
    max_allocation_candidates: int = 12,
) -> dict[str, Any]:
    """Search physical-layout alternatives without granting move authority."""
    optimizer = _load_physical_layout_optimizer()
    optimize = getattr(optimizer, "optimize_physical_layout", None)
    if not callable(optimize):
        raise PlanogramEngineUnavailable(
            "Experimental Planogram physical-layout entrypoint is unavailable"
        )

    result = optimize(
        products=products,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
        mode=mode,
        max_layout_candidates=max_layout_candidates,
        max_allocation_candidates=max_allocation_candidates,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable(
            "Experimental Planogram physical-layout optimizer returned invalid data"
        )

    meta = result.get("physical_layout_optimizer")
    if isinstance(meta, dict):
        if meta.get("production_authority") is not False:
            raise PlanogramEngineUnavailable(
                "Physical-layout preview violated production-authority boundary"
            )
        if meta.get("physical_relocation_authority") is not False:
            raise PlanogramEngineUnavailable(
                "Physical-layout preview violated relocation-authority boundary"
            )
        if meta.get("installation_approved") is not False:
            raise PlanogramEngineUnavailable(
                "Physical-layout preview violated installation-approval boundary"
            )
    else:
        if result.get("production_authority") not in (False, None):
            raise PlanogramEngineUnavailable(
                "Physical-layout preview violated production-authority boundary"
            )
        if result.get("physical_relocation_authority") not in (False, None):
            raise PlanogramEngineUnavailable(
                "Physical-layout preview violated relocation-authority boundary"
            )

    return {
        **result,
        "production_authority": False,
        "physical_relocation_authority": False,
        "installation_approved": False,
        "capex_approved": False,
    }
