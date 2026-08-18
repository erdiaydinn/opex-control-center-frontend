"""Architecture-aware deterministic optimizer for PlanAI.

V2 keeps the fail-closed production generator from V1, but replaces the legacy
ordinal picking proxy with obstacle-aware metre distance whenever measured Store
DNA architecture and module coordinates are available. It also broadens the
candidate portfolio without changing the frozen foundation allocator.

This remains a deterministic candidate optimizer, not a claim of global optimum.
A future solver may search a much larger feasible space behind the same physical
truth and explainability contracts.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import physical_optimizer as v1
from architecture_truth import architecture_route_objective
from physical_engine import generate_production_plan

OPTIMIZER_VERSION = "physical-plan-optimizer-v2"

STRATEGIES: tuple[tuple[str, dict[str, float] | None], ...] = v1.STRATEGIES + (
    (
        "deep_route_focus",
        {
            "sales": 1.75,
            "picking": 2.20,
            "ergonomics": 1.35,
            "balance": 0.80,
            "brand_cluster": 0.90,
        },
    ),
    (
        "replenishment_flow_focus",
        {
            "refill": 1.85,
            "coverage": 1.45,
            "fixture": 1.35,
            "sales": 1.30,
            "balance": 1.05,
        },
    ),
    (
        "balanced_physical_focus",
        {
            "sales": 1.45,
            "picking": 1.50,
            "ergonomics": 1.30,
            "refill": 1.30,
            "coverage": 1.30,
            "fixture": 1.30,
            "brand_cluster": 1.20,
            "risk": 1.20,
            "balance": 1.15,
        },
    ),
)


def _route_objective(
    result: dict[str, Any],
    source_products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
) -> dict[str, Any]:
    # The production wrapper scopes module identity by aisle before routing and
    # stores the resulting evidence on every generated candidate. Reuse that
    # canonical evidence so duplicate legacy module ids cannot be remapped here.
    precomputed = result.get("architecture_route_objective")
    if isinstance(precomputed, dict):
        routed = deepcopy(precomputed)
    else:
        routed = architecture_route_objective(
            result,
            source_products,
            layout,
            store_dna,
        )
    if routed.get("available"):
        return routed
    return {
        **routed,
        "value": v1._picking_route_cost(result),
        "metric": "legacy_sales_weighted_ordinal_rank",
    }


def objective_components(
    result: dict[str, Any],
    source_products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
) -> tuple[dict[str, float | int], dict[str, Any]]:
    components = v1.objective_components(result, source_products)
    route = _route_objective(result, source_products, layout, store_dna)
    components["picking_route_cost"] = float(route["value"])
    return components, route


def _candidate_summary(
    strategy: str,
    result: dict[str, Any],
    objective: dict[str, float | int],
    route: dict[str, Any],
) -> dict[str, Any]:
    summary = v1._candidate_summary(strategy, result, objective)
    summary["route_basis"] = route.get("basis")
    summary["route_metric"] = route.get("metric")
    summary["route_cost"] = route.get("value")
    return summary


def _optimizer_fingerprint(
    selected_strategy: str,
    selected_objective: dict[str, float | int],
    selected_result: dict[str, Any],
    route: dict[str, Any],
) -> str:
    # Reuse the stable placement/objective hash and bind V2 spatial truth to it.
    base = v1._optimizer_fingerprint(
        selected_strategy,
        selected_objective,
        selected_result,
    )
    architecture = route.get("architecture_fingerprint") or "legacy"
    import hashlib

    return hashlib.sha256(
        f"{OPTIMIZER_VERSION}:{base}:{architecture}:{route.get('basis')}".encode()
    ).hexdigest()


def optimize_production_plan(
    products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    *,
    mode: str = "HYBRID",
    brand_side_rules: dict[str, str] | None = None,
    require_images: bool = True,
) -> dict[str, Any]:
    """Select the best hard-first candidate using real walk metres when possible."""
    source_products = deepcopy(products or [])
    baseline = generate_production_plan(
        products=deepcopy(source_products),
        layout=deepcopy(layout),
        store_dna=deepcopy(store_dna),
        mode=mode,
        brand_side_rules=brand_side_rules,
        scoring_config=None,
        require_images=require_images,
    )
    baseline_objective, baseline_route = objective_components(
        baseline,
        source_products,
        layout,
        store_dna,
    )
    baseline_summary = _candidate_summary(
        "baseline",
        baseline,
        baseline_objective,
        baseline_route,
    )

    if not baseline.get("solver_optimizer_allowed"):
        result = deepcopy(baseline)
        result["optimizer"] = {
            "optimizer_version": OPTIMIZER_VERSION,
            "allowed": False,
            "blocked_by_physical_truth": True,
            "baseline_preserved": True,
            "improved": False,
            "selected_strategy": "baseline",
            "baseline_objective": baseline_objective,
            "selected_objective": baseline_objective,
            "objective_delta": v1._objective_delta(
                baseline_objective,
                baseline_objective,
            ),
            "route_objective": baseline_route,
            "candidate_count": 1,
            "candidates": [baseline_summary],
            "fingerprint": _optimizer_fingerprint(
                "baseline",
                baseline_objective,
                baseline,
                baseline_route,
            ),
        }
        return result

    candidates: list[
        tuple[
            int,
            str,
            dict[str, Any],
            dict[str, float | int],
            dict[str, Any],
        ]
    ] = [(0, "baseline", baseline, baseline_objective, baseline_route)]

    for order, (strategy, scoring_config) in enumerate(STRATEGIES[1:], start=1):
        candidate = generate_production_plan(
            products=deepcopy(source_products),
            layout=deepcopy(layout),
            store_dna=deepcopy(store_dna),
            mode=mode,
            brand_side_rules=brand_side_rules,
            scoring_config=deepcopy(scoring_config),
            require_images=require_images,
        )
        candidate_objective, candidate_route = objective_components(
            candidate,
            source_products,
            layout,
            store_dna,
        )
        candidates.append(
            (
                order,
                strategy,
                candidate,
                candidate_objective,
                candidate_route,
            )
        )

    selected = min(
        candidates,
        key=lambda item: (v1.objective_key(item[3]), item[0]),
    )
    _, selected_strategy, selected_result, selected_objective, selected_route = selected

    if v1.objective_key(selected_objective) > v1.objective_key(baseline_objective):
        selected_strategy = "baseline"
        selected_result = baseline
        selected_objective = baseline_objective
        selected_route = baseline_route

    result = deepcopy(selected_result)
    result["optimizer"] = {
        "optimizer_version": OPTIMIZER_VERSION,
        "allowed": True,
        "blocked_by_physical_truth": False,
        "baseline_preserved": v1.objective_key(selected_objective)
        <= v1.objective_key(baseline_objective),
        "improved": v1.objective_key(selected_objective)
        < v1.objective_key(baseline_objective),
        "selected_strategy": selected_strategy,
        "baseline_objective": baseline_objective,
        "selected_objective": selected_objective,
        "objective_delta": v1._objective_delta(
            baseline_objective,
            selected_objective,
        ),
        "route_objective": selected_route,
        "candidate_count": len(candidates),
        "candidates": [
            _candidate_summary(strategy, candidate, objective, route)
            for _, strategy, candidate, objective, route in candidates
        ],
        "fingerprint": _optimizer_fingerprint(
            selected_strategy,
            selected_objective,
            selected_result,
            selected_route,
        ),
    }
    return result
