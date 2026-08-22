"""Temporal realogram event evaluation with fail-closed field-truth boundaries.

This module does not run computer vision. It consumes already-produced shelf,
stock, pick, substitution and cold-chain observations, keeps their provenance,
and builds a deterministic time-aware comparison against an approved-plan-shaped
baseline. Presence can be observed; absence is never inferred from silence.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from statistics import mean
from typing import Any

REALOGRAM_CONTRACT = "planogram-temporal-realogram-v1"
MIN_SCAN_CONFIDENCE = 0.80
MIN_IMAGE_QUALITY = 0.70
MAX_OCCLUSION_PCT = 35.0
MAX_EVENTS = 100_000


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _location(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("aisle_id")),
        _text(row.get("module_id")),
        _text(row.get("shelf_no")),
    )


def _baseline(plan: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], str]:
    expected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for aisle in plan.get("aisles") or []:
        for module in aisle.get("modules") or []:
            for shelf in module.get("shelves") or []:
                location = (
                    _text(aisle.get("aisle_id")),
                    _text(module.get("module_id")),
                    _text(shelf.get("shelf_no")),
                )
                for product in shelf.get("products") or []:
                    sku = _text(product.get("sku") or product.get("SKU")).upper()
                    if not sku:
                        continue
                    expected[sku].append(
                        {
                            "location": location,
                            "facing_count": int(
                                _number(
                                    product.get("facing_count") or product.get("facing"),
                                    1,
                                )
                            ),
                            "barcode": _text(
                                product.get("barcode") or product.get("product_barcodes")
                            ),
                        }
                    )
    fingerprint = hashlib.sha256(
        json.dumps(
            plan,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return dict(expected), fingerprint


def _event_fingerprint(events: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(
            events,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def evaluate_temporal_realogram(
    *,
    plan_payload: dict[str, Any],
    events: list[dict[str, Any]],
    as_of: str | None = None,
    stale_after_minutes: int = 240,
) -> dict[str, Any]:
    if not events or len(events) > MAX_EVENTS:
        return {
            "contract": REALOGRAM_CONTRACT,
            "available": False,
            "blockers": ["event_count_invalid"],
            "production_evidence": False,
            "field_truth": False,
        }
    expected, plan_fp = _baseline(plan_payload)
    parsed_events: list[tuple[datetime, int, dict[str, Any]]] = []
    invalid_events: list[str] = []
    for index, event in enumerate(events):
        timestamp = _parse_time(event.get("observed_at"))
        event_type = _text(event.get("event_type")).lower()
        sku = _text(event.get("sku")).upper()
        source_ref = _text(event.get("source_ref"))
        if timestamp is None or not event_type or not sku or not source_ref:
            invalid_events.append(f"index:{index}")
            continue
        parsed_events.append(
            (
                timestamp,
                index,
                {
                    **event,
                    "event_type": event_type,
                    "sku": sku,
                    "source_ref": source_ref,
                },
            )
        )
    parsed_events.sort(key=lambda row: (row[0], row[1]))
    if not parsed_events:
        return {
            "contract": REALOGRAM_CONTRACT,
            "available": False,
            "blockers": ["no_valid_events"],
            "invalid_events": invalid_events,
            "production_evidence": False,
            "field_truth": False,
        }

    as_of_time = _parse_time(as_of) if as_of else parsed_events[-1][0]
    if as_of_time is None:
        return {
            "contract": REALOGRAM_CONTRACT,
            "available": False,
            "blockers": ["as_of_invalid"],
            "production_evidence": False,
            "field_truth": False,
        }

    alerts: list[dict[str, Any]] = []
    review_required: list[dict[str, Any]] = []
    latest_scan: dict[str, dict[str, Any]] = {}
    sku_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "scan_count": 0,
            "oos_count": 0,
            "replenishment_count": 0,
            "pick_sequence_step_count": 0,
            "barcode_pick_count": 0,
            "substitution_count": 0,
            "cold_chain_transition_count": 0,
            "replenishment_latencies_minutes": [],
            "closed_oos_count": 0,
        }
    )
    open_oos: dict[str, list[datetime]] = defaultdict(list)
    flow_events: dict[str, list[str]] = defaultdict(list)
    normalized_events: list[dict[str, Any]] = []

    for timestamp, _index, event in parsed_events:
        sku = event["sku"]
        event_type = event["event_type"]
        stats = sku_stats[sku]
        flow_id = _text(event.get("flow_id"))
        if flow_id:
            flow_events[flow_id].append(event_type)
        normalized = {
            "observed_at": _iso(timestamp),
            "event_type": event_type,
            "sku": sku,
            "source_ref": event["source_ref"],
            "flow_id": flow_id or None,
        }

        if event_type == "shelf_scan":
            stats["scan_count"] += 1
            confidence = _number(event.get("confidence"), -1.0)
            image_quality = _number(event.get("image_quality_score"), -1.0)
            occlusion_pct = _number(event.get("occlusion_pct"), -1.0)
            location = _location(event)
            facing = int(_number(event.get("facing_count"), 0))
            usable = (
                all(location)
                and facing >= 1
                and confidence >= MIN_SCAN_CONFIDENCE
                and image_quality >= MIN_IMAGE_QUALITY
                and 0 <= occlusion_pct <= MAX_OCCLUSION_PCT
            )
            normalized.update(
                {
                    "location": {
                        "aisle_id": location[0],
                        "module_id": location[1],
                        "shelf_no": location[2],
                    },
                    "facing_count": facing,
                    "confidence": confidence,
                    "image_quality_score": image_quality,
                    "occlusion_pct": occlusion_pct,
                    "usable": usable,
                }
            )
            if not usable:
                review_required.append(
                    {**normalized, "reason": "scan_evidence_below_threshold"}
                )
            else:
                expected_rows = expected.get(sku) or []
                expected_locations = {row["location"] for row in expected_rows}
                if expected_rows and location not in expected_locations:
                    alerts.append(
                        {**normalized, "alert_code": "sku_misplaced", "severity": "high"}
                    )
                elif not expected_rows:
                    alerts.append(
                        {
                            **normalized,
                            "alert_code": "sku_not_in_plan",
                            "severity": "medium",
                        }
                    )
                else:
                    expected_facing = next(
                        row["facing_count"]
                        for row in expected_rows
                        if row["location"] == location
                    )
                    if facing != expected_facing:
                        alerts.append(
                            {
                                **normalized,
                                "alert_code": "facing_mismatch",
                                "severity": "medium",
                                "expected_facing_count": expected_facing,
                            }
                        )
                latest_scan[sku] = normalized

        elif event_type == "inventory_oos":
            stats["oos_count"] += 1
            open_oos[sku].append(timestamp)
            alerts.append(
                {**normalized, "alert_code": "confirmed_oos", "severity": "high"}
            )

        elif event_type == "replenishment":
            stats["replenishment_count"] += 1
            if open_oos[sku]:
                opened = open_oos[sku].pop(0)
                latency = max(0.0, (timestamp - opened).total_seconds() / 60.0)
                stats["replenishment_latencies_minutes"].append(latency)
                stats["closed_oos_count"] += 1
                normalized["closed_oos_latency_minutes"] = round(latency, 2)

        elif event_type == "pick_sequence_step":
            stats["pick_sequence_step_count"] += 1
            sequence_no = int(_number(event.get("sequence_no"), 0))
            location = _location(event)
            normalized["sequence_no"] = sequence_no or None
            if all(location):
                normalized["location"] = {
                    "aisle_id": location[0],
                    "module_id": location[1],
                    "shelf_no": location[2],
                }
                expected_locations = {
                    row["location"] for row in expected.get(sku, [])
                }
                if expected_locations and location not in expected_locations:
                    alerts.append(
                        {
                            **normalized,
                            "alert_code": "pick_sequence_location_mismatch",
                            "severity": "high",
                        }
                    )

        elif event_type == "barcode_pick":
            stats["barcode_pick_count"] += 1
            barcode = _text(event.get("barcode"))
            normalized["barcode"] = barcode or None
            expected_barcodes = {
                row["barcode"] for row in expected.get(sku, []) if row["barcode"]
            }
            if expected_barcodes and barcode and barcode not in expected_barcodes:
                alerts.append(
                    {
                        **normalized,
                        "alert_code": "barcode_plan_mismatch",
                        "severity": "high",
                    }
                )

        elif event_type == "substitution":
            stats["substitution_count"] += 1
            substitute_sku = _text(event.get("substitute_sku")).upper()
            normalized["substitute_sku"] = substitute_sku or None
            if not substitute_sku:
                review_required.append(
                    {**normalized, "reason": "substitute_sku_missing"}
                )

        elif event_type == "cold_chain_transition":
            stats["cold_chain_transition_count"] += 1
            elapsed = _number(event.get("elapsed_seconds"), -1.0)
            allowed = _number(event.get("allowed_seconds"), -1.0)
            temperature = _number(event.get("temperature_c"), float("nan"))
            minimum = _number(event.get("min_temperature_c"), float("nan"))
            maximum = _number(event.get("max_temperature_c"), float("nan"))
            breach = elapsed >= 0 and allowed >= 0 and elapsed > allowed
            if not any(math.isnan(value) for value in (temperature, minimum, maximum)):
                breach = breach or not minimum <= temperature <= maximum
            normalized.update(
                {"elapsed_seconds": elapsed, "allowed_seconds": allowed}
            )
            if breach:
                alerts.append(
                    {
                        **normalized,
                        "alert_code": "cold_chain_transition_breach",
                        "severity": "critical",
                    }
                )

        else:
            review_required.append(
                {**normalized, "reason": "unsupported_event_type"}
            )

        normalized_events.append(normalized)

    sku_summaries: list[dict[str, Any]] = []
    for sku in sorted(sku_stats):
        stats = sku_stats[sku]
        latencies = stats.pop("replenishment_latencies_minutes")
        latest = latest_scan.get(sku)
        stale = False
        age_minutes = None
        if latest:
            latest_time = _parse_time(latest["observed_at"])
            if latest_time is not None:
                age_minutes = max(
                    0.0,
                    (as_of_time - latest_time).total_seconds() / 60.0,
                )
                stale = age_minutes > stale_after_minutes
                if stale:
                    alerts.append(
                        {
                            "sku": sku,
                            "alert_code": "realogram_state_stale",
                            "severity": "medium",
                            "age_minutes": round(age_minutes, 2),
                        }
                    )
        if stats["oos_count"] >= 3:
            alerts.append(
                {
                    "sku": sku,
                    "alert_code": "recurring_oos",
                    "severity": "high",
                    "oos_count": stats["oos_count"],
                }
            )
        sku_summaries.append(
            {
                "sku": sku,
                **stats,
                "open_oos_count": len(open_oos[sku]),
                "mean_replenishment_latency_minutes": (
                    round(mean(latencies), 2) if latencies else None
                ),
                "latest_scan": latest,
                "latest_scan_age_minutes": (
                    round(age_minutes, 2) if age_minutes is not None else None
                ),
                "latest_scan_stale": stale,
            }
        )

    flow_traces = [
        {
            "flow_id": flow_id,
            "event_sequence": sequence,
            "contains_pick_sequence_step": "pick_sequence_step" in sequence,
            "contains_barcode_pick": "barcode_pick" in sequence,
            "contains_oos": "inventory_oos" in sequence,
            "contains_substitution": "substitution" in sequence,
            "contains_cold_chain_transition": "cold_chain_transition" in sequence,
        }
        for flow_id, sequence in sorted(flow_events.items())
    ]
    total_oos = sum(row["oos_count"] for row in sku_summaries)
    closed_oos = sum(row["closed_oos_count"] for row in sku_summaries)

    return {
        "contract": REALOGRAM_CONTRACT,
        "available": True,
        "preview_only": True,
        "production_evidence": False,
        "field_truth": False,
        "auto_correct_allowed": False,
        "plan_fingerprint": plan_fp,
        "event_fingerprint": _event_fingerprint(normalized_events),
        "as_of": _iso(as_of_time),
        "stale_after_minutes": stale_after_minutes,
        "valid_event_count": len(parsed_events),
        "invalid_event_count": len(invalid_events),
        "invalid_events": invalid_events[:500],
        "alert_count": len(alerts),
        "alerts": alerts[:10_000],
        "review_required_count": len(review_required),
        "review_required": review_required[:10_000],
        "sku_summaries": sku_summaries[:10_000],
        "latest_realogram": [latest_scan[sku] for sku in sorted(latest_scan)],
        "flow_traces": flow_traces[:10_000],
        "closed_loop": {
            "confirmed_oos_count": total_oos,
            "oos_with_replenishment_closure_count": closed_oos,
            "open_oos_count": sum(
                row["open_oos_count"] for row in sku_summaries
            ),
            "substitution_event_count": sum(
                row["substitution_count"] for row in sku_summaries
            ),
            "pick_sequence_step_event_count": sum(
                row["pick_sequence_step_count"] for row in sku_summaries
            ),
            "barcode_pick_event_count": sum(
                row["barcode_pick_count"] for row in sku_summaries
            ),
            "cold_chain_transition_event_count": sum(
                row["cold_chain_transition_count"] for row in sku_summaries
            ),
        },
        "evidence_boundary": (
            "temporal realogram state is derived only from supplied sourced observations; "
            "silence never proves absence, and automated correction/publishing remains disabled"
        ),
    }
