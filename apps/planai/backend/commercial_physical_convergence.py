"""Commercial assortment/facing to physical Planogram convergence preview.

The commercial optimizer can select an economically attractive assortment and
facing envelope, but that result is not executable until the physical engine can
place the same SKUs under measured fixture, mass, temperature and architecture
constraints. This module makes that gap explicit rather than silently treating a
commercial recommendation as a valid Planogram.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from commercial_merchandising import optimize_commercial_merchandising
from physical_engine import generate_production_plan

CONVERGENCE_VERSION = "planogram-commercial-physical-convergence-v1"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _sku(row: dict[str, Any]) -> str:
    return _text(row.get("sku") or row.get("SKU")).upper()


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
    *,
    commercial_result: dict[str, Any],
    physical_result: dict[str, Any],
) -> dict[str, Any]:
    targets = {
        _sku(row): int(row.get("facing_count") or 0)
        for row in commercial_result.get("selected_plan") or []
        if _sku(row)
    }
    actual = _placed_facings(physical_result.get("planogram"))
    rows: list[dict[str, Any]] = []
    target_total = 0
    actual_total = 0
    shortfall_total = 0
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
        rows.append(
            {
                "sku": sku,
                "commercial_target_facing": target,
                "physical_placed_facing": observed,
                "facing_shortfall": shortfall,
                "converged": observed >= target,
            }
        )
    physical_publishable = bool(physical_result.get("publishable"))
    commercial_available = bool(commercial_result.get("available"))
    converged = (
        commercial_available
        and physical_publishable
        and bool(targets)
        and not unplaced
        and shortfall_total == 0
    )
    return {
        "target_sku_count": len(targets),
        "physically_placed_target_sku_count": sum(actual.get(sku, 0) > 0 for sku in targets),
        "unplaced_target_sku_count": len(unplaced),
        "unplaced_target_skus": unplaced[:5_000],
        "target_facing_total": target_total,
        "physical_facing_total_for_targets": actual_total,
        "facing_shortfall_total": shortfall_total,
        "facing_convergence_pct": (
            round(min(actual_total, target_total) * 100.0 / target_total, 2)
            if target_total > 0
            else 0.0
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
    commercial = optimize_commercial_merchandising(
        products=products,
        category_capacity_cm=category_capacity_cm,
        total_shelf_width_cm=total_shelf_width_cm,
        substitution_edges=substitution_edges,
        objective_weights=objective_weights,
    )
    if not commercial.get("available"):
        return {
            "convergence_version": CONVERGENCE_VERSION,
            "available": False,
            "blockers": ["commercial_optimizer_unavailable"]
            + list(commercial.get("blockers") or []),
            "commercial": commercial,
            "production_authority": False,
            "assortment_execution_authority": False,
            "market_leadership_claim_allowed": False,
        }

    selected = {
        _sku(row): row for row in commercial.get("selected_plan") or [] if _sku(row)
    }
    physical_products: list[dict[str, Any]] = []
    for raw in products:
        sku = _sku(raw)
        target = selected.get(sku)
        if target is None:
            continue
        row = deepcopy(raw)
        row["commercial_target_facing"] = int(target.get("facing_count") or 1)
        row["commercial_selection_fingerprint"] = commercial.get("commercial_fingerprint")
        physical_products.append(row)

    physical = generate_production_plan(
        physical_products,
        deepcopy(layout),
        deepcopy(store_dna),
        mode=mode,
        require_images=require_images,
    )
    comparison = compare_commercial_to_physical(
        commercial_result=commercial,
        physical_result=physical,
    )
    blockers: list[str] = []
    if not commercial.get("commercial_evidence_complete"):
        blockers.append("commercial_evidence_incomplete")
    if not physical.get("publishable"):
        blockers.append("physical_plan_not_publishable")
    if comparison["unplaced_target_sku_count"]:
        blockers.append("commercial_assortment_not_physically_placeable")
    if comparison["facing_shortfall_total"]:
        blockers.append("commercial_facing_target_not_physically_met")

    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "commercial_fingerprint": commercial.get("commercial_fingerprint"),
                "physical_summary": physical.get("summary"),
                "comparison": comparison,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "convergence_version": CONVERGENCE_VERSION,
        "available": True,
        "preview_only": True,
        "commercial": commercial,
        "physical": physical,
        "comparison": comparison,
        "blockers": list(dict.fromkeys(blockers)),
        "convergence_fingerprint": fingerprint,
        "repository_converged": comparison["converged"] and not blockers,
        "production_authority": False,
        "assortment_execution_authority": False,
        "installation_authority": False,
        "field_evidence": False,
        "market_leadership_claim_allowed": False,
        "evidence_boundary": (
            "commercial selection is compared with the real physical allocator; "
            "repository convergence is not a field KPI result or execution approval"
        ),
    }
