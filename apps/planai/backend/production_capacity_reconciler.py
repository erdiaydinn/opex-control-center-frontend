"""Deterministic full-depth shelf-capacity reconciliation for production previews.

The foundation allocator historically tracks shelf mass per front-facing unit.
This module reconciles generated placements against the physical stack actually
carried by a shelf: ``facing_count * depth_units * unit_weight``. It may reduce
facings, but it never invents dimensions, moves SKUs, drops the last facing, or
grants production authority. Irreducible or incomplete evidence fails closed.
"""
from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

WIDTH_BUFFER_FACTOR = 1.10
RECONCILER_VERSION = "planogram-production-capacity-reconciler-v1"


def _num(value: Any, default: float = 0.0) -> float:
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


def _sku(product: dict[str, Any]) -> str:
    return str(product.get("sku") or product.get("SKU") or "").strip().upper()


def _sales(product: dict[str, Any]) -> float:
    for field in ("sales_qty_7d", "sales_7d", "weekly_sales", "sales_qty"):
        value = _num(product.get(field), -1.0)
        if value >= 0:
            return value
    return 0.0


def depth_units(product: dict[str, Any], shelf: dict[str, Any]) -> int:
    depth_cm = _num(product.get("depth_cm"))
    shelf_depth_cm = _num(shelf.get("shelf_depth_cm"))
    if depth_cm <= 0 or shelf_depth_cm <= 0 or depth_cm > shelf_depth_cm + 1e-9:
        return 0
    return max(1, math.floor(shelf_depth_cm / depth_cm))


def stack_weight_per_facing_kg(product: dict[str, Any], shelf: dict[str, Any]) -> float:
    units = depth_units(product, shelf)
    weight_kg = _num(product.get("weight_kg"))
    if units <= 0 or weight_kg <= 0:
        return 0.0
    return weight_kg * units


def _facing(product: dict[str, Any]) -> int:
    return max(1, _integer(product.get("facing_count") or product.get("facing"), 1))


def _set_facing(product: dict[str, Any], value: int) -> None:
    value = max(1, int(value))
    product["facing_count"] = value
    if "facing" in product:
        product["facing"] = value


def _width_per_facing_cm(product: dict[str, Any]) -> float:
    width_cm = _num(product.get("oriented_width_cm") or product.get("width_cm"))
    return max(0.0, width_cm * WIDTH_BUFFER_FACTOR)


def _shelf_totals(shelf: dict[str, Any]) -> tuple[float, float]:
    total_width = 0.0
    total_weight = 0.0
    for product in shelf.get("products") or []:
        facing = _facing(product)
        total_width += _width_per_facing_cm(product) * facing
        total_weight += stack_weight_per_facing_kg(product, shelf) * facing
    return total_width, total_weight


def _reducible_products(shelf: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [product for product in shelf.get("products") or [] if _facing(product) > 1]
    return sorted(
        rows,
        key=lambda product: (
            _sales(product),
            -stack_weight_per_facing_kg(product, shelf),
            -_width_per_facing_cm(product),
            _sku(product),
        ),
    )


def reconcile_full_depth_capacity(planogram: dict[str, Any] | None) -> dict[str, Any]:
    """Return a capacity-safe copy or explicit fail-closed blockers.

    Facing reductions are deterministic and preserve at least one facing per
    placed SKU. This is a reconciliation layer, not installation or assortment
    authority.
    """
    next_plan = deepcopy(planogram or {})
    if not next_plan.get("aisles"):
        return {
            "contract": RECONCILER_VERSION,
            "available": False,
            "valid": False,
            "production_authority": False,
            "blockers": [{"code": "planogram_missing"}],
            "adjustments": [],
            "planogram": next_plan,
        }

    blockers: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    shelf_reports: list[dict[str, Any]] = []

    for aisle in next_plan.get("aisles") or []:
        for module in aisle.get("modules") or []:
            for shelf in module.get("shelves") or []:
                products = shelf.get("products") or []
                shelf_width = _num(shelf.get("shelf_width_cm"))
                max_weight = _num(shelf.get("max_weight_kg"))
                location = {
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                }

                if products and (shelf_width <= 0 or max_weight <= 0):
                    blockers.append({**location, "code": "shelf_capacity_evidence_missing"})
                    continue

                for product in products:
                    evidence_ok = (
                        _width_per_facing_cm(product) > 0
                        and _num(product.get("height_cm")) > 0
                        and depth_units(product, shelf) > 0
                        and _num(product.get("weight_kg")) > 0
                    )
                    if not evidence_ok:
                        blockers.append(
                            {
                                **location,
                                "code": "product_capacity_evidence_missing",
                                "sku": _sku(product),
                            }
                        )

                if any(
                    blocker.get("aisle_id") == location["aisle_id"]
                    and blocker.get("module_id") == location["module_id"]
                    and blocker.get("shelf_no") == location["shelf_no"]
                    for blocker in blockers
                ):
                    continue

                before_width, before_weight = _shelf_totals(shelf)
                max_iterations = sum(max(0, _facing(product) - 1) for product in products)
                iterations = 0

                while iterations < max_iterations:
                    current_width, current_weight = _shelf_totals(shelf)
                    if current_width <= shelf_width + 1e-6 and current_weight <= max_weight + 1e-6:
                        break
                    reducible = _reducible_products(shelf)
                    if not reducible:
                        break
                    product = reducible[0]
                    previous = _facing(product)
                    _set_facing(product, previous - 1)
                    adjustments.append(
                        {
                            **location,
                            "sku": _sku(product),
                            "from_facing": previous,
                            "to_facing": previous - 1,
                            "reason": (
                                "full_depth_weight_capacity"
                                if current_weight > max_weight + 1e-6
                                else "linear_width_capacity"
                            ),
                        }
                    )
                    iterations += 1

                final_width, final_weight = _shelf_totals(shelf)
                shelf["used_width_cm"] = round(final_width, 6)
                shelf["used"] = round(final_width, 6)
                shelf["used_weight_kg"] = round(final_weight, 6)
                shelf["weight_model"] = "facing_x_depth_units_x_unit_weight"

                if final_width > shelf_width + 1e-6:
                    blockers.append(
                        {
                            **location,
                            "code": "shelf_linear_width_irreducible",
                            "calculated_width_cm": round(final_width, 6),
                            "shelf_width_cm": round(shelf_width, 6),
                        }
                    )
                if final_weight > max_weight + 1e-6:
                    blockers.append(
                        {
                            **location,
                            "code": "shelf_full_depth_weight_irreducible",
                            "calculated_weight_kg": round(final_weight, 6),
                            "max_weight_kg": round(max_weight, 6),
                        }
                    )

                shelf_reports.append(
                    {
                        **location,
                        "before_width_cm": round(before_width, 6),
                        "after_width_cm": round(final_width, 6),
                        "shelf_width_cm": round(shelf_width, 6),
                        "before_full_depth_weight_kg": round(before_weight, 6),
                        "after_full_depth_weight_kg": round(final_weight, 6),
                        "max_weight_kg": round(max_weight, 6),
                    }
                )

    return {
        "contract": RECONCILER_VERSION,
        "available": True,
        "valid": not blockers,
        "production_authority": False,
        "weight_model": "facing_x_depth_units_x_unit_weight",
        "width_buffer_factor": WIDTH_BUFFER_FACTOR,
        "adjustment_count": len(adjustments),
        "adjustments": adjustments,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "shelves": shelf_reports,
        "planogram": next_plan,
        "truth_boundary": (
            "deterministic capacity reconciliation can reduce facings but cannot move SKUs, "
            "invent evidence, grant assortment authority, or grant installation authority"
        ),
    }
