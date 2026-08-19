"""Blind A/B benchmark for expert/manual versus generated Planogram candidates.

Both candidates are re-hydrated from the same product truth and evaluated on the
same measured Store DNA, fixture layout and anonymized SKU baskets. Candidate
payloads cannot override physical dimensions, temperature truth or master sales.
The result is repository benchmark evidence only; it never proves market
leadership or field performance without a blinded expert protocol and live KPI
backtest.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import physical_optimizer as v1
import physical_optimizer_v3 as v3
from architecture_truth import architecture_truth_report, layout_architecture_report
from physical_engine import prepare_production_products, validate_operational_physical_rules
from physical_truth import production_acceptance_report
from picker_tour_simulation import simulate_picker_tours

BLIND_BENCHMARK_VERSION = "planogram-blind-ab-benchmark-v1"
MAX_CANDIDATE_SKUS = 10_000
CAPACITY_TOLERANCE_CM = 0.5


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _sku(row: dict[str, Any]) -> str:
    return _text(row.get("sku") or row.get("SKU")).upper()


def _module_key(aisle: dict[str, Any], module: dict[str, Any]) -> str:
    aisle_id = _text(aisle.get("aisle_id"))
    module_id = _text(module.get("module_id"))
    if "::" in module_id:
        return module_id
    return f"{aisle_id}::{module_id}" if aisle_id else module_id


def _layout_module_index(layout: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            result[_module_key(aisle, module)] = module
    return result


def _layout_shelf_width_cm(module: dict[str, Any], shelf_index: int) -> float:
    shelves = module.get("shelves") or []
    if 0 <= shelf_index < len(shelves):
        width = _number((shelves[shelf_index] or {}).get("shelf_width_cm"))
        if width > 0:
            return width
    width_m = _number(module.get("width_m"))
    if width_m > 0:
        return width_m * 100.0
    width_cm = _number(module.get("width_cm"))
    return width_cm if width_cm > 0 else 0.0


def _facing_count(row: dict[str, Any]) -> int:
    return max(1, min(100, round(_number(row.get("facing_count") or row.get("facing"), 1))))


def _safe_candidate_product(master: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    hydrated = deepcopy(master)
    # Placement can request facings, but cannot rewrite dimensions, sales,
    # temperature/fixture truth or other source-master physical evidence.
    hydrated["facing_count"] = _facing_count(candidate)
    for field in ("coverage_days", "placement_reason", "side", "position"):
        if field in candidate:
            hydrated[field] = candidate[field]
    return hydrated


def _candidate_planogram(candidate: dict[str, Any]) -> dict[str, Any] | None:
    planogram = candidate.get("planogram") if isinstance(candidate, dict) else None
    if isinstance(planogram, dict):
        return deepcopy(planogram)
    if isinstance(candidate, dict) and isinstance(candidate.get("aisles"), list):
        return deepcopy(candidate)
    return None


def _hydrate_candidate(
    *,
    candidate: dict[str, Any],
    prepared_products: list[dict[str, Any]],
    layout: dict[str, Any],
) -> dict[str, Any]:
    planogram = _candidate_planogram(candidate)
    if planogram is None:
        return {
            "available": False,
            "blockers": ["candidate_planogram_missing"],
        }

    master_by_sku: dict[str, dict[str, Any]] = {}
    duplicate_master: set[str] = set()
    for row in prepared_products:
        sku = _sku(row)
        if not sku:
            continue
        if sku in master_by_sku:
            duplicate_master.add(sku)
        master_by_sku[sku] = row
    if duplicate_master:
        return {
            "available": False,
            "blockers": [
                "duplicate_master_sku:" + ",".join(sorted(duplicate_master)[:20])
            ],
        }

    layout_modules = _layout_module_index(layout)
    blockers: list[str] = []
    placed_skus: set[str] = set()
    unknown_skus: set[str] = set()
    duplicate_placements: set[str] = set()
    capacity_violations: list[dict[str, Any]] = []
    placed_rows = 0

    for aisle in planogram.get("aisles", []) or []:
        aisle_id = _text(aisle.get("aisle_id"))
        for module in aisle.get("modules", []) or []:
            key = _module_key(aisle, module)
            layout_module = layout_modules.get(key)
            if layout_module is None:
                blockers.append(f"candidate_module_not_in_layout:{key}")
            for shelf_index, shelf in enumerate(module.get("shelves", []) or []):
                rows = shelf.get("products", []) or []
                if not isinstance(rows, list):
                    blockers.append(f"candidate_products_invalid:{key}:{shelf_index + 1}")
                    shelf["products"] = []
                    continue
                hydrated_rows: list[dict[str, Any]] = []
                used_width_cm = 0.0
                for raw in rows:
                    candidate_product = raw if isinstance(raw, dict) else {"sku": raw}
                    sku = _sku(candidate_product)
                    if not sku or sku not in master_by_sku:
                        if sku:
                            unknown_skus.add(sku)
                        else:
                            blockers.append(
                                f"candidate_sku_missing:{key}:{shelf_index + 1}"
                            )
                        continue
                    if sku in placed_skus:
                        duplicate_placements.add(sku)
                    placed_skus.add(sku)
                    placed_rows += 1
                    if placed_rows > MAX_CANDIDATE_SKUS:
                        blockers.append("candidate_sku_limit_exceeded")
                        break
                    hydrated = _safe_candidate_product(
                        master_by_sku[sku],
                        candidate_product,
                    )
                    hydrated_rows.append(hydrated)
                    used_width_cm += max(0.0, _number(hydrated.get("width_cm"))) * _facing_count(
                        hydrated
                    )
                shelf["products"] = hydrated_rows
                shelf_width_cm = _number(shelf.get("shelf_width_cm"))
                if shelf_width_cm <= 0 and layout_module is not None:
                    shelf_width_cm = _layout_shelf_width_cm(layout_module, shelf_index)
                if rows and shelf_width_cm <= 0:
                    blockers.append(f"candidate_shelf_width_missing:{key}:{shelf_index + 1}")
                elif used_width_cm > shelf_width_cm + CAPACITY_TOLERANCE_CM:
                    capacity_violations.append(
                        {
                            "module_id": key,
                            "shelf_no": shelf_index + 1,
                            "used_width_cm": round(used_width_cm, 3),
                            "shelf_width_cm": round(shelf_width_cm, 3),
                            "overflow_cm": round(used_width_cm - shelf_width_cm, 3),
                        }
                    )
                shelf["shelf_width_cm"] = shelf_width_cm
                shelf["used_width_cm"] = round(used_width_cm, 3)
            if placed_rows > MAX_CANDIDATE_SKUS:
                break
        if placed_rows > MAX_CANDIDATE_SKUS:
            break

    if unknown_skus:
        blockers.append("candidate_unknown_sku:" + ",".join(sorted(unknown_skus)[:50]))
    if duplicate_placements:
        blockers.append(
            "candidate_duplicate_sku_placement:"
            + ",".join(sorted(duplicate_placements)[:50])
        )
    if capacity_violations:
        blockers.append("candidate_shelf_capacity_overflow")

    unplaced = [
        deepcopy(row)
        for sku, row in master_by_sku.items()
        if sku not in placed_skus
    ]
    result = {
        "planogram": planogram,
        "unplaced": unplaced,
        "diagnostics": {"summary": {"strict_rule_violation_count": 0}},
        "physical_truth": {"blockers": []},
    }
    operational = validate_operational_physical_rules(planogram)
    result["operational_physical_validation"] = operational
    return {
        "available": True,
        "result": result,
        "blockers": list(dict.fromkeys(blockers)),
        "capacity_violations": capacity_violations,
        "operational_validation": operational,
        "placed_sku_count": len(placed_skus),
        "unplaced_sku_count": len(unplaced),
    }


def _weighted_unplaced_sales(
    result: dict[str, Any],
    prepared_products: list[dict[str, Any]],
) -> float:
    sales_by_sku = {_sku(row): max(0.0, v1._sales(row)) for row in prepared_products}
    return round(
        sum(sales_by_sku.get(_sku(row), 0.0) for row in result.get("unplaced") or []),
        6,
    )


def _candidate_evaluation(
    *,
    candidate: dict[str, Any],
    prepared_products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    hydrated = _hydrate_candidate(
        candidate=candidate,
        prepared_products=prepared_products,
        layout=layout,
    )
    if not hydrated.get("available"):
        return {
            "available": False,
            "blockers": hydrated.get("blockers") or [],
        }

    result = hydrated["result"]
    tour_report = simulate_picker_tours(
        result=result,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
    )
    tour = v3._tour_summary(tour_report)
    blockers = list(hydrated.get("blockers") or [])
    operational = hydrated.get("operational_validation") or {}
    if int(operational.get("violation_count") or 0):
        blockers.append("candidate_operational_physical_violation")
    if not tour.get("available"):
        blockers.append(
            "candidate_picker_tour_unavailable:"
            + _text(tour_report.get("reason") or "unknown")
        )

    objective: dict[str, float | int] = {
        "hard_violation_count": len(list(dict.fromkeys(blockers)))
        + int(operational.get("violation_count") or 0)
        + len(hydrated.get("capacity_violations") or []),
        "weighted_unplaced_sales": _weighted_unplaced_sales(
            result,
            prepared_products,
        ),
        "unplaced_sku_count": len(result.get("unplaced") or []),
        "tour_unsimulated_order_count": int(tour.get("unsimulated_order_count") or 0),
        "tour_p95_m": float(tour.get("p95_m") or 0.0),
        "tour_average_m": float(tour.get("average_m") or 0.0),
        "coverage_shortfall": float(v1._coverage_shortfall(result)),
        "brand_fragmentation": float(v1._brand_fragmentation(result)),
        "capacity_pressure": float(v1._capacity_pressure(result)),
    }
    return {
        "available": True,
        "objective": objective,
        "objective_key": list(v3.objective_key(objective)),
        "blockers": list(dict.fromkeys(blockers)),
        "placed_sku_count": hydrated.get("placed_sku_count"),
        "unplaced_sku_count": hydrated.get("unplaced_sku_count"),
        "capacity_violations": hydrated.get("capacity_violations") or [],
        "operational_validation": operational,
        "tour": tour,
        "tour_evidence": {
            "simulation_version": tour_report.get("simulation_version"),
            "architecture_fingerprint": tour_report.get("architecture_fingerprint"),
            "routing_algorithm": tour_report.get("routing_algorithm"),
            "production_evidence": False,
        },
    }


def _evidence_fingerprint(
    *,
    prepared_products: list[dict[str, Any]],
    layout: dict[str, Any],
    architecture_fingerprint: str | None,
    orders: list[dict[str, Any]],
) -> str:
    product_truth = sorted(
        (
            _sku(row),
            round(v1._sales(row), 6),
            round(_number(row.get("width_cm")), 4),
            round(_number(row.get("height_cm")), 4),
            round(_number(row.get("depth_cm")), 4),
            _text(row.get("temperature_zone") or row.get("storage_type")),
        )
        for row in prepared_products
        if _sku(row)
    )
    payload = {
        "products": product_truth,
        "layout": layout,
        "architecture_fingerprint": architecture_fingerprint,
        "basket_fingerprint": v3.order_basket_fingerprint(orders),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def benchmark_candidates(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
) -> dict[str, Any]:
    """Blindly compare candidate A/B under identical measured evidence."""
    if not orders:
        return {
            "benchmark_version": BLIND_BENCHMARK_VERSION,
            "available": False,
            "reason": "order_baskets_missing",
            "blockers": ["observed_or_test_order_baskets_required"],
            "production_evidence": False,
            "market_leadership_proven": False,
        }

    architecture = architecture_truth_report(store_dna)
    if int(_number(((store_dna or {}).get("architecture") or {}).get("schema_version"))) == 2:
        return {
            "benchmark_version": BLIND_BENCHMARK_VERSION,
            "available": False,
            "reason": "architecture_v2_picker_benchmark_pending",
            "blockers": ["architecture_v2_picker_tour_benchmark_required"],
            "production_evidence": False,
            "market_leadership_proven": False,
        }
    layout_truth = layout_architecture_report(layout, store_dna)
    prepared = prepare_production_products(products)
    acceptance = production_acceptance_report(
        prepared,
        layout,
        store_dna,
        require_images=False,
    )
    shared_blockers = list(acceptance.get("blockers") or [])
    shared_blockers.extend(architecture.get("blockers") or [])
    shared_blockers.extend(layout_truth.get("blockers") or [])
    shared_blockers = list(dict.fromkeys(shared_blockers))
    if (
        not acceptance.get("production_ready")
        or not architecture.get("valid")
        or not layout_truth.get("valid")
    ):
        return {
            "benchmark_version": BLIND_BENCHMARK_VERSION,
            "available": False,
            "reason": "shared_physical_truth_invalid",
            "blockers": shared_blockers,
            "production_evidence": False,
            "market_leadership_proven": False,
        }

    evaluation_a = _candidate_evaluation(
        candidate=candidate_a,
        prepared_products=prepared,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
    )
    evaluation_b = _candidate_evaluation(
        candidate=candidate_b,
        prepared_products=prepared,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
    )
    if not evaluation_a.get("available") or not evaluation_b.get("available"):
        return {
            "benchmark_version": BLIND_BENCHMARK_VERSION,
            "available": False,
            "reason": "candidate_evaluation_unavailable",
            "candidate_a": evaluation_a,
            "candidate_b": evaluation_b,
            "production_evidence": False,
            "market_leadership_proven": False,
        }

    key_a = v3.objective_key(evaluation_a["objective"])
    key_b = v3.objective_key(evaluation_b["objective"])
    if key_a < key_b:
        winner = "A"
    elif key_b < key_a:
        winner = "B"
    else:
        winner = "TIE"

    delta_b_minus_a = {
        name: round(
            float(evaluation_b["objective"].get(name) or 0.0)
            - float(evaluation_a["objective"].get(name) or 0.0),
            6,
        )
        for name in v3.TOUR_OBJECTIVE_ORDER
    }
    evidence_fingerprint = _evidence_fingerprint(
        prepared_products=prepared,
        layout=layout,
        architecture_fingerprint=architecture.get("fingerprint"),
        orders=orders,
    )
    return {
        "benchmark_version": BLIND_BENCHMARK_VERSION,
        "available": True,
        "blind": True,
        "candidate_labels": ["A", "B"],
        "winner_on_repository_objective": winner,
        "objective_order": list(v3.TOUR_OBJECTIVE_ORDER),
        "objective_delta_b_minus_a": delta_b_minus_a,
        "candidate_a": evaluation_a,
        "candidate_b": evaluation_b,
        "shared_evidence_fingerprint": evidence_fingerprint,
        "basket_fingerprint": v3.order_basket_fingerprint(orders),
        "production_evidence": False,
        "market_leadership_proven": False,
        "promotion_allowed": False,
        "required_external_proof": [
            "blinded_expert_identity_reveal_after_scoring",
            "real_store_before_after_kpi_backtest",
            "field_installation_acceptance",
        ],
        "evidence_boundary": (
            "A/B ranking is a deterministic repository benchmark on supplied baskets; "
            "it is not proof of human preference, installation quality or live KPI gain"
        ),
    }
