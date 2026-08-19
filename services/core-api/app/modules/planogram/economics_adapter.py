"""Core boundary for evidence-bound Planogram physical-layout economics."""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import Any

from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    _load_modules,
    _module_from_root,
)
from app.modules.planogram.physical_layout_adapter import (
    generate_physical_layout_search_preview,
)


@lru_cache(maxsize=1)
def _load_physical_economics() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "physical_economics.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Planogram physical-layout economics is unavailable")
    return _module_from_root("physical_economics", root)


def generate_physical_layout_economics_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    mode: str,
    assumptions: dict[str, Any],
    max_layout_candidates: int = 16,
    max_allocation_candidates: int = 12,
) -> dict[str, Any]:
    """Recompute V5 server-side, then evaluate sourced economic assumptions."""
    physical_layout = generate_physical_layout_search_preview(
        products=products,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
        mode=mode,
        max_layout_candidates=max_layout_candidates,
        max_allocation_candidates=max_allocation_candidates,
    )
    evaluator = getattr(
        _load_physical_economics(),
        "evaluate_physical_layout_economics",
        None,
    )
    if not callable(evaluator):
        raise PlanogramEngineUnavailable(
            "Planogram physical-layout economics entrypoint is unavailable"
        )

    economics = evaluator(
        physical_layout_result=physical_layout,
        assumptions=assumptions,
    )
    if not isinstance(economics, dict):
        raise PlanogramEngineUnavailable("Planogram economics returned invalid data")
    if economics.get("production_evidence") is not False:
        raise PlanogramEngineUnavailable(
            "Planogram economics violated production-evidence boundary"
        )
    if economics.get("finance_approved") is not False:
        raise PlanogramEngineUnavailable(
            "Planogram economics violated finance-approval boundary"
        )
    if economics.get("investment_decision_allowed") is not False:
        raise PlanogramEngineUnavailable(
            "Planogram economics violated investment-authority boundary"
        )

    return {
        "physical_layout": physical_layout,
        "economics": economics,
        "preview_only": True,
        "production_authority": False,
        "physical_relocation_authority": False,
        "installation_approved": False,
        "capex_approved": False,
        "finance_approved": False,
        "investment_decision_allowed": False,
        "realized_savings_proven": False,
    }
