"""Bounded multi-profile search for PlanAI market-leadership benchmarking.

V4 expands V3's eight fixed candidate profiles into a deterministic search
portfolio while preserving the exact same physical-truth and basket-tour gates.
It is preview/benchmark code: production authority remains with the reviewed V3
path until real-store backtests prove that the larger search is beneficial.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import physical_optimizer_v2 as v2
import physical_optimizer_v3 as v3
from engine import DEFAULT_SCORING_CONFIG
from physical_engine import generate_production_plan

OPTIMIZER_VERSION = "physical-plan-optimizer-v4-bounded-search"
MIN_SEARCH_CANDIDATES = 8
DEFAULT_SEARCH_CANDIDATES = 24
MAX_SEARCH_CANDIDATES = 32
SEARCH_FACTORS = (0.75, 1.0, 1.35, 1.75)
PARETO_METRICS = (
    "weighted_unplaced_sales",
    "unplaced_sku_count",
    "tour_unsimulated_order_count",
    "tour_p95_m",
    "tour_average_m",
    "brand_fragmentation",
    "capacity_pressure",
)


def _rounded_config(config: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 4) for key, value in sorted(config.items())}


def _config_key(config: dict[str, float] | None) -> tuple[tuple[str, float], ...]:
    if config is None:
        return ()
    return tuple(_rounded_config(config).items())


def search_profiles() -> tuple[tuple[str, dict[str, float] | None], ...]:
    """Return a deterministic, de-duplicated portfolio of scoring profiles."""
    profiles: list[tuple[str, dict[str, float] | None]] = [("baseline", None)]
    seen = {()}

    for name, raw_config in v2.STRATEGIES[1:]:
        config = _rounded_config(dict(raw_config or {}))
        key = _config_key(config)
        if key in seen:
            continue
        seen.add(key)
        profiles.append((f"seed::{name}", config))

    base = {key: float(value) for key, value in DEFAULT_SCORING_CONFIG.items()}
    for picking_factor in SEARCH_FACTORS:
        for availability_factor in SEARCH_FACTORS:
            config = dict(base)
            config["picking"] = base["picking"] * picking_factor
            config["sales"] = base["sales"] * availability_factor
            config["refill"] = base["refill"] * availability_factor
            # A speed-heavy search must not silently erase ergonomics/risk.
            guard_factor = max(0.9, 1.15 - (picking_factor - 1.0) * 0.15)
            config["ergonomics"] = base["ergonomics"] * guard_factor
            config["risk"] = base["risk"] * guard_factor
            normalized = _rounded_config(config)
            key = _config_key(normalized)
            if key in seen:
                continue
            seen.add(key)
            profile_name = f"search::pick-{picking_factor:.2f}::availability-{availability_factor:.2f}"
            profiles.append((profile_name, normalized))

    # Explicitly probe safer ergonomic/replenishment corners as well as speed.
    for name, changes in (
        ("search::ergonomic-guard", {"ergonomics": 1.65, "risk": 1.65}),
        ("search::refill-guard", {"refill": 1.7, "risk": 1.4}),
        (
            "search::balanced-high",
            {
                "sales": 1.6,
                "picking": 1.6,
                "ergonomics": 1.25,
                "refill": 1.25,
                "risk": 1.4,
            },
        ),
    ):
        config = dict(base)
        config.update(changes)
        normalized = _rounded_config(config)
        key = _config_key(normalized)
        if key not in seen:
            seen.add(key)
            profiles.append((name, normalized))

    return tuple(profiles)


def _metric(objective: dict[str, float | int], name: str) -> float:
    return float(objective.get(name) or 0.0)


def _dominates(
    left: dict[str, float | int],
    right: dict[str, float | int],
) -> bool:
    left_hard = _metric(left, "hard_violation_count")
    right_hard = _metric(right, "hard_violation_count")
    if left_hard != right_hard:
        return left_hard < right_hard
    left_values = tuple(_metric(left, name) for name in PARETO_METRICS)
    right_values = tuple(_metric(right, name) for name in PARETO_METRICS)
    return all(a <= b for a, b in zip(left_values, right_values, strict=True)) and any(
        a < b for a, b in zip(left_values, right_values, strict=True)
    )


def _pareto_indices(
    candidates: list[
        tuple[
            int,
            str,
            dict[str, Any],
            dict[str, float | int],
            dict[str, Any],
            dict[str, Any],
        ]
    ],
) -> list[int]:
    frontier: list[int] = []
    for index, candidate in enumerate(candidates):
        objective = candidate[3]
        if any(
            other_index != index and _dominates(other[3], objective)
            for other_index, other in enumerate(candidates)
        ):
            continue
        frontier.append(index)
    return frontier


def _summary(
    strategy: str,
    objective: dict[str, float | int],
    route: dict[str, Any],
    tour: dict[str, Any],
    *,
    pareto: bool,
) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "pareto_frontier": pareto,
        "hard_violation_count": int(objective["hard_violation_count"]),
        "weighted_unplaced_sales": float(objective["weighted_unplaced_sales"]),
        "unplaced_sku_count": int(objective["unplaced_sku_count"]),
        "coverage_shortfall": float(objective["coverage_shortfall"]),
        "brand_fragmentation": float(objective["brand_fragmentation"]),
        "capacity_pressure": float(objective["capacity_pressure"]),
        "tour_coverage_pct": float(tour["coverage_pct"]),
        "tour_p50_m": float(tour["p50_m"]),
        "tour_p90_m": float(tour["p90_m"]),
        "tour_p95_m": float(tour["p95_m"]),
        "tour_average_m": float(tour["average_m"]),
        "tour_unsimulated_order_count": int(tour["unsimulated_order_count"]),
        "route_basis": route.get("basis"),
    }


def optimize_production_plan(
    products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    *,
    orders: list[dict[str, Any]] | None = None,
    mode: str = "HYBRID",
    brand_side_rules: dict[str, str] | None = None,
    require_images: bool = True,
    max_candidates: int = DEFAULT_SEARCH_CANDIDATES,
) -> dict[str, Any]:
    """Search a bounded candidate portfolio and expose explainable alternatives."""
    source_products = deepcopy(products or [])
    source_orders = deepcopy(orders or [])
    if not source_orders:
        result = v3.optimize_production_plan(
            products=source_products,
            layout=deepcopy(layout),
            store_dna=deepcopy(store_dna),
            orders=source_orders,
            mode=mode,
            brand_side_rules=brand_side_rules,
            require_images=require_images,
        )
        result["market_search_optimizer"] = {
            "optimizer_version": OPTIMIZER_VERSION,
            "allowed": False,
            "effective": False,
            "reason": "order_baskets_missing",
            "selected_by": v3.OPTIMIZER_VERSION,
            "production_authority": False,
        }
        return result

    budget = max(MIN_SEARCH_CANDIDATES, min(MAX_SEARCH_CANDIDATES, max_candidates))
    profiles = search_profiles()[:budget]
    baseline = generate_production_plan(
        products=deepcopy(source_products),
        layout=deepcopy(layout),
        store_dna=deepcopy(store_dna),
        mode=mode,
        brand_side_rules=brand_side_rules,
        scoring_config=None,
        require_images=require_images,
    )
    if not baseline.get("solver_optimizer_allowed"):
        result = deepcopy(baseline)
        result["market_search_optimizer"] = {
            "optimizer_version": OPTIMIZER_VERSION,
            "allowed": False,
            "effective": False,
            "reason": "physical_truth_blocks_optimizer",
            "selected_by": "baseline",
            "production_authority": False,
        }
        return result

    baseline_objective, baseline_route, baseline_tour = v3.objective_components(
        baseline,
        source_products,
        layout,
        store_dna,
        source_orders,
    )
    if not baseline_tour["available"]:
        result = v3.optimize_production_plan(
            products=source_products,
            layout=deepcopy(layout),
            store_dna=deepcopy(store_dna),
            orders=source_orders,
            mode=mode,
            brand_side_rules=brand_side_rules,
            require_images=require_images,
        )
        result["market_search_optimizer"] = {
            "optimizer_version": OPTIMIZER_VERSION,
            "allowed": False,
            "effective": False,
            "reason": "picker_tour_simulation_unavailable",
            "selected_by": v3.OPTIMIZER_VERSION,
            "production_authority": False,
        }
        return result

    candidate_type = tuple[
        int,
        str,
        dict[str, Any],
        dict[str, float | int],
        dict[str, Any],
        dict[str, Any],
    ]
    candidates: list[candidate_type] = [
        (
            0,
            "baseline",
            baseline,
            baseline_objective,
            baseline_route,
            baseline_tour,
        )
    ]
    for order, (strategy, scoring_config) in enumerate(profiles[1:], start=1):
        candidate = generate_production_plan(
            products=deepcopy(source_products),
            layout=deepcopy(layout),
            store_dna=deepcopy(store_dna),
            mode=mode,
            brand_side_rules=brand_side_rules,
            scoring_config=deepcopy(scoring_config),
            require_images=require_images,
        )
        objective, route, tour = v3.objective_components(
            candidate,
            source_products,
            layout,
            store_dna,
            source_orders,
        )
        candidates.append((order, strategy, candidate, objective, route, tour))

    selected = min(candidates, key=lambda row: (v3.objective_key(row[3]), row[0]))
    if v3.objective_key(selected[3]) > v3.objective_key(baseline_objective):
        selected = candidates[0]
    _, selected_strategy, selected_result, selected_objective, _, selected_tour = selected

    pareto = set(_pareto_indices(candidates))
    ranked = sorted(candidates, key=lambda row: (v3.objective_key(row[3]), row[0]))
    alternatives = [
        row for row in ranked if row[1] != selected_strategy and row[0] in pareto
    ][:3]

    result = deepcopy(selected_result)
    result["market_search_optimizer"] = {
        "optimizer_version": OPTIMIZER_VERSION,
        "allowed": True,
        "effective": True,
        "preview_only": True,
        "production_authority": False,
        "production_evidence": False,
        "evidence_boundary": (
            "candidate search uses supplied baskets and repository geometry only; "
            "blind expert and field KPI acceptance remain external"
        ),
        "search_space": "deterministic-seed-plus-weight-grid",
        "search_budget": budget,
        "available_profile_count": len(search_profiles()),
        "candidate_count": len(candidates),
        "baseline_preserved": v3.objective_key(selected_objective)
        <= v3.objective_key(baseline_objective),
        "improved": v3.objective_key(selected_objective)
        < v3.objective_key(baseline_objective),
        "selected_strategy": selected_strategy,
        "selected_objective": selected_objective,
        "baseline_objective": baseline_objective,
        "selected_tour": selected_tour,
        "pareto_frontier_count": len(pareto),
        "alternatives": [
            _summary(
                strategy,
                objective,
                route,
                tour,
                pareto=True,
            )
            for _, strategy, _, objective, route, tour in alternatives
        ],
        "candidates": [
            _summary(
                strategy,
                objective,
                route,
                tour,
                pareto=index in pareto,
            )
            for index, strategy, _, objective, route, tour in candidates
        ],
    }
    return result
