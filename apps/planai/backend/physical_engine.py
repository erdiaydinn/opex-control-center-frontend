"""Production-only Planogram entry point guarded by physical truth.

The canonical deterministic allocator in ``engine.py`` remains untouched. This
wrapper is intentionally fail-closed: it resolves master/file dimensions with
AI estimation disabled, validates measured Store DNA, fixture capacity and any
declared store architecture, and only then delegates to the foundation allocator.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import engine as deterministic_engine
from architecture_truth import (
    architecture_route_objective,
    architecture_truth_report,
    layout_architecture_report,
)
from physical_truth import (
    clone_with_physical_truth,
    physical_constraint_reason,
    production_acceptance_report,
    required_fixture_class,
)


def _explicit_unplaced(
    products: list[dict[str, Any]],
    acceptance: dict[str, Any],
) -> list[dict[str, Any]]:
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
                    "fixture/mimari geometri tamamlanmadan production plan üretme."
                ),
            }
        )
    return rows


def prepare_production_products(
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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


def _iter_placed(planogram: dict[str, Any]):
    for aisle in (planogram or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            for shelf in module.get("shelves", []) or []:
                for product in shelf.get("products", []) or []:
                    yield aisle, module, shelf, product


def validate_operational_physical_rules(
    planogram: dict[str, Any],
) -> dict[str, Any]:
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


def _apply_architecture_gate(
    acceptance: dict[str, Any],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed only when an architecture contract has been declared.

    Legacy approved stores can migrate incrementally. A store that supplies an
    architecture object, however, cannot silently fall back to non-spatial truth.
    """
    architecture = architecture_truth_report(store_dna)
    layout_validation = layout_architecture_report(layout, store_dna)
    acceptance["architecture_truth"] = architecture
    acceptance["layout_architecture_validation"] = layout_validation

    if architecture.get("present") and (
        not architecture.get("valid") or not layout_validation.get("valid")
    ):
        blockers = list(acceptance.get("blockers") or [])
        for blocker in list(architecture.get("blockers") or []) + list(
            layout_validation.get("blockers") or []
        ):
            if blocker not in blockers:
                blockers.append(blocker)
        acceptance["blockers"] = blockers
        acceptance["production_ready"] = False
        acceptance["solver_optimizer_allowed"] = False
    return architecture, layout_validation


def _qualify_route_module_ids(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Scope module identity by aisle for spatial routing only.

    The legacy allocator legitimately reuses small integer module ids across
    aisle/fixture pools. Spatial routing must never collapse A/1 and PALLET/1
    into the same physical location, so route-only copies use an aisle-qualified
    identity while the canonical plan payload remains unchanged.
    """
    if payload is None:
        return None
    qualified = deepcopy(payload)
    for aisle in qualified.get("aisles", []) or []:
        aisle_id = str(aisle.get("aisle_id") or "").strip()
        for module in aisle.get("modules", []) or []:
            module_id = str(module.get("module_id") or "").strip()
            module["module_id"] = f"{aisle_id}::{module_id}"
    return qualified


def _architecture_route_report(
    result: dict[str, Any],
    prepared: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
) -> dict[str, Any]:
    routed_result = deepcopy(result)
    routed_result["planogram"] = _qualify_route_module_ids(result.get("planogram"))
    routed_layout = _qualify_route_module_ids(layout)
    return architecture_route_objective(
        routed_result,
        prepared,
        routed_layout,
        store_dna,
    )


def _apply_route_gate(
    acceptance: dict[str, Any],
    architecture: dict[str, Any],
    route_report: dict[str, Any],
) -> bool:
    """Return whether declared architecture is physically walkable.

    Missing architecture remains an incremental-migration state. Once measured
    architecture is declared, however, an unreachable picker origin or placed
    fixture is a production blocker rather than permission to fall back to an
    ordinal route proxy.
    """
    if not architecture.get("present"):
        return True
    if route_report.get("available"):
        return True

    reason = str(route_report.get("reason") or "unknown").strip()
    blocker = f"architecture_route_unavailable:{reason}"
    blockers = list(acceptance.get("blockers") or [])
    if blocker not in blockers:
        blockers.append(blocker)
    acceptance["blockers"] = blockers
    acceptance["production_ready"] = False
    acceptance["solver_optimizer_allowed"] = False
    return False


def generate_production_plan(
    products: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    *,
    mode: str = "HYBRID",
    brand_side_rules: dict[str, str] | None = None,
    scoring_config: dict[str, float] | None = None,
    require_images: bool = True,
    progress_callback=None,
) -> dict[str, Any]:
    prepared = prepare_production_products(products or [])
    acceptance = production_acceptance_report(
        prepared,
        layout,
        store_dna,
        require_images=require_images,
    )
    architecture, layout_architecture = _apply_architecture_gate(
        acceptance,
        layout,
        store_dna,
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
            "architecture_truth": architecture,
            "layout_architecture_validation": layout_architecture,
            "summary": {
                "total": len(prepared),
                "placed": 0,
                "unplaced": len(unplaced),
                "strict_rule_violation_count": 0,
                "production_acceptance_blocker_count": len(
                    acceptance.get("blockers") or []
                ),
                "unplaced_reason_counts": {
                    reason: sum(
                        1 for row in unplaced if row.get("reason") == reason
                    )
                    for reason in sorted(
                        {row.get("reason") or "unknown" for row in unplaced}
                    )
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
                "architecture_truth": architecture,
                "layout_architecture_validation": layout_architecture,
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
    route_report = _architecture_route_report(
        result,
        prepared,
        layout,
        store_dna,
    )
    route_valid = _apply_route_gate(acceptance, architecture, route_report)
    existing_strict = int(
        result.get("diagnostics", {})
        .get("summary", {})
        .get("strict_rule_violation_count", 0)
        or 0
    )
    publishable = existing_strict == 0 and operational["valid"] and route_valid

    result["engine_version"] = "physical-truth-gated-deterministic-v1"
    result["foundation_engine_version"] = "deterministic-best-fit-v4.2"
    result["production_ready"] = publishable
    result["publishable"] = publishable
    result["solver_optimizer_allowed"] = route_valid
    result["physical_truth"] = acceptance
    result["architecture_truth"] = architecture
    result["layout_architecture_validation"] = layout_architecture
    result["architecture_route_objective"] = route_report
    result["operational_physical_validation"] = operational
    result.setdefault("summary", {})["operational_physical_violation_count"] = operational[
        "violation_count"
    ]
    result.setdefault("summary", {})["production_acceptance_blocker_count"] = len(
        acceptance.get("blockers") or []
    )
    result.setdefault("diagnostics", {})[
        "operational_physical_validation"
    ] = operational
    result.setdefault("diagnostics", {})["architecture_truth"] = architecture
    result.setdefault("diagnostics", {})[
        "layout_architecture_validation"
    ] = layout_architecture
    result.setdefault("diagnostics", {})[
        "architecture_route_objective"
    ] = route_report
    if not publishable:
        result.setdefault("diagnostics", {}).setdefault("summary", {})["valid"] = False
    return result
