"""Commercial assortment/facing to physical Planogram convergence preview.

Commercial optimization and physical placement use different objective spaces.
This module deliberately aligns their linear-space envelope and then asks the
canonical physical allocator to prove a conservative facing reservation. A
second-pass Capacity V2 validator vetoes plans whose full-depth stack mass or
linear footprint exceeds the measured shelf.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from commercial_merchandising import optimize_commercial_merchandising
from physical_capacity_v2 import validate_planogram_capacity_v2
from physical_engine import generate_production_plan

CONVERGENCE_VERSION = "planogram-commercial-physical-convergence-v2"
PHYSICAL_LINEAR_SPACE_FACTOR = 1.10
PHYSICAL_FACING_CAP = 5


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
    return _text(row.get("sku") or row.get("SKU")).upper()


def _source_width_cm(row: dict[str, Any]) -> float:
    for field in ("width_cm", "product_width_cm", "product_width_in_cm"):
        value = _number(row.get(field))
        if value > 0:
            return value
    return 0.0


def _commercial_products_for_physical_space(
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use the same linear spacing envelope as physical placement."""
    adjusted: list[dict[str, Any]] = []
    for raw in products:
        row = deepcopy(raw)
        width = _source_width_cm(row)
        if width > 0:
            row["commercial_source_pack_width_cm"] = width
            row["width_cm"] = round(width * PHYSICAL_LINEAR_SPACE_FACTOR, 6)
            row["commercial_linear_spacing_factor"] = PHYSICAL_LINEAR_SPACE_FACTOR

        declared_max = _integer(
            row.get("max_facing") or row.get("maximum_facing"),
            PHYSICAL_FACING_CAP,
        )
        declared_min = max(
            1,
            _integer(row.get("min_facing") or row.get("minimum_facing"), 1),
        )
        safe_max = max(1, min(PHYSICAL_FACING_CAP, declared_max))
        row["max_facing"] = safe_max
        row["min_facing"] = min(declared_min, safe_max)
        adjusted.append(row)
    return adjusted


def _projection_tier(target_facing: int) -> str:
    if target_facing <= 1:
        return "BACK"
    if target_facing == 2:
        return "MID"
    if target_facing == 3:
        return "FAST"
    return "HOT"


def _physical_projection_product(
    raw: dict[str, Any],
    *,
    target_facing: int,
    commercial_fingerprint: str | None,
) -> dict[str, Any]:
    """Force the legacy allocator to conservatively reserve a target facing."""
    target = max(1, min(PHYSICAL_FACING_CAP, int(target_facing)))
    reserved = 5 if target == 4 else target
    row = deepcopy(raw)
    row["commercial_observed_sales_qty_7d"] = row.get("sales_qty_7d")
    row["commercial_observed_percent_stops"] = row.get("percent_stops")
    row["commercial_observed_on_hand_qty"] = row.get("on_hand_qty")
    row["commercial_observed_case_pack_qty"] = row.get("case_pack_qty")
    row["commercial_target_facing"] = target
    row["commercial_physical_reserved_facing"] = reserved
    row["commercial_selection_fingerprint"] = commercial_fingerprint

    # Placement-projection controls only; original observed values are retained above.
    row["sales_qty_7d"] = 0
    row["percent_stops"] = 0
    row["on_hand_qty"] = 0
    row["case_pack_qty"] = 1
    row["tier"] = _projection_tier(target)
    row["front_tier"] = row["tier"]
    return row


def _placed_facings(planogram: dict[str, Any] | None) -> dict[str, int]:
    facings: dict[str, int] = {}
    for aisle in (planogram or {}).get("aisles") or []:
        for module in aisle.get("modules") or []:
            for shelf in module.get("shelves") or []:
                for product in shelf.get("products") or []:
                    sku = _sku(product)
                    if not sku:
                        continue
                    facing = int(product.get("facing_count") or product.get("facing") or 1)
                    facings[sku] = facings.get(sku, 0) + max(1, facing)
    return facings


def compare_commercial_to_physical(
    *, commercial_result: dict[str, Any], physical_result: dict[str, Any]
) -> dict[str, Any]:
    targets = {
        _sku(row): int(row.get("facing_count") or 0)
        for row in commercial_result.get("selected_plan") or []
        if _sku(row)
    }
    actual = _placed_facings(physical_result.get("planogram"))
    rows: list[dict[str, Any]] = []
    target_total = actual_total = shortfall_total = 0
    unplaced: list[str] = []
    for sku in sorted(targets):
        target = max(0, targets[sku])
        observed = max(0, actual.get(sku, 0))
        shortfall = max(0, target - observed)
        target_total += target
        actual_total += observed
        shortfall_total += shortfall
        if observed == 0:
            unplaced.append(sku)
        rows.append({
            "sku": sku,
            "commercial_target_facing": target,
            "physical_reserved_or_placed_facing": observed,
            "facing_shortfall": shortfall,
            "conservative_over_reservation": max(0, observed - target),
            "converged": observed >= target,
        })
    physical_publishable = bool(physical_result.get("publishable"))
    commercial_available = bool(commercial_result.get("available"))
    converged = (
        commercial_available and physical_publishable and bool(targets)
        and not unplaced and shortfall_total == 0
    )
    return {
        "target_sku_count": len(targets),
        "physically_placed_target_sku_count": sum(actual.get(sku, 0) > 0 for sku in targets),
        "unplaced_target_sku_count": len(unplaced),
        "unplaced_target_skus": unplaced[:5_000],
        "target_facing_total": target_total,
        "physical_reserved_or_placed_facing_total": actual_total,
        "facing_shortfall_total": shortfall_total,
        "facing_convergence_pct": (
            round(min(actual_total, target_total) * 100.0 / target_total, 2)
            if target_total > 0 else 0.0
        ),
        "rows": rows[:10_000],
        "commercial_available": commercial_available,
        "physical_publishable": physical_publishable,
        "converged": converged,
    }


def converge_commercial_physical(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    category_capacity_cm: dict[str, Any] | None = None,
    total_shelf_width_cm: float | None = None,
    substitution_edges: list[dict[str, Any]] | None = None,
    objective_weights: dict[str, Any] | None = None,
    mode: str = "HYBRID",
    require_images: bool = True,
) -> dict[str, Any]:
    commercial_products = _commercial_products_for_physical_space(products)
    commercial = optimize_commercial_merchandising(
        products=commercial_products,
        category_capacity_cm=category_capacity_cm,
        total_shelf_width_cm=total_shelf_width_cm,
        substitution_edges=substitution_edges,
        objective_weights=objective_weights,
    )
    if not commercial.get("available"):
        return {
            "convergence_version": CONVERGENCE_VERSION,
            "available": False,
            "blockers": ["commercial_optimizer_unavailable"] + list(commercial.get("blockers") or []),
            "commercial": commercial,
            "production_authority": False,
            "assortment_execution_authority": False,
            "market_leadership_claim_allowed": False,
        }

    selected = {_sku(row): row for row in commercial.get("selected_plan") or [] if _sku(row)}
    physical_products: list[dict[str, Any]] = []
    for raw in products:
        sku = _sku(raw)
        target = selected.get(sku)
        if target is None:
            continue
        physical_products.append(_physical_projection_product(
            raw,
            target_facing=int(target.get("facing_count") or 1),
            commercial_fingerprint=commercial.get("commercial_fingerprint"),
        ))

    physical = generate_production_plan(
        physical_products, deepcopy(layout), deepcopy(store_dna),
        mode=mode, require_images=require_images,
    )
    capacity_v2 = validate_planogram_capacity_v2(physical.get("planogram"))
    comparison = compare_commercial_to_physical(
        commercial_result=commercial, physical_result=physical
    )
    blockers: list[str] = []
    if not commercial.get("commercial_evidence_complete"):
        blockers.append("commercial_evidence_incomplete")
    if not physical.get("publishable"):
        blockers.append("physical_plan_not_publishable")
    if not capacity_v2.get("valid"):
        blockers.append("physical_capacity_v2_failed")
    if comparison["unplaced_target_sku_count"]:
        blockers.append("commercial_assortment_not_physically_placeable")
    if comparison["facing_shortfall_total"]:
        blockers.append("commercial_facing_target_not_physically_met")

    fingerprint = hashlib.sha256(json.dumps({
        "commercial_fingerprint": commercial.get("commercial_fingerprint"),
        "physical_summary": physical.get("summary"),
        "capacity_v2": {
            "valid": capacity_v2.get("valid"),
            "violation_count": capacity_v2.get("violation_count"),
            "warning_count": capacity_v2.get("warning_count"),
        },
        "comparison": comparison,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    return {
        "convergence_version": CONVERGENCE_VERSION,
        "available": True,
        "preview_only": True,
        "commercial_input_contract": {
            "linear_spacing_factor": PHYSICAL_LINEAR_SPACE_FACTOR,
            "facing_cap": PHYSICAL_FACING_CAP,
            "target_4_reserved_as_5": True,
            "demand_fields_used_as_projection_controls": False,
        },
        "commercial": commercial,
        "physical": physical,
        "physical_capacity_v2": capacity_v2,
        "comparison": comparison,
        "blockers": list(dict.fromkeys(blockers)),
        "convergence_fingerprint": fingerprint,
        "repository_converged": comparison["converged"] and bool(capacity_v2.get("valid")) and not blockers,
        "production_authority": False,
        "assortment_execution_authority": False,
        "installation_authority": False,
        "field_evidence": False,
        "market_leadership_claim_allowed": False,
        "evidence_boundary": (
            "commercial selection is projected through a conservative facing reservation, "
            "then vetoed by full-depth capacity v2; repository convergence is not a "
            "field KPI result or execution approval"
        ),
    }
