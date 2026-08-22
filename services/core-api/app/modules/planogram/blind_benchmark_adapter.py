"""Core boundary for blinded V1/V2 Planogram A/B benchmarking."""

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
def _load_v1_benchmark() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "blind_benchmark.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Planogram blind benchmark V1 is unavailable")
    return _module_from_root("blind_benchmark", root)


@lru_cache(maxsize=1)
def _load_v2_benchmark() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "blind_benchmark_v2.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Planogram blind benchmark V2 is unavailable")
    return _module_from_root("blind_benchmark_v2", root)


def _architecture_schema_version(store_dna: dict[str, Any]) -> int:
    architecture = store_dna.get("architecture")
    if not isinstance(architecture, dict):
        raise PlanogramEngineUnavailable(
            "Blind benchmark requires measured Store DNA architecture"
        )
    try:
        return int(architecture.get("schema_version") or 0)
    except (TypeError, ValueError) as exc:
        raise PlanogramEngineUnavailable(
            "Blind benchmark architecture schema is invalid"
        ) from exc


def generate_blind_benchmark_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
) -> dict[str, Any]:
    """Score anonymous A/B candidates under one shared evidence fingerprint."""
    schema_version = _architecture_schema_version(store_dna)
    if schema_version == 1:
        module = _load_v1_benchmark()
        benchmark = getattr(module, "benchmark_candidates", None)
    elif schema_version == 2:
        module = _load_v2_benchmark()
        benchmark = getattr(module, "benchmark_candidates_v2", None)
    else:
        raise PlanogramEngineUnavailable(
            f"Unsupported blind benchmark architecture schema: {schema_version}"
        )

    if not callable(benchmark):
        raise PlanogramEngineUnavailable("Blind benchmark entrypoint is unavailable")
    result = benchmark(
        products=products,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
        candidate_a=candidate_a,
        candidate_b=candidate_b,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Blind benchmark returned invalid data")
    if result.get("production_evidence") is not False:
        raise PlanogramEngineUnavailable(
            "Blind benchmark violated production-evidence boundary"
        )
    if result.get("market_leadership_proven") is not False:
        raise PlanogramEngineUnavailable(
            "Blind benchmark violated market-leadership truth boundary"
        )
    if result.get("promotion_allowed") not in (False, None):
        raise PlanogramEngineUnavailable(
            "Blind benchmark violated promotion-authority boundary"
        )
    return {
        **result,
        "architecture_schema_version": schema_version,
        "production_authority": False,
        "production_evidence": False,
        "market_leadership_proven": False,
        "promotion_allowed": False,
    }
