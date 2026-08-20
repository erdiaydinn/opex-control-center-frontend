"""Core boundary for evidence-bound Planogram shadow backtests."""

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
def _load_shadow_backtest() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "shadow_backtest.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Planogram shadow backtest is unavailable")
    return _module_from_root("shadow_backtest", root)


def generate_shadow_backtest_preview(
    *,
    pairs: list[dict[str, Any]],
    metric_directions: dict[str, str] | None = None,
    minimum_pairs: int = 3,
) -> dict[str, Any]:
    module = _load_shadow_backtest()
    function = getattr(module, "evaluate_shadow_backtest", None)
    if not callable(function):
        raise PlanogramEngineUnavailable("Planogram shadow backtest entrypoint is unavailable")
    result = function(
        pairs=pairs,
        metric_directions=metric_directions,
        minimum_pairs=minimum_pairs,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Planogram shadow backtest returned invalid data")
    if result.get("causal_claim_allowed") not in (False, None):
        raise PlanogramEngineUnavailable("Shadow backtest violated causal-claim boundary")
    if result.get("market_leadership_claim_allowed") not in (False, None):
        raise PlanogramEngineUnavailable("Shadow backtest violated market-claim boundary")
    return {
        **result,
        "causal_claim_allowed": False,
        "market_leadership_claim_allowed": False,
    }
