"""Evidence-bound commercial merchandising optimizer for PlanAI previews.

This module adds the retail decision layer that physical placement alone cannot
provide: category space allocation, assortment selection, substitution/cross-
elasticity awareness, facing optimization, and replenishment economics.

It is deliberately preview-only. Missing commercial evidence is surfaced rather
than invented, and no result grants production, purchasing, pricing, or finance
authority.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

COMMERCIAL_OPTIMIZER_VERSION = "planogram-commercial-merchandising-v1"
DEFAULT_WEIGHTS = {
    "sales": 1.0,
    "revenue": 0.8,
    "margin": 1.25,
    "replenishment": 1.0,
}
MAX_PRODUCTS = 10_000
MAX_SUBSTITUTION_EDGES = 50_000
MIN_EDGE_FOR_GROUP = 0.30


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _sku(row: dict[str, Any]) -> str:
    return _text(row.get("sku") or row.get("SKU") or row.get("barcode")).upper()


def _category(row: dict[str, Any]) -> str:
    return _text(
        row.get("category_l2")
        or row.get("category")
        or row.get("category_l1")
        or "UNCLASSIFIED"
    ).upper()


def _first_number(
    row: dict[str, Any],
    names: tuple[str, ...],
    default: float = 0.0,
) -> float:
    for name in names:
        if row.get(name) not in (None, ""):
            return _number(row.get(name), default)
    return default


def _product_metrics(row: dict[str, Any]) -> dict[str, Any]:
    sales = max(
        0.0,
        _first_number(
            row,
            ("sales_qty_7d", "sales_7d", "weekly_sales_qty", "sales"),
        ),
    )
    price = max(
        0.0,
        _first_number(row, ("unit_price", "selling_price", "price")),
    )
    margin = max(
        0.0,
        _first_number(
            row,
            ("unit_margin", "gross_margin_per_unit", "margin_per_unit"),
        ),
    )
    width = max(
        0.0,
        _first_number(
            row,
            ("width_cm", "product_width_cm", "product_width_in_cm"),
        ),
    )
    min_facing = max(
        1,
        _integer(row.get("min_facing") or row.get("minimum_facing"), 1),
    )
    max_facing = max(
        min_facing,
        min(
            24,
            _integer(row.get("max_facing") or row.get("maximum_facing"), 8),
        ),
    )
    elasticity = max(
        0.0,
        min(1.5, _number(row.get("space_elasticity"), 0.0)),
    )
    refill_cost = max(
        0.0,
        _number(row.get("replenishment_cost_per_visit"), 0.0),
    )
    refill_visits = max(
        0.0,
        _number(row.get("replenishments_per_day"), 0.0),
    )
    return {
        "sku": _sku(row),
        "category": _category(row),
        "width_cm": width,
        "sales_qty_7d": sales,
        "unit_price": price,
        "unit_margin": margin,
        "revenue_7d": sales * price,
        "gross_margin_7d": sales * margin,
        "min_facing": min_facing,
        "max_facing": max_facing,
        "space_elasticity": elasticity,
        "replenishment_cost_7d": refill_cost * refill_visits * 7.0,
        "substitution_group": (
            _text(row.get("substitution_group")).upper() or None
        ),
        "source": row,
    }


def _weights(raw: dict[str, Any] | None) -> dict[str, float]:
    result = dict(DEFAULT_WEIGHTS)
    for name, default_value in result.items():
        if isinstance(raw, dict) and raw.get(name) not in (None, ""):
            result[name] = max(0.0, _number(raw.get(name), default_value))
    return result


class _UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        if left not in self.parent or right not in self.parent:
            return
        a = self.find(left)
        b = self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def _substitution_graph(
    products: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[
    dict[str, str],
    dict[tuple[str, str], float],
    list[dict[str, Any]],
]:
    skus = [row["sku"] for row in products]
    uf = _UnionFind(skus)
    by_declared: dict[str, list[str]] = defaultdict(list)
    for row in products:
        if row["substitution_group"]:
            by_declared[row["substitution_group"]].append(row["sku"])
    for members in by_declared.values():
        for sku in members[1:]:
            uf.union(members[0], sku)

    edge_map: dict[tuple[str, str], float] = {}
    normalized_edges: list[dict[str, Any]] = []
    for index, edge in enumerate(edges[:MAX_SUBSTITUTION_EDGES]):
        left = _text(
            edge.get("sku_a") or edge.get("source_sku")
        ).upper()
        right = _text(
            edge.get("sku_b") or edge.get("target_sku")
        ).upper()
        elasticity = max(
            0.0,
            min(
                1.5,
                _number(edge.get("cross_elasticity"), -1.0),
            ),
        )
        if not left or not right or left == right or elasticity < 0:
            continue
        if left not in uf.parent or right not in uf.parent:
            continue
        key = tuple(sorted((left, right)))
        edge_map[key] = max(edge_map.get(key, 0.0), elasticity)
        normalized_edges.append(
            {
                "sku_a": key[0],
                "sku_b": key[1],
                "cross_elasticity": elasticity,
                "index": index,
            }
        )
        if elasticity >= MIN_EDGE_FOR_GROUP:
            uf.union(left, right)

    roots = {sku: uf.find(sku) for sku in skus}
    return roots, edge_map, normalized_edges


def _category_capacity(
    products: list[dict[str, Any]],
    *,
    explicit: dict[str, Any] | None,
    total_shelf_width_cm: float | None,
    weights: dict[str, float],
) -> tuple[dict[str, float], dict[str, Any]]:
    categories = sorted({row["category"] for row in products})
    explicit_map = {
        _text(name).upper(): max(0.0, _number(value))
        for name, value in (explicit or {}).items()
        if _text(name)
    }
    if explicit_map:
        return (
            {
                category: round(explicit_map.get(category, 0.0), 3)
                for category in categories
            },
            {
                "mode": "explicit_category_capacity",
                "total_width_cm": round(sum(explicit_map.values()), 3),
            },
        )

    total_width = max(0.0, _number(total_shelf_width_cm))
    if total_width <= 0:
        return (
            {category: 0.0 for category in categories},
            {"mode": "missing", "total_width_cm": 0.0},
        )

    aggregate: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for row in products:
        category = aggregate[row["category"]]
        category["sales"] += row["sales_qty_7d"]
        category["revenue"] += row["revenue_7d"]
        category["margin"] += row["gross_margin_7d"]

    totals = {
        metric: sum(aggregate[category][metric] for category in categories)
        for metric in ("sales", "revenue", "margin")
    }
    scores: dict[str, float] = {}
    for category in categories:
        score = 0.0
        for metric in ("sales", "revenue", "margin"):
            total = totals[metric]
            share = (
                aggregate[category][metric] / total
                if total > 0
                else 0.0
            )
            score += weights[metric] * share
        scores[category] = score

    total_score = sum(scores.values())
    if total_score <= 0:
        equal = total_width / max(len(categories), 1)
        capacity = {category: equal for category in categories}
    else:
        capacity = {
            category: total_width * scores[category] / total_score
            for category in categories
        }
    return (
        {
            category: round(value, 3)
            for category, value in capacity.items()
        },
        {
            "mode": "weighted_sales_revenue_margin",
            "total_width_cm": round(total_width, 3),
            "category_scores": {
                category: round(score, 6)
                for category, score in scores.items()
            },
        },
    )


def _value_at_facing(
    row: dict[str, Any],
    facing: int,
    weights: dict[str, float],
) -> dict[str, float]:
    facing = max(1, facing)
    demand_multiplier = (
        float(facing) ** row["space_elasticity"]
        if row["space_elasticity"] > 0
        else 1.0
    )
    predicted_sales = row["sales_qty_7d"] * demand_multiplier
    revenue = predicted_sales * row["unit_price"]
    margin = predicted_sales * row["unit_margin"]
    refill_cost = row["replenishment_cost_7d"] / facing
    objective = (
        weights["sales"] * predicted_sales
        + weights["revenue"] * revenue
        + weights["margin"] * margin
        - weights["replenishment"] * refill_cost
    )
    return {
        "predicted_sales_qty_7d": predicted_sales,
        "predicted_revenue_7d": revenue,
        "predicted_gross_margin_7d": margin,
        "replenishment_cost_7d": refill_cost,
        "objective": objective,
    }


def _optimize_category(
    rows: list[dict[str, Any]],
    *,
    capacity_cm: float,
    weights: dict[str, float],
    roots: dict[str, str],
) -> dict[str, Any]:
    selected: dict[str, int] = {}
    used = 0.0

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[roots[row["sku"]]].append(row)

    for members in sorted(
        groups.values(),
        key=lambda group: min(item["sku"] for item in group),
    ):
        if len(members) < 2:
            continue
        ranked = sorted(
            members,
            key=lambda row: (
                -_value_at_facing(
                    row,
                    row["min_facing"],
                    weights,
                )["objective"]
                / max(row["width_cm"] * row["min_facing"], 1e-9),
                row["sku"],
            ),
        )
        chosen = ranked[0]
        width_needed = chosen["width_cm"] * chosen["min_facing"]
        if (
            width_needed > 0
            and used + width_needed <= capacity_cm + 1e-9
        ):
            selected[chosen["sku"]] = chosen["min_facing"]
            used += width_needed

    by_sku = {row["sku"]: row for row in rows}
    while True:
        actions: list[tuple[float, str, str, int, float]] = []
        for row in rows:
            if row["width_cm"] <= 0:
                continue
            current = selected.get(row["sku"], 0)
            if current == 0:
                next_facing = row["min_facing"]
                width_needed = row["width_cm"] * next_facing
                delta = _value_at_facing(
                    row,
                    next_facing,
                    weights,
                )["objective"]
                action = "assort"
            elif current < row["max_facing"]:
                next_facing = current + 1
                width_needed = row["width_cm"]
                delta = (
                    _value_at_facing(
                        row,
                        next_facing,
                        weights,
                    )["objective"]
                    - _value_at_facing(
                        row,
                        current,
                        weights,
                    )["objective"]
                )
                action = "face"
            else:
                continue
            if (
                width_needed <= 0
                or used + width_needed > capacity_cm + 1e-9
            ):
                continue
            utility_per_cm = delta / width_needed
            if utility_per_cm <= 0:
                continue
            actions.append(
                (
                    -utility_per_cm,
                    row["sku"],
                    action,
                    next_facing,
                    width_needed,
                )
            )
        if not actions:
            break
        _, sku, _, next_facing, width_needed = min(actions)
        selected[sku] = next_facing
        used += width_needed

    plan: list[dict[str, Any]] = []
    objective_total = 0.0
    for sku, facing in sorted(selected.items()):
        row = by_sku[sku]
        value = _value_at_facing(row, facing, weights)
        objective_total += value["objective"]
        plan.append(
            {
                "sku": sku,
                "category": row["category"],
                "facing_count": facing,
                "used_width_cm": round(
                    row["width_cm"] * facing,
                    3,
                ),
                "space_elasticity": row["space_elasticity"],
                **{
                    name: round(number, 4)
                    for name, number in value.items()
                },
            }
        )
    return {
        "capacity_cm": round(capacity_cm, 3),
        "used_width_cm": round(used, 3),
        "utilization_pct": (
            round(used * 100.0 / capacity_cm, 2)
            if capacity_cm > 0
            else 0.0
        ),
        "selected_sku_count": len(plan),
        "objective_value": round(objective_total, 4),
        "facing_plan": plan,
    }


def optimize_commercial_merchandising(
    *,
    products: list[dict[str, Any]],
    category_capacity_cm: dict[str, Any] | None = None,
    total_shelf_width_cm: float | None = None,
    substitution_edges: list[dict[str, Any]] | None = None,
    objective_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Jointly select assortment and facings inside an evidence-bound space envelope."""
    raw_products = list(products or [])
    if not raw_products or len(raw_products) > MAX_PRODUCTS:
        return {
            "optimizer_version": COMMERCIAL_OPTIMIZER_VERSION,
            "available": False,
            "blockers": ["product_count_invalid"],
            "production_authority": False,
        }

    normalized = [_product_metrics(row) for row in raw_products]
    blockers: list[str] = []
    seen: set[str] = set()
    evidence_gaps: list[dict[str, Any]] = []
    for index, row in enumerate(normalized):
        if not row["sku"]:
            blockers.append(f"sku_missing:index:{index}")
            continue
        if row["sku"] in seen:
            blockers.append(f"duplicate_sku:{row['sku']}")
        seen.add(row["sku"])
        if row["width_cm"] <= 0:
            blockers.append(f"width_missing:{row['sku']}")
        missing = []
        source = row["source"]
        if not _text(source.get("commercial_source_ref")):
            missing.append("commercial_source_ref")
        if source.get("commercial_attested") is not True:
            missing.append("commercial_attested")
        for field in (
            "sales_qty_7d",
            "space_elasticity",
            "replenishment_cost_per_visit",
            "replenishments_per_day",
        ):
            if source.get(field) in (None, "") and not (
                field == "sales_qty_7d"
                and source.get("sales_7d") not in (None, "")
            ):
                missing.append(field)
        if (
            source.get("unit_margin") in (None, "")
            and source.get("gross_margin_per_unit") in (None, "")
        ):
            missing.append("unit_margin")
        if (
            source.get("unit_price") in (None, "")
            and source.get("selling_price") in (None, "")
            and source.get("price") in (None, "")
        ):
            missing.append("unit_price")
        if missing:
            evidence_gaps.append(
                {"sku": row["sku"], "missing": missing}
            )

    if blockers:
        return {
            "optimizer_version": COMMERCIAL_OPTIMIZER_VERSION,
            "available": False,
            "blockers": list(dict.fromkeys(blockers)),
            "production_authority": False,
            "commercial_evidence_complete": False,
        }

    weights = _weights(objective_weights)
    edges = list(substitution_edges or [])
    roots, edge_map, normalized_edges = _substitution_graph(
        normalized,
        edges,
    )
    capacity, allocation_meta = _category_capacity(
        normalized,
        explicit=category_capacity_cm,
        total_shelf_width_cm=total_shelf_width_cm,
        weights=weights,
    )
    if not capacity or sum(capacity.values()) <= 0:
        return {
            "optimizer_version": COMMERCIAL_OPTIMIZER_VERSION,
            "available": False,
            "blockers": ["shelf_capacity_missing"],
            "production_authority": False,
            "commercial_evidence_complete": not evidence_gaps,
            "evidence_gaps": evidence_gaps[:500],
        }

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        by_category[row["category"]].append(row)

    category_results: dict[str, dict[str, Any]] = {}
    selected_skus: set[str] = set()
    for category in sorted(by_category):
        result = _optimize_category(
            by_category[category],
            capacity_cm=capacity.get(category, 0.0),
            weights=weights,
            roots=roots,
        )
        category_results[category] = result
        selected_skus.update(
            item["sku"] for item in result["facing_plan"]
        )

    groups: dict[str, list[str]] = defaultdict(list)
    for sku, root in roots.items():
        groups[root].append(sku)
    substitution_groups = [
        {
            "group_id": root,
            "skus": sorted(members),
            "selected_skus": sorted(
                set(members) & selected_skus
            ),
        }
        for root, members in sorted(groups.items())
        if len(members) > 1
    ]

    excluded: list[dict[str, Any]] = []
    substitution_adjusted_unmet_sales = 0.0
    for row in normalized:
        if row["sku"] in selected_skus:
            continue
        alternatives = set(groups[roots[row["sku"]]]) & selected_skus
        best_cross = 0.0
        best_alt = None
        for alternative in sorted(alternatives):
            value = edge_map.get(
                tuple(sorted((row["sku"], alternative))),
                0.0,
            )
            if value > best_cross:
                best_cross = value
                best_alt = alternative
        recovered_share = min(best_cross, 1.0)
        adjusted_unmet = row["sales_qty_7d"] * (
            1.0 - recovered_share
        )
        substitution_adjusted_unmet_sales += adjusted_unmet
        excluded.append(
            {
                "sku": row["sku"],
                "category": row["category"],
                "sales_qty_7d": row["sales_qty_7d"],
                "covered_by_substitute": bool(alternatives),
                "best_selected_substitute_sku": best_alt,
                "explicit_cross_elasticity": (
                    round(best_cross, 4) if best_alt else None
                ),
                "substitution_adjusted_unmet_sales_qty_7d": round(
                    adjusted_unmet,
                    4,
                ),
            }
        )

    selected_plan = [
        item
        for category in sorted(category_results)
        for item in category_results[category]["facing_plan"]
    ]
    total_capacity = sum(
        row["capacity_cm"] for row in category_results.values()
    )
    total_used = sum(
        row["used_width_cm"] for row in category_results.values()
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "products": raw_products,
                "capacity": capacity,
                "substitution_edges": normalized_edges,
                "weights": weights,
                "selected_plan": selected_plan,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "optimizer_version": COMMERCIAL_OPTIMIZER_VERSION,
        "available": True,
        "preview_only": True,
        "production_authority": False,
        "assortment_authority": False,
        "pricing_authority": False,
        "finance_approved": False,
        "market_leadership_claim_allowed": False,
        "commercial_evidence_complete": not evidence_gaps,
        "evidence_gaps": evidence_gaps[:500],
        "objective_weights": weights,
        "category_space_allocation": allocation_meta,
        "category_capacity_cm": capacity,
        "category_results": category_results,
        "selected_assortment_count": len(selected_skus),
        "excluded_assortment_count": len(excluded),
        "selected_plan": selected_plan,
        "excluded_skus": excluded[:5_000],
        "substitution_groups": substitution_groups[:5_000],
        "substitution_edge_count": len(normalized_edges),
        "substitution_adjusted_unmet_sales_qty_7d": round(
            substitution_adjusted_unmet_sales,
            4,
        ),
        "total_capacity_cm": round(total_capacity, 3),
        "total_used_width_cm": round(total_used, 3),
        "space_utilization_pct": (
            round(total_used * 100.0 / total_capacity, 2)
            if total_capacity > 0
            else 0.0
        ),
        "commercial_fingerprint": fingerprint,
        "evidence_boundary": (
            "assortment/facing/category-space results use only supplied demand, margin, "
            "replenishment, elasticity and substitution evidence; realized sales, margin, "
            "stockout and labor effects require controlled backtest and field validation"
        ),
    }
