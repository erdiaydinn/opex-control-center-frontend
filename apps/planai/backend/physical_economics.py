"""Evidence-bound economics for Planogram physical-layout proposals.

This module translates an already-computed V5 route improvement into a CFO-style
scenario only when every economic input is explicitly supplied, attested and
source-referenced. It never invents wages, order volume, working days, move cost
or route-to-time conversion.

The result is decision support, not finance approval, production evidence or an
investment authorization.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

ECONOMICS_VERSION = "planogram-physical-economics-v1"
MAX_CAPEX_ITEMS = 100
SUPPORTED_CURRENCY_LENGTH = 3


@dataclass(frozen=True)
class RangeAssumption:
    low: float
    base: float
    high: float
    source_ref: str
    attested: bool


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _currency(value: Any) -> str:
    return _text(value).upper()


def _range_assumption(
    raw: dict[str, Any] | None,
    *,
    name: str,
    minimum: float = 0.0,
    strictly_positive: bool = True,
) -> tuple[RangeAssumption | None, list[str]]:
    row = raw if isinstance(raw, dict) else {}
    blockers: list[str] = []
    source_ref = _text(row.get("source_ref"))
    attested = bool(row.get("attested") is True)
    low = _number(row.get("low"), float("nan"))
    base = _number(row.get("base"), float("nan"))
    high = _number(row.get("high"), float("nan"))

    values = (low, base, high)
    if any(math.isnan(value) for value in values):
        blockers.append(f"{name}_range_missing")
    else:
        threshold_ok = all(
            value > minimum if strictly_positive else value >= minimum
            for value in values
        )
        if not threshold_ok:
            blockers.append(f"{name}_range_invalid")
        if not (low <= base <= high):
            blockers.append(f"{name}_range_order_invalid")
    if not source_ref:
        blockers.append(f"{name}_source_ref_missing")
    if not attested:
        blockers.append(f"{name}_attestation_missing")
    if blockers:
        return None, blockers
    return RangeAssumption(
        low=low,
        base=base,
        high=high,
        source_ref=source_ref,
        attested=True,
    ), []


def _candidate_by_label(
    meta: dict[str, Any],
    label: str,
) -> dict[str, Any] | None:
    for row in meta.get("candidates") or []:
        if _text(row.get("label")) == label:
            return row
    return None


def _route_delta(result: dict[str, Any]) -> tuple[dict[str, float] | None, list[str]]:
    meta = result.get("physical_layout_optimizer")
    if not isinstance(meta, dict):
        return None, ["physical_layout_optimizer_missing"]
    if not meta.get("allowed"):
        return None, ["physical_layout_optimizer_not_allowed"]

    selected_label = _text(meta.get("selected_layout_label")) or "baseline"
    baseline = _candidate_by_label(meta, "baseline")
    selected = _candidate_by_label(meta, selected_label)
    if baseline is None:
        return None, ["baseline_candidate_summary_missing"]
    if selected is None:
        return None, ["selected_candidate_summary_missing"]

    baseline_avg = _number(baseline.get("tour_average_m"), float("nan"))
    selected_avg = _number(selected.get("tour_average_m"), float("nan"))
    baseline_p95 = _number(baseline.get("tour_p95_m"), float("nan"))
    selected_p95 = _number(selected.get("tour_p95_m"), float("nan"))
    coverage = _number(selected.get("tour_coverage_pct"), 0.0)
    route_metrics = (baseline_avg, selected_avg, baseline_p95, selected_p95)
    if any(math.isnan(value) for value in route_metrics):
        return None, ["route_metrics_missing"]
    if coverage < 100.0:
        return None, ["selected_route_coverage_incomplete"]
    return {
        "baseline_average_m": baseline_avg,
        "selected_average_m": selected_avg,
        "average_saving_m": baseline_avg - selected_avg,
        "baseline_p95_m": baseline_p95,
        "selected_p95_m": selected_p95,
        "p95_saving_m": baseline_p95 - selected_p95,
        "selected_route_coverage_pct": coverage,
    }, []


def _capex(
    items: list[dict[str, Any]] | None,
    *,
    currency: str,
) -> tuple[float | None, list[dict[str, Any]], list[str]]:
    rows = list(items or [])
    if not rows:
        return None, [], ["capex_items_missing"]
    if len(rows) > MAX_CAPEX_ITEMS:
        return None, [], ["capex_item_limit_exceeded"]

    blockers: list[str] = []
    normalized: list[dict[str, Any]] = []
    total = 0.0
    for index, row in enumerate(rows):
        amount = _number(row.get("amount"), float("nan"))
        row_currency = _currency(row.get("currency"))
        source_ref = _text(row.get("source_ref"))
        attested = row.get("attested") is True
        label = _text(row.get("label")) or f"item-{index + 1}"
        if math.isnan(amount) or amount < 0:
            blockers.append(f"capex_amount_invalid:index:{index}")
            continue
        if row_currency != currency:
            blockers.append(f"capex_currency_mismatch:index:{index}")
        if not source_ref:
            blockers.append(f"capex_source_ref_missing:index:{index}")
        if not attested:
            blockers.append(f"capex_attestation_missing:index:{index}")
        normalized.append(
            {
                "label": label,
                "amount": round(amount, 2),
                "currency": row_currency,
                "source_ref": source_ref or None,
                "attested": attested,
            }
        )
        total += max(0.0, amount)
    if blockers:
        return None, normalized, blockers
    return round(total, 2), normalized, []


def _scenario(
    *,
    name: str,
    route_saving_m: float,
    orders_per_day: float,
    operating_days_per_year: float,
    effective_seconds_per_meter: float,
    loaded_labor_cost_per_hour: float,
    capex: float,
    currency: str,
) -> dict[str, Any]:
    route_seconds_saved_per_order = max(0.0, route_saving_m) * effective_seconds_per_meter
    daily_hours_saved = route_seconds_saved_per_order * orders_per_day / 3600.0
    daily_labor_value = daily_hours_saved * loaded_labor_cost_per_hour
    annual_labor_value = daily_labor_value * operating_days_per_year
    first_year_net = annual_labor_value - capex
    payback_operating_days = capex / daily_labor_value if daily_labor_value > 0 else None
    roi_pct = ((annual_labor_value - capex) / capex * 100.0) if capex > 0 else None
    return {
        "scenario": name,
        "route_saving_m_per_order": round(max(0.0, route_saving_m), 3),
        "route_seconds_saved_per_order": round(route_seconds_saved_per_order, 3),
        "daily_hours_saved": round(daily_hours_saved, 3),
        "daily_labor_value": round(daily_labor_value, 2),
        "annual_labor_value": round(annual_labor_value, 2),
        "capex": round(capex, 2),
        "first_year_net_value": round(first_year_net, 2),
        "payback_operating_days": (
            round(payback_operating_days, 1)
            if payback_operating_days is not None
            else None
        ),
        "first_year_roi_pct": round(roi_pct, 2) if roi_pct is not None else None,
        "currency": currency,
        "economically_positive_first_year": first_year_net > 0,
    }


def evaluate_physical_layout_economics(
    *,
    physical_layout_result: dict[str, Any],
    assumptions: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate V5 economics using only explicit attested input ranges."""
    route, blockers = _route_delta(physical_layout_result)
    if blockers:
        return {
            "economics_version": ECONOMICS_VERSION,
            "available": False,
            "blockers": blockers,
            "production_evidence": False,
            "finance_approved": False,
            "investment_decision_allowed": False,
        }

    currency = _currency(assumptions.get("currency"))
    if len(currency) != SUPPORTED_CURRENCY_LENGTH or not currency.isalpha():
        blockers.append("currency_invalid")

    orders, order_blockers = _range_assumption(
        assumptions.get("orders_per_day"),
        name="orders_per_day",
    )
    days, day_blockers = _range_assumption(
        assumptions.get("operating_days_per_year"),
        name="operating_days_per_year",
        minimum=1.0,
    )
    seconds_per_meter, speed_blockers = _range_assumption(
        assumptions.get("effective_seconds_per_meter"),
        name="effective_seconds_per_meter",
    )
    labor_cost, labor_blockers = _range_assumption(
        assumptions.get("loaded_labor_cost_per_hour"),
        name="loaded_labor_cost_per_hour",
    )
    blockers.extend(order_blockers)
    blockers.extend(day_blockers)
    blockers.extend(speed_blockers)
    blockers.extend(labor_blockers)

    capex_total, capex_items, capex_blockers = _capex(
        assumptions.get("capex_items"),
        currency=currency,
    )
    blockers.extend(capex_blockers)
    if blockers or None in (orders, days, seconds_per_meter, labor_cost, capex_total):
        return {
            "economics_version": ECONOMICS_VERSION,
            "available": False,
            "blockers": list(dict.fromkeys(blockers)),
            "currency": currency or None,
            "capex_items": capex_items,
            "production_evidence": False,
            "finance_approved": False,
            "investment_decision_allowed": False,
        }

    assert orders is not None
    assert days is not None
    assert seconds_per_meter is not None
    assert labor_cost is not None
    assert capex_total is not None
    assert route is not None

    scenario_values = {
        "downside": (
            orders.low,
            days.low,
            seconds_per_meter.low,
            labor_cost.low,
        ),
        "base": (
            orders.base,
            days.base,
            seconds_per_meter.base,
            labor_cost.base,
        ),
        "upside": (
            orders.high,
            days.high,
            seconds_per_meter.high,
            labor_cost.high,
        ),
    }
    scenarios = [
        _scenario(
            name=name,
            route_saving_m=route["average_saving_m"],
            orders_per_day=values[0],
            operating_days_per_year=values[1],
            effective_seconds_per_meter=values[2],
            loaded_labor_cost_per_hour=values[3],
            capex=capex_total,
            currency=currency,
        )
        for name, values in scenario_values.items()
    ]
    source_manifest = {
        "orders_per_day": orders.source_ref,
        "operating_days_per_year": days.source_ref,
        "effective_seconds_per_meter": seconds_per_meter.source_ref,
        "loaded_labor_cost_per_hour": labor_cost.source_ref,
        "capex_items": [row["source_ref"] for row in capex_items],
    }
    fingerprint_payload = {
        "route": route,
        "assumptions": assumptions,
        "source_manifest": source_manifest,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "economics_version": ECONOMICS_VERSION,
        "available": True,
        "currency": currency,
        "route": route,
        "capex_total": capex_total,
        "capex_items": capex_items,
        "scenarios": scenarios,
        "source_manifest": source_manifest,
        "economics_fingerprint": fingerprint,
        "all_inputs_attested": True,
        "production_evidence": False,
        "finance_approved": False,
        "investment_decision_allowed": False,
        "auto_execute_allowed": False,
        "evidence_boundary": (
            "economics are derived from repository V5 route deltas and supplied "
            "attested financial/operational assumptions; realized savings require "
            "post-installation measurement and finance validation"
        ),
    }
