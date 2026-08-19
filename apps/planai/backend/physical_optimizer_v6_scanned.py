"""Bounded Architecture V2 allocation search for fingerprint-reviewed scanned stores.

This preview optimizer is intentionally separate from the V1 production-facing
V3/V4/V5 line. It accepts only physically complete products, a catalog-bound
scanned fixture layout, reviewed Architecture V2 geometry and anonymized baskets.
It generates deterministic feasible allocations, then ranks them with the real
Architecture V2 picker-tour simulator. It does not claim global optimality or
production/installation authority.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from itertools import product as cartesian_product
from typing import Any

import architecture_truth_v2
import objective_v3
import picker_tour_simulation_v2
from physical_truth import layout_physical_truth_report, product_physical_truth_report

OPTIMIZER_VERSION = "scanned-physical-optimizer-v6-preview"
MAX_CANDIDATES = 24
HEAVY_GRAMS = 4000.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _sku(row: dict[str, Any]) -> str:
    return str(row.get("sku") or row.get("SKU") or "").strip().upper()


def _text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _sales(row: dict[str, Any]) -> float:
    return max(
        0.0,
        _num(
            row.get("weekly_sales")
            or row.get("sales_7d")
            or row.get("sales")
            or row.get("avg_sales"),
            0.0,
        ),
    )


def _storage(row: dict[str, Any]) -> str:
    return str(row.get("storage_type") or "").strip().upper()


def _demand(orders: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for order in orders:
        for raw in order.get("skus") or []:
            sku = str(raw or "").strip().upper()
            if sku:
                counts[sku] = counts.get(sku, 0) + 1
    return counts


def _affinity(orders: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    graph: dict[str, dict[str, int]] = {}
    for order in orders:
        unique = sorted({str(raw or "").strip().upper() for raw in order.get("skus") or [] if str(raw or "").strip()})
        for left_index, left in enumerate(unique):
            graph.setdefault(left, {})
            for right in unique[left_index + 1 :]:
                graph.setdefault(right, {})
                graph[left][right] = graph[left].get(right, 0) + 1
                graph[right][left] = graph[right].get(left, 0) + 1
    return graph


def _picker_entry(store_dna: dict[str, Any]) -> tuple[float, float] | None:
    architecture = (store_dna or {}).get("architecture") or {}
    for row in architecture.get("elements") or []:
        if row.get("element_type") == "picker_entry":
            return (_num(row.get("center_x_m")), _num(row.get("center_y_m")))
    return None


def _module_rows(layout: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for aisle in layout.get("aisles") or []:
        aisle_id = str(aisle.get("aisle_id") or "")
        for module in aisle.get("modules") or []:
            rows.append((aisle_id, module))
    return rows


def _shelf_refs(layout: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for aisle_id, module in _module_rows(layout):
        for shelf in module.get("shelves") or []:
            rows.append(
                {
                    "aisle_id": aisle_id,
                    "module": module,
                    "shelf": shelf,
                    "remaining_width_cm": _num(shelf.get("shelf_width_cm")),
                    "placed_skus": [],
                }
            )
    return rows


def _route_rank(module: dict[str, Any], entry: tuple[float, float]) -> float:
    dx = _num(module.get("x_m")) - entry[0]
    dy = _num(module.get("y_m")) - entry[1]
    return (dx * dx + dy * dy) ** 0.5


def _profiles() -> list[dict[str, float]]:
    profiles: list[dict[str, float]] = []
    for route_weight, affinity_weight, ergonomic_weight in cartesian_product(
        (0.7, 1.1, 1.6, 2.2),
        (0.0, 0.45, 0.9),
        (0.55, 1.05),
    ):
        profiles.append(
            {
                "route_weight": route_weight,
                "affinity_weight": affinity_weight,
                "ergonomic_weight": ergonomic_weight,
            }
        )
    return profiles[:MAX_CANDIDATES]


def _profile_id(profile: dict[str, float]) -> str:
    return (
        f"r{profile['route_weight']:.2f}-"
        f"a{profile['affinity_weight']:.2f}-"
        f"e{profile['ergonomic_weight']:.2f}"
    )


def _feasible(product: dict[str, Any], shelf: dict[str, Any], remaining_width_cm: float) -> bool:
    width = _num(product.get("width_cm"))
    height = _num(product.get("height_cm"))
    depth = _num(product.get("depth_cm"))
    weight_kg = _num(product.get("weight_g")) / 1000.0
    if min(width, height, depth) <= 0 or weight_kg <= 0:
        return False
    if width > remaining_width_cm:
        return False
    if height > _num(shelf.get("shelf_height_cm")):
        return False
    if depth > _num(shelf.get("shelf_depth_cm")):
        return False
    if weight_kg > _num(shelf.get("max_weight_kg")):
        return False
    allowed = str(shelf.get("allowed_storage_type") or "").strip().upper()
    return allowed == _storage(product)


def _facings(product: dict[str, Any], demand_count: int, max_demand: int, remaining_width_cm: float) -> int:
    width = _num(product.get("width_cm"))
    if width <= 0:
        return 0
    ratio = demand_count / max(1, max_demand)
    target = 4 if ratio >= 0.75 else 3 if ratio >= 0.45 else 2 if ratio >= 0.2 else 1
    return max(1, min(target, int(remaining_width_cm // width)))


def _shelf_score(
    *,
    product: dict[str, Any],
    shelf_ref: dict[str, Any],
    entry: tuple[float, float],
    demand_count: int,
    graph: dict[str, dict[str, int]],
    profile: dict[str, float],
) -> float:
    module = shelf_ref["module"]
    shelf = shelf_ref["shelf"]
    route = _route_rank(module, entry)
    sku = _sku(product)
    affinity_value = sum(
        graph.get(sku, {}).get(other, 0) for other in shelf_ref["placed_skus"]
    )
    zone = str(shelf.get("zone_type") or "").lower()
    heavy = _num(product.get("weight_g")) >= HEAVY_GRAMS
    ergonomic_penalty = 0.0
    if heavy and zone not in {"bottom", "lower"}:
        ergonomic_penalty = 12.0
    elif not heavy and zone == "bottom":
        ergonomic_penalty = 1.5
    category = _text(product, "category", "category_name", "subcategory")
    category_neighbors = 0
    if category:
        category_neighbors = sum(
            1
            for placed in shelf.get("products") or []
            if _text(placed, "category", "category_name", "subcategory") == category
        )
    slack_ratio = shelf_ref["remaining_width_cm"] / max(
        _num(shelf.get("shelf_width_cm")),
        1.0,
    )
    return (
        route * (1.0 + demand_count) * profile["route_weight"]
        - affinity_value * profile["affinity_weight"]
        - category_neighbors * 0.55
        + ergonomic_penalty * profile["ergonomic_weight"]
        + slack_ratio * 0.2
    )


def _ordered_products(
    products: list[dict[str, Any]],
    demand: dict[str, int],
    graph: dict[str, dict[str, int]],
    profile: dict[str, float],
) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[float, float, float, str]:
        sku = _sku(row)
        centrality = sum(graph.get(sku, {}).values())
        priority = (
            demand.get(sku, 0) * profile["route_weight"]
            + centrality * profile["affinity_weight"]
            + _sales(row) * 0.04
        )
        return (-priority, -_sales(row), -_num(row.get("weight_g")), sku)

    return sorted((deepcopy(row) for row in products), key=key)


def _allocate_candidate(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    entry: tuple[float, float],
    demand: dict[str, int],
    graph: dict[str, dict[str, int]],
    profile: dict[str, float],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidate = deepcopy(layout)
    shelves = _shelf_refs(candidate)
    unplaced: list[dict[str, Any]] = []
    max_demand = max(demand.values(), default=1)

    for row in _ordered_products(products, demand, graph, profile):
        feasible = [
            shelf_ref
            for shelf_ref in shelves
            if _feasible(row, shelf_ref["shelf"], shelf_ref["remaining_width_cm"])
        ]
        if not feasible:
            unplaced.append(row)
            continue
        selected = min(
            feasible,
            key=lambda shelf_ref: _shelf_score(
                product=row,
                shelf_ref=shelf_ref,
                entry=entry,
                demand_count=demand.get(_sku(row), 0),
                graph=graph,
                profile=profile,
            ),
        )
        facing_count = _facings(
            row,
            demand.get(_sku(row), 0),
            max_demand,
            selected["remaining_width_cm"],
        )
        if facing_count <= 0:
            unplaced.append(row)
            continue
        placed = deepcopy(row)
        placed["facing_count"] = facing_count
        selected["shelf"].setdefault("products", []).append(placed)
        selected["placed_skus"].append(_sku(row))
        selected["remaining_width_cm"] -= _num(row.get("width_cm")) * facing_count
    return candidate, unplaced


def _brand_fragmentation(planogram: dict[str, Any]) -> int:
    brand_modules: dict[str, set[str]] = {}
    for aisle_id, module in _module_rows(planogram):
        module_key = f"{aisle_id}::{module.get('module_id')}"
        for shelf in module.get("shelves") or []:
            for product in shelf.get("products") or []:
                brand = _text(product, "brand", "brand_name")
                if brand:
                    brand_modules.setdefault(brand, set()).add(module_key)
    return sum(max(0, len(modules) - 1) for modules in brand_modules.values())


def _objective(
    *,
    products: list[dict[str, Any]],
    unplaced: list[dict[str, Any]],
    planogram: dict[str, Any],
    tour: dict[str, Any],
) -> dict[str, Any]:
    unplaced_skus = {_sku(row) for row in unplaced}
    weighted_unplaced_sales = sum(
        _sales(row) for row in products if _sku(row) in unplaced_skus
    )
    coverage = _num(tour.get("coverage_pct"), 0.0)
    return {
        "hard_violation_count": 0,
        "weighted_unplaced_sales": round(weighted_unplaced_sales, 6),
        "unplaced_sku_count": len(unplaced_skus),
        "tour_unsimulated_order_count": int(tour.get("unsimulated_order_count") or 0),
        "tour_p95_m": _num(tour.get("p95_m"), float("inf")),
        "tour_average_m": _num(tour.get("average_m"), float("inf")),
        "coverage_shortfall": round(max(0.0, 100.0 - coverage), 6),
        "brand_fragmentation": _brand_fragmentation(planogram),
        "capacity_pressure": 0.0,
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def optimize_scanned_store(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    max_candidates: int = MAX_CANDIDATES,
) -> dict[str, Any]:
    """Allocate products on reviewed Architecture V2 scanned fixture truth."""
    max_candidates = max(1, min(int(max_candidates), MAX_CANDIDATES))
    product_truth = product_physical_truth_report(products, require_images=False)
    layout_truth = layout_physical_truth_report(layout)
    architecture_truth = architecture_truth_v2.architecture_truth_report_v2(store_dna)
    blockers = [
        *list(product_truth.get("blockers") or []),
        *list(layout_truth.get("blockers") or []),
        *list(architecture_truth.get("blockers") or []),
    ]
    entry = _picker_entry(store_dna)
    if entry is None:
        blockers.append("scanned_optimizer_picker_entry_missing")
    if not orders:
        blockers.append("scanned_optimizer_order_baskets_required")
    blockers = list(dict.fromkeys(blockers))
    if blockers:
        return {
            "optimizer_version": OPTIMIZER_VERSION,
            "allowed": False,
            "blockers": blockers,
            "production_authority": False,
            "installation_approved": False,
            "global_optimum_claim": False,
        }

    assert entry is not None
    demand = _demand(orders)
    graph = _affinity(orders)
    candidate_rows: list[dict[str, Any]] = []
    for profile in _profiles()[:max_candidates]:
        planogram, unplaced = _allocate_candidate(
            products=products,
            layout=layout,
            entry=entry,
            demand=demand,
            graph=graph,
            profile=profile,
        )
        tour = picker_tour_simulation_v2.simulate_picker_tours_v2(
            products=products,
            planogram=planogram,
            layout=layout,
            store_dna=store_dna,
            orders=orders,
        )
        objective = _objective(
            products=products,
            unplaced=unplaced,
            planogram=planogram,
            tour=tour,
        )
        candidate_rows.append(
            {
                "profile_id": _profile_id(profile),
                "profile": profile,
                "planogram": planogram,
                "unplaced_skus": sorted({_sku(row) for row in unplaced}),
                "tour": tour,
                "objective": objective,
                "objective_key": list(objective_v3.objective_key(objective)),
            }
        )

    selected = min(
        candidate_rows,
        key=lambda row: objective_v3.objective_key(row["objective"]),
    )
    summaries = [
        {
            "profile_id": row["profile_id"],
            "profile": row["profile"],
            "objective": row["objective"],
            "objective_key": row["objective_key"],
            "tour": {
                "order_count": row["tour"].get("order_count"),
                "coverage_pct": row["tour"].get("coverage_pct"),
                "average_m": row["tour"].get("average_m"),
                "p95_m": row["tour"].get("p95_m"),
            },
            "unplaced_skus": row["unplaced_skus"],
        }
        for row in candidate_rows
    ]
    result = {
        "optimizer_version": OPTIMIZER_VERSION,
        "allowed": True,
        "candidate_count": len(candidate_rows),
        "selected_profile_id": selected["profile_id"],
        "selected_objective": selected["objective"],
        "selected_tour": selected["tour"],
        "planogram": selected["planogram"],
        "unplaced_skus": selected["unplaced_skus"],
        "candidates": summaries,
        "physical_truth": {
            "products": product_truth,
            "layout": layout_truth,
            "architecture_v2": architecture_truth,
        },
        "production_authority": False,
        "store_dna_authority": False,
        "installation_approved": False,
        "relocation_execution_allowed": False,
        "capex_approved": False,
        "global_optimum_claim": False,
        "field_evidence": False,
        "evidence_boundary": (
            "selected allocation is the best candidate in a bounded deterministic search on "
            "fingerprint-reviewed Architecture V2 geometry and anonymized baskets; it is not a "
            "global optimum, approved Store DNA, installation instruction or production plan"
        ),
    }
    result["optimizer_fingerprint"] = _fingerprint(
        {
            "version": OPTIMIZER_VERSION,
            "products": products,
            "layout": layout,
            "store_dna": store_dna,
            "orders": orders,
            "selected_profile_id": selected["profile_id"],
            "selected_objective": selected["objective"],
        }
    )
    return result
