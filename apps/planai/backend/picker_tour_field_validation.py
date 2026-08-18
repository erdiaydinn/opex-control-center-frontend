"""Field-validation contract for PlanAI picker-tour simulation.

Repository/synthetic tests may exercise this code, but acceptance requires
caller-supplied observed field distances for the same order baskets. No default
threshold silently converts simulation output into production truth.
"""

from __future__ import annotations

import hashlib
import json
from math import ceil
from typing import Any

from picker_tour_simulation import MAX_EXPLAINED_ORDERS, simulate_picker_tours

FIELD_VALIDATION_VERSION = "picker-tour-field-validation-v1"
MAX_FIELD_VALIDATION_ORDERS = MAX_EXPLAINED_ORDERS


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _order_hash(order_id: str) -> str:
    return hashlib.sha256(order_id.encode("utf-8")).hexdigest()[:16]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_picker_tour_against_field(
    *,
    result: dict[str, Any],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    thresholds: dict[str, float] | None = None,
    resolution_m: float = 0.5,
) -> dict[str, Any]:
    if not observations:
        return {
            "validation_version": FIELD_VALIDATION_VERSION,
            "available": False,
            "acceptance_evaluated": False,
            "acceptance_passed": None,
            "reason": "field_observations_missing",
            "production_evidence": False,
        }
    if len(orders) > MAX_FIELD_VALIDATION_ORDERS:
        return {
            "validation_version": FIELD_VALIDATION_VERSION,
            "available": False,
            "acceptance_evaluated": False,
            "acceptance_passed": None,
            "reason": "field_validation_sample_limit_exceeded",
            "limit": MAX_FIELD_VALIDATION_ORDERS,
            "production_evidence": False,
        }

    simulation = simulate_picker_tours(
        result=result,
        layout=layout,
        store_dna=store_dna,
        orders=orders,
        resolution_m=resolution_m,
    )
    if not simulation.get("available"):
        return {
            "validation_version": FIELD_VALIDATION_VERSION,
            "available": False,
            "acceptance_evaluated": False,
            "acceptance_passed": None,
            "reason": "picker_tour_simulation_unavailable",
            "simulation_reason": simulation.get("reason"),
            "production_evidence": False,
        }

    predicted = {
        _text(row.get("order_id")): _num(row.get("distance_m"))
        for row in simulation.get("explained_orders") or []
        if _text(row.get("order_id")) and _num(row.get("distance_m")) > 0
    }
    observed = {
        _text(row.get("order_id")): _num(row.get("distance_m"))
        for row in observations
        if _text(row.get("order_id")) and _num(row.get("distance_m")) > 0
    }
    matched_ids = sorted(set(predicted).intersection(observed))
    if not matched_ids:
        return {
            "validation_version": FIELD_VALIDATION_VERSION,
            "available": False,
            "acceptance_evaluated": False,
            "acceptance_passed": None,
            "reason": "no_matching_field_observations",
            "production_evidence": False,
        }

    absolute_errors = [abs(predicted[key] - observed[key]) for key in matched_ids]
    percentage_errors = [
        abs(predicted[key] - observed[key]) * 100.0 / observed[key]
        for key in matched_ids
        if observed[key] > 0
    ]
    signed_errors = [predicted[key] - observed[key] for key in matched_ids]
    match_pct = round(len(matched_ids) * 100.0 / max(len(orders), 1), 2)
    metrics = {
        "matched_order_count": len(matched_ids),
        "input_order_count": len(orders),
        "match_pct": match_pct,
        "mae_m": round(sum(absolute_errors) / len(absolute_errors), 3),
        "median_absolute_error_m": _percentile(absolute_errors, 0.50),
        "p95_absolute_error_m": _percentile(absolute_errors, 0.95),
        "mape_pct": round(sum(percentage_errors) / len(percentage_errors), 3)
        if percentage_errors
        else 0.0,
        "mean_bias_m": round(sum(signed_errors) / len(signed_errors), 3),
    }

    threshold_values = dict(thresholds or {})
    acceptance_evaluated = bool(threshold_values)
    threshold_results: dict[str, bool] = {}
    allowed_thresholds = {
        "min_match_pct": (lambda value: metrics["match_pct"] >= value),
        "max_mae_m": (lambda value: metrics["mae_m"] <= value),
        "max_p95_absolute_error_m": (
            lambda value: metrics["p95_absolute_error_m"] <= value
        ),
        "max_mape_pct": (lambda value: metrics["mape_pct"] <= value),
    }
    unknown_thresholds = sorted(set(threshold_values) - set(allowed_thresholds))
    if unknown_thresholds:
        return {
            "validation_version": FIELD_VALIDATION_VERSION,
            "available": False,
            "acceptance_evaluated": False,
            "acceptance_passed": None,
            "reason": "unknown_acceptance_threshold",
            "unknown_thresholds": unknown_thresholds,
            "production_evidence": False,
        }
    for key, value in threshold_values.items():
        threshold_results[key] = allowed_thresholds[key](float(value))
    acceptance_passed = (
        all(threshold_results.values()) if acceptance_evaluated else None
    )

    comparison_rows = [
        {
            "order_ref_hash": _order_hash(order_id),
            "predicted_distance_m": round(predicted[order_id], 3),
            "observed_distance_m": round(observed[order_id], 3),
            "absolute_error_m": round(
                abs(predicted[order_id] - observed[order_id]),
                3,
            ),
        }
        for order_id in matched_ids
    ]
    fingerprint_payload = {
        "validation_version": FIELD_VALIDATION_VERSION,
        "architecture_fingerprint": simulation.get("architecture_fingerprint"),
        "metrics": metrics,
        "thresholds": threshold_values,
        "threshold_results": threshold_results,
        "comparisons": comparison_rows,
    }
    return {
        "validation_version": FIELD_VALIDATION_VERSION,
        "available": True,
        "production_evidence": False,
        "truth_boundary": (
            "field observations are caller supplied; repository execution cannot "
            "attest device/calibration/warehouse provenance"
        ),
        "acceptance_evaluated": acceptance_evaluated,
        "acceptance_passed": acceptance_passed,
        "acceptance_state": (
            "PASS"
            if acceptance_passed is True
            else "FAIL"
            if acceptance_passed is False
            else "EVIDENCE_ONLY_NO_THRESHOLDS"
        ),
        "metrics": metrics,
        "thresholds": threshold_values,
        "threshold_results": threshold_results,
        "comparisons": comparison_rows,
        "architecture_fingerprint": simulation.get("architecture_fingerprint"),
        "validation_fingerprint": _fingerprint(fingerprint_payload),
    }
