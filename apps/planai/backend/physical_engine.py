"""Production-only Planogram entry point guarded by physical truth.

The canonical deterministic allocator in ``engine.py`` remains untouched.  This
wrapper is intentionally fail-closed: it resolves master/file dimensions with
AI estimation disabled, validates measured Store DNA and fixture capacity, and
only then delegates to the frozen foundation allocator.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import engine as deterministic_engine
from physical_truth import (
    clone_with_physical_truth,
    physical_constraint_reason,
    production_acceptance_report,
    required_fixture_class,
)


def _explicit_unplaced(
    products: List[Dict[str, Any]],
    acceptance: Dict[str, Any],
) -> List[Dict[str, Any]]:
    blockers = acceptance.get("blockers") or []
    blocker_text = ",".join(blockers) or "unknown_physical_truth_blocker"
    rows = []
    for product in products:
        reason = "production_physical_truth_gate_blocked"
        constraint_reason = blocker_text
        if product.get("dimension_source") == "missing":
            reason = "approved_dimensions_missing"
            constraint_reason = "approved_width_height_depth_required"
        elif not product.get("image_url"):
            reason = "approved_image_link_missing"
            constraint_reason = "approved_product_image_required"
        rows.append(
            {
                "sku": product.get("sku"),
                "product_name": product.get("product_name"),
                "brand": product.get("brand"),
                "category_l1": product.get("category_l1"),
                "storage_type": product.get("storage_type"),
                "reason": reason,
                "constraint_reason": constraint_reason,
                "suggested_action": (
                    "Onaylı ürün ölçüsü/görseli, ölçülmüş Store DNA ve gerçek "
                    "fixture kapasitesi tamamlanmadan production plan üretme."
                ),
            }
        )
    return rows


def prepare_production_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared = []
    for raw in products or []:
        # Critical boundary: production truth never fills missing dimensions
        # with AI estimates. Master/file evidence only.
        enriched = deterministic_engine.enrich_product(
            raw,
            allow_ai_dimensions=False,
        )
        truth = clone_with_physical_truth(enriched)
        # Preserve temperature truth as a separate axis while adapting the
        # legacy allocator's storage pool for pallet-required products.
        truth["temperature_zone"] = truth.get("temperature_zone") or "AMBIENT"
        if truth.get("required_fixture_class") == "PALLET":
            truth["storage_type"] = "PALLET"
            truth["_storage"] = "PALLET"
        prepared.append(truth)
    return prepared


def _iter_placed(planogram: Dict[str, Any]):
    for aisle in (planogram or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            for shelf in module.get("shelves", []) or []:
                for product in shelf.get("products", []) or []:
                    yield aisle, module, shelf, product


def validate_operational_physical_rules(planogram: Dict[str, Any]) -> Dict[str, Any]:
    violations = []
    for aisle, module, shelf, product in _iter_placed(planogram):
        reason = physical_constraint_reason(product, module, shelf)
        if reason:
            violations.append(
                {
                    "type": reason,
                    "sku": product.get("sku"),
                    "product_name": product.get("product_name"),
                    "required_fixture_class": required_fixture_class(product),
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "side": module.get("side"),
                    "shelf_no": shelf.get("shelf_no"),
                    "zone_type": shelf.get("zone_type"),
                }
            )
    return {
        "violation_count": len(violations),
        "violations": violations,
        "valid": not violations,
    }


def generate_production_plan(
    products: List[Dict[str, Any]],
    layout: Optional[Dict[str, Any]],
    store_dna: Optional[Dict[str, Any]],
    *,
    mode: str = "HYBRID",
    brand_side_rules: Optional[Dict[str, str]] = None,
    scoring_config: Optional[Dict[str, float]] = None,
    require_images: bool = True,
    progress_callback=None,
) -> Dict[str, Any]:
    prepared = prepare_production_products(products or [])
    acceptance = production_acceptance_report(
        prepared,
        layout,
        store_dna,
        require_images=require_images,
    )

    if not acceptance.get("production_ready"):
        unplaced = _explicit_unplaced(prepared, acceptance)
        return {
            "engine_version": "physical-truth-gate-v1",
            "foundation_engine_version": "deterministic-best-fit-v4.2",
            "single_source_of_truth": True,
            "production_ready": False,
            "publishable": False,
            "solver_optimizer_allowed": False,
            "physical_truth": acceptance,
            "summary": {
                "total": len(prepared),
                "placed": 0,
                "unplaced": len(unplaced),
                "strict_rule_violation_count": 0,
                "production_acceptance_blocker_count": len(acceptance.get("blockers") or []),
                "unplaced_reason_counts": {
                    reason: sum(1 for row in unplaced if row.get("reason") == reason)
                    for reason in sorted({row.get("reason") or "unknown" for row in unplaced})
                },
            },
            "planogram": None,
            "unplaced": unplaced,
            "unplaced_products": unplaced,
            "diagnostics": {
                "summary": {
                    "strict_rule_violation_count": 0,
                    "valid": False,
                },
                "physical_truth_blockers": acceptance.get("blockers") or [],
            },
        }

    result = deterministic_engine.generate_planogram(
        products=prepared,
        layout=layout,
        mode=mode,
        brand_side_rules=brand_side_rules,
        scoring_config=scoring_config,
        allow_ai_dimensions=False,
        progress_callback=progress_callback,
    )

    operational = validate_operational_physical_rules(result.get("planogram") or {})
    existing_strict = int(
        result.get("diagnostics", {})
        .get("summary", {})
        .get("strict_rule_violation_count", 0)
        or 0
    )
    publishable = existing_strict == 0 and operational["valid"]

    result["engine_version"] = "physical-truth-gated-deterministic-v1"
    result["foundation_engine_version"] = "deterministic-best-fit-v4.2"
    result["production_ready"] = publishable
    result["publishable"] = publishable
    result["solver_optimizer_allowed"] = True
    result["physical_truth"] = acceptance
    result["operational_physical_validation"] = operational
    result.setdefault("summary", {})["operational_physical_violation_count"] = operational[
        "violation_count"
    ]
    result.setdefault("summary", {})["production_acceptance_blocker_count"] = 0
    result.setdefault("diagnostics", {})["operational_physical_validation"] = operational
    if not publishable:
        result.setdefault("diagnostics", {}).setdefault("summary", {})["valid"] = False
    return result
