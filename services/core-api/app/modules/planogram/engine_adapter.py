"""Thin adapter to the canonical PlanAI deterministic/physical-truth engine.

The implementation deliberately does not copy placement rules into Core API.
`apps/planai/backend` remains the single source of truth; this module only
loads that reviewed library and exposes a narrow fail-closed product boundary.
"""

from __future__ import annotations

import importlib
import os
import sys
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


class PlanogramEngineUnavailable(RuntimeError):
    """Raised when the canonical PlanAI library cannot be loaded safely."""


def _candidate_roots() -> tuple[Path, ...]:
    configured = os.getenv("OPEX_PLANOGRAM_ENGINE_ROOT", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))

    # Source checkout: services/core-api/app/modules/planogram -> repository root.
    with suppress(IndexError):
        candidates.append(
            Path(__file__).resolve().parents[5] / "apps" / "planai" / "backend"
        )

    # Immutable Core API image target.
    candidates.append(Path("/opt/eay/planai"))

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def _resolve_engine_root() -> Path:
    required = (
        "engine.py",
        "physical_truth.py",
        "physical_engine.py",
        "architecture_truth.py",
    )
    for root in _candidate_roots():
        if all((root / filename).is_file() for filename in required):
            return root
    raise PlanogramEngineUnavailable("Canonical Planogram engine source is unavailable")


def _module_from_root(name: str, root: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        source = getattr(existing, "__file__", None)
        if source is None or Path(source).resolve().parent != root:
            raise PlanogramEngineUnavailable(
                f"Unsafe Python module collision while loading Planogram dependency: {name}"
            )
        return existing

    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if source is None or Path(source).resolve().parent != root:
        raise PlanogramEngineUnavailable(
            f"Planogram dependency resolved outside canonical engine root: {name}"
        )
    return module


@lru_cache(maxsize=1)
def _load_modules() -> tuple[Path, ModuleType, ModuleType, ModuleType]:
    root = _resolve_engine_root()
    engine = _module_from_root("engine", root)
    physical_truth = _module_from_root("physical_truth", root)
    physical_engine = _module_from_root("physical_engine", root)
    return root, engine, physical_truth, physical_engine


@lru_cache(maxsize=1)
def _load_optimizer() -> ModuleType:
    root, _, _, _ = _load_modules()
    optimizer_path = root / "physical_optimizer_v3.py"
    if not optimizer_path.is_file():
        raise PlanogramEngineUnavailable("Canonical Planogram optimizer V3 is unavailable")
    return _module_from_root("physical_optimizer_v3", root)


@lru_cache(maxsize=1)
def _load_market_search_optimizer() -> ModuleType:
    root, _, _, _ = _load_modules()
    optimizer_path = root / "physical_optimizer_v4.py"
    if not optimizer_path.is_file():
        raise PlanogramEngineUnavailable(
            "Experimental Planogram market-search optimizer V4 is unavailable"
        )
    return _module_from_root("physical_optimizer_v4", root)


def engine_status() -> dict[str, Any]:
    """Return non-sensitive deployment status for the canonical library."""
    root, engine, physical_truth, physical_engine = _load_modules()
    return {
        "available": True,
        "contract": "physical-truth-gated-deterministic-v1",
        "foundation": "deterministic-best-fit-v4.2",
        "library_mode": True,
        "legacy_bridge_enabled": False,
        "production_ai_dimensions_allowed": False,
        "architecture_contract": "store-architecture-v1",
        "optimizer": {
            "available": (root / "physical_optimizer_v3.py").is_file(),
            "contract": "physical-plan-optimizer-v3-picker-tour",
            "fallback_contract": "physical-plan-optimizer-v2",
            "production_authority": False,
            "route_objective": "measured-basket-picker-tour-v1",
            "requires_observed_baskets": True,
        },
        "market_search_benchmark": {
            "available": (root / "physical_optimizer_v4.py").is_file(),
            "contract": "physical-plan-optimizer-v4-bounded-search",
            "preview_only": True,
            "production_authority": False,
            "requires_observed_baskets": True,
            "promotion_requires": [
                "blind_expert_benchmark",
                "real_store_kpi_backtest",
                "field_acceptance",
            ],
        },
        "source_modules": {
            "engine": Path(engine.__file__ or "").name,
            "physical_truth": Path(physical_truth.__file__ or "").name,
            "physical_engine": Path(physical_engine.__file__ or "").name,
        },
    }


def generate_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """Evaluate request-supplied candidate data through the canonical engine.

    This is intentionally only a preview. The caller cannot turn request data
    into production authority; the route layer always marks the result as
    unattested and non-releasable.
    """
    _, _, _, physical_engine = _load_modules()
    generator = getattr(physical_engine, "generate_production_plan", None)
    if not callable(generator):
        raise PlanogramEngineUnavailable(
            "Canonical production Planogram entrypoint is unavailable"
        )

    result = generator(products, layout, store_dna, mode=mode)
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Canonical Planogram engine returned an invalid result")
    return result


def generate_optimized_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    mode: str,
    orders: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run basket-aware architecture optimization without production authority.

    V3 uses only caller-supplied observed/test baskets. When baskets or measured
    architecture are absent, the canonical V3 optimizer delegates to the V2
    physical optimizer rather than fabricating demand or geometry evidence.
    Every candidate still passes the physical production gate and Core keeps
    HTTP payloads unattested and non-releasable.
    """
    optimizer = _load_optimizer()
    optimize = getattr(optimizer, "optimize_production_plan", None)
    if not callable(optimize):
        raise PlanogramEngineUnavailable(
            "Canonical Planogram optimizer entrypoint is unavailable"
        )
    result = optimize(
        products,
        layout,
        store_dna,
        mode=mode,
        orders=orders,
    )
    if not isinstance(result, dict) or not isinstance(result.get("optimizer"), dict):
        raise PlanogramEngineUnavailable("Canonical Planogram optimizer returned an invalid result")
    return result


def _objective_delta(
    canonical: dict[str, float | int],
    experimental: dict[str, float | int],
) -> dict[str, float]:
    names = (
        "hard_violation_count",
        "weighted_unplaced_sales",
        "unplaced_sku_count",
        "tour_unsimulated_order_count",
        "tour_p95_m",
        "tour_average_m",
        "coverage_shortfall",
        "brand_fragmentation",
        "capacity_pressure",
    )
    return {
        name: round(float(experimental.get(name) or 0.0) - float(canonical.get(name) or 0.0), 6)
        for name in names
    }


def generate_market_leadership_benchmark_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    mode: str,
    orders: list[dict[str, Any]],
    max_candidates: int = 24,
) -> dict[str, Any]:
    """Compare canonical V3 and experimental V4 on identical unattested evidence.

    The comparison is intentionally incapable of promoting V4. It exists to
    produce a repeatable, same-input benchmark before any blind expert or field
    KPI evaluation. Raw order/customer identity is not part of the Core request
    contract; only anonymized SKU baskets reach this adapter.
    """
    if not orders:
        raise PlanogramEngineUnavailable(
            "Market-leadership benchmark requires observed or test SKU baskets"
        )

    canonical_optimizer = _load_optimizer()
    market_optimizer = _load_market_search_optimizer()
    canonical_optimize = getattr(canonical_optimizer, "optimize_production_plan", None)
    market_optimize = getattr(market_optimizer, "optimize_production_plan", None)
    objective_key = getattr(canonical_optimizer, "objective_key", None)
    if (
        not callable(canonical_optimize)
        or not callable(market_optimize)
        or not callable(objective_key)
    ):
        raise PlanogramEngineUnavailable("Planogram benchmark optimizer contract is unavailable")

    canonical = canonical_optimize(
        products,
        layout,
        store_dna,
        mode=mode,
        orders=orders,
    )
    experimental = market_optimize(
        products,
        layout,
        store_dna,
        mode=mode,
        orders=orders,
        max_candidates=max_candidates,
    )
    canonical_meta = canonical.get("picker_tour_optimizer") or {}
    experimental_meta = experimental.get("market_search_optimizer") or {}
    canonical_objective = canonical_meta.get("selected_objective")
    experimental_objective = experimental_meta.get("selected_objective")

    comparison_available = isinstance(canonical_objective, dict) and isinstance(
        experimental_objective, dict
    )
    if comparison_available:
        canonical_rank = objective_key(canonical_objective)
        experimental_rank = objective_key(experimental_objective)
        if experimental_rank < canonical_rank:
            winner = "experimental_v4"
        elif canonical_rank < experimental_rank:
            winner = "canonical_v3"
        else:
            winner = "tie"
        delta = _objective_delta(canonical_objective, experimental_objective)
    else:
        winner = "unavailable"
        delta = {}

    return {
        "benchmark_contract": "planogram-v3-v4-same-evidence-benchmark-v1",
        "preview_only": True,
        "production_authority": False,
        "production_evidence": False,
        "comparison_available": comparison_available,
        "winner_on_repository_objective": winner,
        "objective_delta_experimental_minus_canonical": delta,
        "canonical_v3": {
            "optimizer_version": canonical_meta.get("optimizer_version"),
            "allowed": canonical_meta.get("allowed"),
            "effective": canonical_meta.get("effective"),
            "selected_strategy": canonical_meta.get("selected_strategy"),
            "candidate_count": canonical_meta.get("candidate_count"),
            "selected_objective": canonical_objective,
            "selected_tour": canonical_meta.get("selected_tour"),
        },
        "experimental_v4": {
            "optimizer_version": experimental_meta.get("optimizer_version"),
            "allowed": experimental_meta.get("allowed"),
            "effective": experimental_meta.get("effective"),
            "selected_strategy": experimental_meta.get("selected_strategy"),
            "candidate_count": experimental_meta.get("candidate_count"),
            "search_budget": experimental_meta.get("search_budget"),
            "pareto_frontier_count": experimental_meta.get("pareto_frontier_count"),
            "selected_objective": experimental_objective,
            "selected_tour": experimental_meta.get("selected_tour"),
            "alternatives": experimental_meta.get("alternatives") or [],
        },
        "promotion_allowed": False,
        "promotion_blockers": [
            "blind_expert_benchmark_required",
            "real_store_kpi_backtest_required",
            "field_acceptance_required",
        ],
        "evidence_boundary": (
            "repository objective comparison is necessary but insufficient; "
            "V4 cannot replace V3 without blind expert and real-store evidence"
        ),
    }
