"""Second-pass physical capacity validator for PlanAI plans.

The legacy allocator accounts shelf weight per facing, while a shelf can carry
multiple units behind each facing. This validator recomputes the true displayed
stack footprint and weight from placed facings and shelf depth. It is a veto
layer: it never grants production authority.
"""
from __future__ import annotations

import math
from typing import Any

CAPACITY_V2_VERSION = "planogram-physical-capacity-v2-full-depth-stack"
WIDTH_BUFFER_FACTOR = 1.10
MAX_VIOLATIONS = 10_000


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


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _iter_shelves(planogram: dict[str, Any] | None):
    for aisle in (planogram or {}).get("aisles") or []:
        for module in aisle.get("modules") or []:
            for shelf in module.get("shelves") or []:
                yield aisle, module, shelf


def _product_capacity(product: dict[str, Any], shelf: dict[str, Any]) -> dict[str, Any]:
    facing = max(1, _integer(product.get("facing_count") or product.get("facing"), 1))
    width_cm = max(0.0, _num(product.get("width_cm")))
    height_cm = max(0.0, _num(product.get("height_cm")))
    depth_cm = max(0.0, _num(product.get("depth_cm")))
    weight_kg = max(0.0, _num(product.get("weight_kg")))
    shelf_depth_cm = max(0.0, _num(shelf.get("shelf_depth_cm")))
    evidence_complete = all(value > 0 for value in (width_cm, height_cm, depth_cm, weight_kg))
    depth_units = (
        max(1, math.floor(shelf_depth_cm / depth_cm))
        if depth_cm > 0 and shelf_depth_cm > 0
        else 0
    )
    return {
        "sku": _text(product.get("sku") or product.get("SKU")).upper(),
        "facing_count": facing,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "depth_cm": depth_cm,
        "weight_kg": weight_kg,
        "depth_units": depth_units,
        "linear_width_cm": width_cm * facing * WIDTH_BUFFER_FACTOR,
        "stack_weight_kg": weight_kg * facing * depth_units,
        "evidence_complete": evidence_complete and depth_units > 0,
    }


def validate_planogram_capacity_v2(planogram: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(planogram, dict) or not planogram.get("aisles"):
        return {
            "contract": CAPACITY_V2_VERSION,
            "available": False,
            "valid": False,
            "blockers": ["planogram_missing"],
            "production_authority": False,
        }

    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    shelf_reports: list[dict[str, Any]] = []
    missing_evidence = 0

    for aisle, module, shelf in _iter_shelves(planogram):
        shelf_width_cm = max(0.0, _num(shelf.get("shelf_width_cm")))
        shelf_height_cm = max(0.0, _num(shelf.get("shelf_height_cm")))
        shelf_depth_cm = max(0.0, _num(shelf.get("shelf_depth_cm")))
        max_weight_kg = max(0.0, _num(shelf.get("max_weight_kg")))
        calculated_width = 0.0
        calculated_weight = 0.0
        products = []

        for product in shelf.get("products") or []:
            row = _product_capacity(product, shelf)
            products.append(row)
            if not row["evidence_complete"]:
                missing_evidence += 1
                violations.append({
                    "code": "product_capacity_evidence_missing",
                    "sku": row["sku"],
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                })
                continue
            calculated_width += row["linear_width_cm"]
            calculated_weight += row["stack_weight_kg"]

            if shelf_height_cm > 0 and row["height_cm"] > shelf_height_cm + 1e-9:
                violations.append({
                    "code": "product_height_exceeds_shelf",
                    "sku": row["sku"],
                    "product_height_cm": round(row["height_cm"], 3),
                    "shelf_height_cm": round(shelf_height_cm, 3),
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                })
            if shelf_depth_cm > 0 and row["depth_cm"] > shelf_depth_cm + 1e-9:
                violations.append({
                    "code": "product_depth_exceeds_shelf",
                    "sku": row["sku"],
                    "product_depth_cm": round(row["depth_cm"], 3),
                    "shelf_depth_cm": round(shelf_depth_cm, 3),
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                })

        if calculated_width > shelf_width_cm + 1e-6:
            violations.append({
                "code": "shelf_linear_width_exceeded",
                "calculated_width_cm": round(calculated_width, 3),
                "shelf_width_cm": round(shelf_width_cm, 3),
                "aisle_id": aisle.get("aisle_id"),
                "module_id": module.get("module_id"),
                "shelf_no": shelf.get("shelf_no"),
            })
        if calculated_weight > max_weight_kg + 1e-6:
            violations.append({
                "code": "shelf_full_depth_weight_exceeded",
                "calculated_weight_kg": round(calculated_weight, 3),
                "max_weight_kg": round(max_weight_kg, 3),
                "aisle_id": aisle.get("aisle_id"),
                "module_id": module.get("module_id"),
                "shelf_no": shelf.get("shelf_no"),
            })

        declared_weight = max(0.0, _num(shelf.get("used_weight_kg")))
        declared_width = max(0.0, _num(shelf.get("used_width_cm") or shelf.get("used")))
        if calculated_weight > declared_weight + 0.01:
            warnings.append({
                "code": "legacy_declared_weight_understated",
                "gap_kg": round(calculated_weight - declared_weight, 3),
                "declared_weight_kg": round(declared_weight, 3),
                "calculated_weight_kg": round(calculated_weight, 3),
                "aisle_id": aisle.get("aisle_id"),
                "module_id": module.get("module_id"),
                "shelf_no": shelf.get("shelf_no"),
            })
        if abs(calculated_width - declared_width) > 0.11 and products:
            warnings.append({
                "code": "declared_width_differs_from_recalculation",
                "gap_cm": round(calculated_width - declared_width, 3),
                "aisle_id": aisle.get("aisle_id"),
                "module_id": module.get("module_id"),
                "shelf_no": shelf.get("shelf_no"),
            })

        shelf_reports.append({
            "aisle_id": aisle.get("aisle_id"),
            "module_id": module.get("module_id"),
            "shelf_no": shelf.get("shelf_no"),
            "product_count": len(products),
            "calculated_linear_width_cm": round(calculated_width, 3),
            "shelf_width_cm": round(shelf_width_cm, 3),
            "calculated_full_depth_weight_kg": round(calculated_weight, 3),
            "max_weight_kg": round(max_weight_kg, 3),
        })

    hard = violations[:MAX_VIOLATIONS]
    return {
        "contract": CAPACITY_V2_VERSION,
        "available": True,
        "valid": not hard,
        "production_authority": False,
        "width_buffer_factor": WIDTH_BUFFER_FACTOR,
        "weight_model": "facing_x_depth_units_x_unit_weight",
        "shelf_count": len(shelf_reports),
        "missing_evidence_count": missing_evidence,
        "violation_count": len(violations),
        "violations": hard,
        "warning_count": len(warnings),
        "warnings": warnings[:MAX_VIOLATIONS],
        "shelves": shelf_reports[:MAX_VIOLATIONS],
        "evidence_boundary": (
            "capacity v2 is a deterministic veto over supplied dimensions, facings, "
            "shelf geometry and unit mass; it does not grant installation authority"
        ),
    }
