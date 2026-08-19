"""Blind A/B benchmark for Architecture V2 oriented Store DNA.

This is deliberately separate from the V1 production-facing benchmark. It
reuses the same candidate hydration/master-truth rules, but route evaluation is
performed by the V2 oriented-polygon picker simulator. Promotion authority stays
false until V2 itself has field acceptance.
"""

from __future__ import annotations

from typing import Any

import blind_benchmark as blind_v1
import physical_optimizer as objective_v1
import physical_optimizer_v3 as objective_v3
from architecture_truth_v2 import (
    architecture_truth_report_v2,
    layout_architecture_report_v2,
)
from physical_engine import prepare_production_products
from physical_truth import production_acceptance_report
from picker_tour_simulation_v2 import simulate_picker_tours_v2

BLIND_BENCHMARK_V2_VERSION = "planogram-blind-ab-benchmark-v2-oriented-polygons"


def _number(value: Any, default: float = 0.0) -> float:
    return blind_v1._number(value, default)


def _candidate_evaluation_v2(
    *,
    candidate: dict[str, Any],
    prepared_products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    hydrated = blind_v1._hydrate_candidate(
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
    tour_report = simulate_picker_tours_v2(
        result=result,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
    )
    tour = objective_v3._tour_summary(tour_report)
    blockers = list(hydrated.get("blockers") or [])
    operational = hydrated.get("operational_validation") or {}
    if int(operational.get("violation_count") or 0):
        blockers.append("candidate_operational_physical_violation")
    if not tour.get("available"):
        blockers.append(
            "candidate_picker_tour_v2_unavailable:"
            + blind_v1._text(tour_report.get("reason") or "unknown")
        )

    objective: dict[str, float | int] = {
        "hard_violation_count": len(list(dict.fromkeys(blockers)))
        + int(operational.get("violation_count") or 0)
        + len(hydrated.get("capacity_violations") or []),
        "weighted_unplaced_sales": blind_v1._weighted_unplaced_sales(
            result,
            prepared_products,
        ),
        "unplaced_sku_count": len(result.get("unplaced") or []),
        "tour_unsimulated_order_count": int(tour.get("unsimulated_order_count") or 0),
        "tour_p95_m": float(tour.get("p95_m") or 0.0),
        "tour_average_m": float(tour.get("average_m") or 0.0),
        "coverage_shortfall": float(objective_v1._coverage_shortfall(result)),
        "brand_fragmentation": float(objective_v1._brand_fragmentation(result)),
        "capacity_pressure": float(objective_v1._capacity_pressure(result)),
    }
    return {
        "available": True,
        "objective": objective,
        "objective_key": list(objective_v3.objective_key(objective)),
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
            "preview_only": True,
            "production_evidence": False,
            "non_orthogonal_element_count": tour_report.get(
                "non_orthogonal_element_count"
            ),
            "non_orthogonal_module_count": tour_report.get(
                "non_orthogonal_module_count"
            ),
        },
    }


def benchmark_candidates_v2(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
) -> dict[str, Any]:
    """Blindly compare A/B under the same Architecture V2 measured evidence."""
    if not orders:
        return {
            "benchmark_version": BLIND_BENCHMARK_V2_VERSION,
            "available": False,
            "reason": "order_baskets_missing",
            "blockers": ["observed_or_test_order_baskets_required"],
            "preview_only": True,
            "production_evidence": False,
            "market_leadership_proven": False,
        }

    architecture = architecture_truth_report_v2(store_dna)
    layout_truth = layout_architecture_report_v2(layout, store_dna)
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
            "benchmark_version": BLIND_BENCHMARK_V2_VERSION,
            "available": False,
            "reason": "shared_physical_truth_invalid",
            "blockers": shared_blockers,
            "preview_only": True,
            "production_evidence": False,
            "market_leadership_proven": False,
        }

    evaluation_a = _candidate_evaluation_v2(
        candidate=candidate_a,
        prepared_products=prepared,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
    )
    evaluation_b = _candidate_evaluation_v2(
        candidate=candidate_b,
        prepared_products=prepared,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
    )
    if not evaluation_a.get("available") or not evaluation_b.get("available"):
        return {
            "benchmark_version": BLIND_BENCHMARK_V2_VERSION,
            "available": False,
            "reason": "candidate_evaluation_unavailable",
            "candidate_a": evaluation_a,
            "candidate_b": evaluation_b,
            "preview_only": True,
            "production_evidence": False,
            "market_leadership_proven": False,
        }

    key_a = objective_v3.objective_key(evaluation_a["objective"])
    key_b = objective_v3.objective_key(evaluation_b["objective"])
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
        for name in objective_v3.TOUR_OBJECTIVE_ORDER
    }
    evidence_fingerprint = blind_v1._evidence_fingerprint(
        prepared_products=prepared,
        layout=layout,
        architecture_fingerprint=architecture.get("fingerprint"),
        orders=orders,
    )
    return {
        "benchmark_version": BLIND_BENCHMARK_V2_VERSION,
        "available": True,
        "blind": True,
        "preview_only": True,
        "spatial_contract": "store-architecture-v2-oriented-polygons",
        "candidate_labels": ["A", "B"],
        "winner_on_repository_objective": winner,
        "objective_order": list(objective_v3.TOUR_OBJECTIVE_ORDER),
        "objective_delta_b_minus_a": delta_b_minus_a,
        "candidate_a": evaluation_a,
        "candidate_b": evaluation_b,
        "shared_evidence_fingerprint": evidence_fingerprint,
        "basket_fingerprint": objective_v3.order_basket_fingerprint(orders),
        "non_orthogonal_element_count": architecture.get(
            "non_orthogonal_element_count"
        ),
        "non_orthogonal_module_count": layout_truth.get(
            "non_orthogonal_module_count"
        ),
        "production_authority": False,
        "production_evidence": False,
        "market_leadership_proven": False,
        "promotion_allowed": False,
        "required_external_proof": [
            "architecture_v2_field_measurement_acceptance",
            "blinded_expert_identity_reveal_after_scoring",
            "real_store_before_after_kpi_backtest",
            "field_installation_acceptance",
        ],
        "evidence_boundary": (
            "V2 A/B ranking uses supplied baskets and oriented measured preview "
            "geometry; it does not promote Architecture V2 or prove live KPI gain"
        ),
    }
