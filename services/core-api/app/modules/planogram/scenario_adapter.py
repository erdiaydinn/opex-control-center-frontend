"""Core boundary for deterministic V5 scenario-candidate replay."""

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
def _load_candidate_preview() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "physical_layout_candidate_preview.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable(
            "Planogram physical-layout candidate preview is unavailable"
        )
    return _module_from_root("physical_layout_candidate_preview", root)


def generate_physical_layout_candidate_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    layout_fingerprint: str,
    mode: str,
    max_layout_candidates: int = 16,
    max_allocation_candidates: int = 12,
) -> dict[str, Any]:
    module = _load_candidate_preview()
    replay = getattr(module, "preview_physical_layout_candidate", None)
    if not callable(replay):
        raise PlanogramEngineUnavailable(
            "Planogram physical-layout candidate entrypoint is unavailable"
        )

    result = replay(
        products=products,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
        layout_fingerprint=layout_fingerprint,
        mode=mode,
        max_layout_candidates=max_layout_candidates,
        max_allocation_candidates=max_allocation_candidates,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable(
            "Planogram physical-layout candidate preview returned invalid data"
        )

    for field in (
        "production_authority",
        "execution_authority",
        "physical_relocation_authority",
        "installation_approved",
        "capex_approved",
    ):
        value = result.get(field)
        if value not in (False, None):
            raise PlanogramEngineUnavailable(
                f"Planogram scenario replay violated authority boundary: {field}"
            )

    return {
        **result,
        "production_authority": False,
        "execution_authority": False,
        "physical_relocation_authority": False,
        "installation_approved": False,
        "capex_approved": False,
        "global_optimum_claim": False,
    }
