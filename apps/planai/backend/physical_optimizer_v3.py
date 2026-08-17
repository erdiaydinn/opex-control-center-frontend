"""Basket-aware deterministic Planogram optimizer above V2 physical truth.

V3 adds measured picker-tour performance as a candidate discriminator without
allowing route gains to sacrifice hard constraints or high-sales placement.
Observed/test baskets are caller supplied; absence of baskets delegates to V2
and never fabricates demand evidence.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import physical_optimizer as v1
import physical_optimizer_v2 as v2
from physical_engine import generate_production_plan
from picker_tour_simulation import simulate_picker_tours

OPTIMIZER_VERSION = "physical-plan-optimizer-v3-picker-tour"
STRATEGIES = v2.STRATEGIES

TOUR_OBJECTIVE_ORDER = (
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


def _normalized_order_skus(order: dict[str, Any]) -> list[str]:
    raw = order.get("skus")
    if raw is None:
        raw = order.get("items")
    if not isinstance(raw, list):
        return []
    values = []
    for item in raw:
        if isinstance(item, dict):
            sku = item.get("sku") or item.get("SKU")
        else:
            sku = item
        text = str(sku or "").strip().upper()
        if text:
            values.append(text)
    return sorted(values)


def order_basket_fingerprint(orders: list[dict[str, Any]]) -> str:
    """Fingerprint basket composition without persisting raw order identifiers."""
    baskets = sorted(
        (_normalized_order_skus(order) for order in orders),
        key=lambda row: (len(row), row),
    )
    payload = json.dumps(
        baskets,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tour_summary(report: dict[str, Any]) -> dict[str, Any]:
    orders = report.get("orders") or {}
    distance = report.get("distance_m") or {}
    input_count = int(orders.get("input_count") or 0)
    simulated = int(orders.get("simulated_count") or 0)
    return {
        "available": bool(report.get("available")),
        "input_order_count": input_count,
        "simulated_order_count": simulated,
        "coverage_pct": float(orders.get("coverage_pct") or 0.0),
        "unsimulated_order_count": max(0, input_count - simulated),
        "average_m": float(distance.get("average") or 0.0),
        "p50_m": float(distance.get("p50") or 0.0),
        "p90_m": float(distance.get("p90") or 0.0),
        "p95_m": float(distance.get("p95") or 0.0),
        "max_m": float(distance.get("max") or 0.0),
    }


def objective_components(
    result: dict[str, Any],
    source_products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    orders: list[dict[str, Any]],
) -> tuple[dict[str, float | int], dict[str, Any], dict[str, Any]]:
    base, route = v2.objective_components(
        result,
        source_products,
        layout,
        store_dna,
    )
    tour_report = simulate_picker_tours(
        result=result,
        layout=layout or {},
        store_dna=store_dna or {},
        orders=orders,
    )
    tour = _tour_summary(tour_report)
    components = dict(base)
    components.update(
        {
            "tour_unsimulated_order_count": int(tour["unsimulated_order_count"]),
            "tour_p95_m": float(tour["p95_m"]),
            "tour_average_m": float(tour["average_m"]),
        }
    )
    return components, route, tour


def objective_key(components: dict[str, float | int]) -> tuple[float, ...]:
    return tuple(float(components[name]) for name in TOUR_OBJECTIVE_ORDER)


def _candidate_summary(
    strategy: str,
    result: dict[str, Any],
    objective: dict[str, float | int],
    route: dict[str, Any],
    tour: dict[str, Any],
) -> dict[str, Any]:
    summary = v1._candidate_summary(strategy, result, objective)
    summary.update(
        {
            "route_basis": route.get("basis"),
            "tour_available": tour["available"],
            "tour_coverage_pct": tour["coverage_pct"],
            "tour_p95_m": tour["p95_m"],
            "tour_average_m": tour["average_m"],
            "tour_unsimulated_order_count": tour["unsimulated_order_count"],
        }
    )
    return summary


def _fallback_to_v2(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    mode: str,
    brand_side_rules: dict[str, str] | None,
    require_images: bool,
    reason: str,
    basket_fingerprint: str | None,
) -> dict[str, Any]:
    result = v2.optimize_production_plan(
        products=products,
        layout=layout,
        store_dna=store_dna,
        mode=mode,
        brand_side_rules=brand_side_rules,
        require_images=require_images,
    )
    result["picker_tour_optimizer"] = {
        "optimizer_version": OPTIMIZER_VERSION,
        "allowed": False,
        "effective": False,
        "reason": reason,
        "production_evidence": False,
        "order_basket_fingerprint": basket_fingerprint,
        "selected_by": "physical-plan-optimizer-v2",
    }
    return result


def optimize_production_plan(
    products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    *,
    orders: list[dict[str, Any]] | None = None,
    mode: str = "HYBRID",
    brand_side_rules: dict[str, str] | None = None,
    require_images: bool = True,
) -> dict[str, Any]:
    source_products = deepcopy(products or [])
    source_orders = deepcopy(orders or [])
    basket_fingerprint = (
        order_basket_fingerprint(source_orders) if source_orders else None
    )

    if not source_orders:
        return _fallback_to_v2(
            products=source_products,
            layout=deepcopy(layout),
            store_dna=deepcopy(store_dna),
            mode=mode,
            brand_side_rules=brand_side_rules,
            require_images=require_images,
            reason="order_baskets_missing",
            basket_fingerprint=None,
        )

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
        result["picker_tour_optimizer"] = {
            "optimizer_version": OPTIMIZER_VERSION,
            "allowed": False,
            "effective": False,
            "reason": "physical_truth_blocks_optimizer",
            "production_evidence": False,
            "order_basket_fingerprint": basket_fingerprint,
            "selected_by": "baseline",
        }
        return result

    baseline_objective, baseline_route, baseline_tour = objective_components(
        baseline,
        source_products,
        layout,
        store_dna,
        source_orders,
    )
    if not baseline_tour["available"]:
        return _fallback_to_v2(
            products=source_products,
            layout=deepcopy(layout),
            store_dna=deepcopy(store_dna),
            mode=mode,
            brand_side_rules=brand_side_rules,
            require_images=require_images,
            reason="picker_tour_simulation_unavailable",
            basket_fingerprint=basket_fingerprint,
        )

    candidates: list[
        tuple[
            int,
            str,
            dict[str, Any],
            dict[str, float | int],
            dict[str, Any],
            dict[str, Any],
        ]
    ] = [
        (
            0,
            "baseline",
            baseline,
            baseline_objective,
            baseline_route,
            baseline_tour,
        )
    ]

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
        objective, route, tour = objective_components(
            candidate,
            source_products,
            layout,
            store_dna,
            source_orders,
        )
        candidates.append((order, strategy, candidate, objective, route, tour))

    selected = min(
        candidates,
        key=lambda item: (objective_key(item[3]), item[0]),
    )
    _, selected_strategy, selected_result, selected_objective, selected_route, selected_tour = selected

    if objective_key(selected_objective) > objective_key(baseline_objective):
        selected_strategy = "baseline"
        selected_result = baseline
        selected_objective = baseline_objective
        selected_route = baseline_route
        selected_tour = baseline_tour

    result = deepcopy(selected_result)
    result["picker_tour_optimizer"] = {
        "optimizer_version": OPTIMIZER_VERSION,
        "allowed": True,
        "effective": True,
        "production_evidence": False,
        "evidence_boundary": (
            "selection reflects only caller-supplied baskets and measured geometry; "
            "field acceptance remains external"
        ),
        "order_basket_fingerprint": basket_fingerprint,
        "objective_order": list(TOUR_OBJECTIVE_ORDER),
        "baseline_preserved": objective_key(selected_objective)
        <= objective_key(baseline_objective),
        "improved": objective_key(selected_objective)
        < objective_key(baseline_objective),
        "selected_strategy": selected_strategy,
        "baseline_objective": baseline_objective,
        "selected_objective": selected_objective,
        "selected_tour": selected_tour,
        "selected_route_basis": selected_route.get("basis"),
        "candidate_count": len(candidates),
        "candidates": [
            _candidate_summary(strategy, candidate, objective, route, tour)
            for _, strategy, candidate, objective, route, tour in candidates
        ],
    }
    return result
