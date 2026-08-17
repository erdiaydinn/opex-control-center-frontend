"""Deterministic plan-level optimizer above the physical-truth gate.

Master Roadmap 25 deliberately keeps ``engine.py`` as the foundation allocator.
Every candidate is generated through ``physical_engine.generate_production_plan``
so optimizer tuning can never bypass approved dimensions, Store DNA, fixture
capacity or operational physical validation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from physical_engine import generate_production_plan

OPTIMIZER_VERSION = "physical-plan-optimizer-v1"

# Candidate order is part of the deterministic contract. Baseline is always
# candidate zero and wins exact objective ties.
STRATEGIES: tuple[tuple[str, dict[str, float] | None], ...] = (
    ("baseline", None),
    (
        "route_focus",
        {
            "sales": 1.50,
            "picking": 1.70,
            "ergonomics": 1.15,
            "balance": 0.90,
        },
    ),
    (
        "coverage_focus",
        {
            "coverage": 1.65,
            "refill": 1.20,
            "sales": 1.45,
            "fixture": 1.45,
        },
    ),
    (
        "capacity_focus",
        {
            "fixture": 1.75,
            "balance": 1.25,
            "risk": 1.30,
            "coverage": 1.20,
        },
    ),
    (
        "brand_block_focus",
        {
            "brand_cluster": 1.85,
            "sales": 1.40,
            "picking": 1.25,
            "balance": 0.90,
        },
    ),
)

OBJECTIVE_ORDER = (
    "hard_violation_count",
    "weighted_unplaced_sales",
    "unplaced_sku_count",
    "coverage_shortfall",
    "picking_route_cost",
    "brand_fragmentation",
    "capacity_pressure",
)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _sku(row: dict[str, Any]) -> str:
    return str(row.get("sku") or row.get("SKU") or "").strip()


def _sales(row: dict[str, Any]) -> float:
    for field in (
        "sales_qty_7d",
        "sales_7d",
        "qty_7d",
        "weekly_sales",
        "sales_qty",
    ):
        value = _num(row.get(field), -1.0)
        if value >= 0:
            return value
    return 0.0


def _iter_shelves(planogram: dict[str, Any] | None):
    aisles = (planogram or {}).get("aisles", []) or []
    for aisle_index, aisle in enumerate(aisles, start=1):
        for module_index, module in enumerate(
            aisle.get("modules", []) or [],
            start=1,
        ):
            for shelf_index, shelf in enumerate(
                module.get("shelves", []) or [],
                start=1,
            ):
                yield aisle_index, module_index, shelf_index, aisle, module, shelf


def _iter_placed(planogram: dict[str, Any] | None):
    for aisle_index, module_index, shelf_index, aisle, module, shelf in _iter_shelves(
        planogram
    ):
        for product in shelf.get("products", []) or []:
            yield aisle_index, module_index, shelf_index, aisle, module, shelf, product


def _hard_violations(result: dict[str, Any]) -> int:
    diagnostics = result.get("diagnostics") or {}
    strict = int(
        _num((diagnostics.get("summary") or {}).get("strict_rule_violation_count"), 0)
    )
    operational = int(
        _num(
            (result.get("operational_physical_validation") or {}).get(
                "violation_count"
            ),
            0,
        )
    )
    blockers = len((result.get("physical_truth") or {}).get("blockers") or [])
    return strict + operational + blockers


def _weighted_unplaced_sales(
    result: dict[str, Any],
    source_products: Iterable[dict[str, Any]],
) -> float:
    sales_by_sku = {_sku(row): _sales(row) for row in source_products}
    return round(
        sum(
            sales_by_sku.get(_sku(row), 0.0)
            for row in result.get("unplaced") or []
        ),
        6,
    )


def _coverage_shortfall(result: dict[str, Any]) -> float:
    shortfall = 0.0
    for *_, product in _iter_placed(result.get("planogram")):
        coverage = product.get("coverage_days")
        if coverage is None:
            continue
        shortfall += max(0.0, 1.0 - _num(coverage)) * max(1.0, _sales(product))
    return round(shortfall, 6)


def _picking_route_cost(result: dict[str, Any]) -> float:
    cost = 0.0
    for (
        aisle_index,
        module_index,
        shelf_index,
        aisle,
        module,
        _,
        product,
    ) in _iter_placed(result.get("planogram")):
        aisle_rank = _num(aisle.get("row"), float(aisle_index))
        aisle_position = _num(aisle.get("position"), 0.0)
        module_position = _num(module.get("position"), float(module_index))
        route_rank = (
            aisle_rank * 100.0
            + aisle_position * 10.0
            + module_position
            + shelf_index / 100.0
        )
        cost += route_rank * max(1.0, _sales(product))
    return round(cost, 6)


def _brand_fragmentation(result: dict[str, Any]) -> int:
    locations: dict[str, set[tuple[str, str]]] = {}
    for _, _, _, aisle, module, _, product in _iter_placed(result.get("planogram")):
        brand = str(
            product.get("brand") or product.get("brand_name") or ""
        ).strip().lower()
        if not brand:
            continue
        location = (str(aisle.get("aisle_id")), str(module.get("module_id")))
        locations.setdefault(brand, set()).add(location)
    return sum(max(0, len(items) - 1) for items in locations.values())


def _capacity_pressure(result: dict[str, Any]) -> float:
    pressure = 0.0
    for *_, shelf in _iter_shelves(result.get("planogram")):
        width = max(1.0, _num(shelf.get("shelf_width_cm"), 100.0))
        used = _num(shelf.get("used_width_cm", shelf.get("used", 0.0)), 0.0)
        utilization = used / width
        pressure += max(0.0, utilization - 0.90) * 100.0
        pressure += sum(
            1.0
            for product in shelf.get("products", []) or []
            if product.get("facing_reduced")
        )
    return round(pressure, 6)


def objective_components(
    result: dict[str, Any],
    source_products: Iterable[dict[str, Any]],
) -> dict[str, float | int]:
    """Return the hard-first objective used for deterministic candidate ranking."""
    return {
        "hard_violation_count": _hard_violations(result),
        "weighted_unplaced_sales": _weighted_unplaced_sales(result, source_products),
        "unplaced_sku_count": len(result.get("unplaced") or []),
        "coverage_shortfall": _coverage_shortfall(result),
        "picking_route_cost": _picking_route_cost(result),
        "brand_fragmentation": _brand_fragmentation(result),
        "capacity_pressure": _capacity_pressure(result),
    }


def objective_key(components: dict[str, float | int]) -> tuple[float, ...]:
    return tuple(float(components[name]) for name in OBJECTIVE_ORDER)


def _candidate_summary(
    strategy: str,
    result: dict[str, Any],
    objective: dict[str, float | int],
) -> dict[str, Any]:
    summary = result.get("summary") or {}
    return {
        "strategy": strategy,
        "objective": objective,
        "production_ready": bool(result.get("production_ready")),
        "publishable": bool(result.get("publishable")),
        "placed": int(_num(summary.get("placed"), 0)),
        "unplaced": int(_num(summary.get("unplaced"), 0)),
    }


def _plan_fingerprint(result: dict[str, Any]) -> str:
    placements = []
    for _, _, _, aisle, module, shelf, product in _iter_placed(
        result.get("planogram")
    ):
        placements.append(
            {
                "sku": _sku(product),
                "aisle_id": str(aisle.get("aisle_id")),
                "module_id": str(module.get("module_id")),
                "shelf_no": str(shelf.get("shelf_no")),
                "facing": int(
                    _num(product.get("facing_count", product.get("facing")), 0)
                ),
            }
        )
    placements.sort(
        key=lambda row: (
            row["sku"],
            row["aisle_id"],
            row["module_id"],
            row["shelf_no"],
            row["facing"],
        )
    )
    payload = json.dumps(
        placements,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _optimizer_fingerprint(
    selected_strategy: str,
    selected_objective: dict[str, float | int],
    selected_result: dict[str, Any],
) -> str:
    payload = {
        "optimizer_version": OPTIMIZER_VERSION,
        "strategy": selected_strategy,
        "objective": selected_objective,
        "plan_fingerprint": _plan_fingerprint(selected_result),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _objective_delta(
    baseline: dict[str, float | int],
    selected: dict[str, float | int],
) -> dict[str, float]:
    return {
        name: round(float(selected[name]) - float(baseline[name]), 6)
        for name in OBJECTIVE_ORDER
    }


def optimize_production_plan(
    products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    *,
    mode: str = "HYBRID",
    brand_side_rules: dict[str, str] | None = None,
    require_images: bool = True,
) -> dict[str, Any]:
    """Select the best deterministic candidate without ever degrading baseline.

    If physical truth is incomplete, no alternative candidate is generated. The
    blocked baseline is returned with explicit optimizer metadata so callers
    cannot mistake optimizer availability for production authority.
    """
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
    baseline_objective = objective_components(baseline, source_products)
    baseline_summary = _candidate_summary("baseline", baseline, baseline_objective)

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
            "objective_delta": _objective_delta(
                baseline_objective,
                baseline_objective,
            ),
            "candidate_count": 1,
            "candidates": [baseline_summary],
            "fingerprint": _optimizer_fingerprint(
                "baseline",
                baseline_objective,
                baseline,
            ),
        }
        return result

    candidates: list[
        tuple[int, str, dict[str, Any], dict[str, float | int]]
    ] = [(0, "baseline", baseline, baseline_objective)]
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
        candidates.append(
            (
                order,
                strategy,
                candidate,
                objective_components(candidate, source_products),
            )
        )

    selected = min(candidates, key=lambda item: (objective_key(item[3]), item[0]))
    _, selected_strategy, selected_result, selected_objective = selected

    # Defensive invariant: because baseline is always candidate zero, selection
    # can never be lexicographically worse than it. Fail closed if that contract
    # is ever violated by a future refactor.
    if objective_key(selected_objective) > objective_key(baseline_objective):
        selected_strategy = "baseline"
        selected_result = baseline
        selected_objective = baseline_objective

    result = deepcopy(selected_result)
    result["optimizer"] = {
        "optimizer_version": OPTIMIZER_VERSION,
        "allowed": True,
        "blocked_by_physical_truth": False,
        "baseline_preserved": objective_key(selected_objective)
        <= objective_key(baseline_objective),
        "improved": objective_key(selected_objective) < objective_key(baseline_objective),
        "selected_strategy": selected_strategy,
        "baseline_objective": baseline_objective,
        "selected_objective": selected_objective,
        "objective_delta": _objective_delta(baseline_objective, selected_objective),
        "candidate_count": len(candidates),
        "candidates": [
            _candidate_summary(strategy, candidate, objective)
            for _, strategy, candidate, objective in candidates
        ],
        "fingerprint": _optimizer_fingerprint(
            selected_strategy,
            selected_objective,
            selected_result,
        ),
    }
    return result
