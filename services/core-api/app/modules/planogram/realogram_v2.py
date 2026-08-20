"""Multi-source temporal realogram normalization and action-queue preview."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from app.modules.planogram.temporal_realogram import evaluate_temporal_realogram

REALOGRAM_V2_CONTRACT = "planogram-temporal-realogram-v2-multisource"
SUPPORTED_PROVIDERS = {
    "shelf_cv",
    "iot_shelf",
    "wms",
    "scanner",
    "picker_app",
    "cold_chain_sensor",
    "manual_verified",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _event_key(event: dict[str, Any]) -> tuple[str, str]:
    provider = _text(event.get("provider")).lower()
    provider_event_id = _text(event.get("provider_event_id") or event.get("event_id"))
    if provider_event_id:
        return provider, provider_event_id
    digest = hashlib.sha256(
        json.dumps(event, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    return provider, digest


def _action_for_alert(alert: dict[str, Any], index: int) -> dict[str, Any] | None:
    code = _text(alert.get("alert_code"))
    sku = _text(alert.get("sku")).upper()
    if not code:
        return None
    mapping = {
        "cold_chain_transition_breach": ("P0", "quarantine_and_quality_review"),
        "confirmed_oos": ("P1", "replenish_or_substitute_review"),
        "recurring_oos": ("P1", "assortment_replenishment_review"),
        "sku_misplaced": ("P1", "shelf_correction_review"),
        "barcode_plan_mismatch": ("P1", "barcode_location_review"),
        "pick_sequence_location_mismatch": ("P2", "picker_route_review"),
        "facing_mismatch": ("P2", "facing_correction_review"),
        "sku_not_in_plan": ("P2", "assortment_exception_review"),
        "realogram_state_stale": ("P2", "refresh_shelf_evidence"),
    }
    priority, action = mapping.get(code, ("P3", "manual_review"))
    return {
        "action_id": f"realogram-{index + 1}",
        "priority": priority,
        "action": action,
        "alert_code": code,
        "sku": sku or None,
        "auto_execute_allowed": False,
    }


def evaluate_temporal_realogram_v2(
    *,
    plan_payload: dict[str, Any],
    events: list[dict[str, Any]],
    as_of: str | None = None,
    stale_after_minutes: int = 240,
) -> dict[str, Any]:
    if not events:
        return {
            "contract": REALOGRAM_V2_CONTRACT,
            "available": False,
            "blockers": ["events_missing"],
            "field_truth": False,
            "auto_execute_allowed": False,
        }
    clean: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    provider_counts: Counter[str] = Counter()
    provenance_complete = True
    for index, raw in enumerate(events):
        event = dict(raw)
        provider = _text(event.get("provider")).lower()
        source_ref = _text(event.get("source_ref"))
        if provider not in SUPPORTED_PROVIDERS:
            invalid.append({"index": index, "reason": "provider_unsupported"})
            continue
        if not source_ref:
            invalid.append({"index": index, "reason": "source_ref_missing"})
            provenance_complete = False
            continue
        key = _event_key(event)
        if key in seen:
            duplicates.append({"index": index, "provider": provider})
            continue
        seen.add(key)
        provider_counts[provider] += 1
        event.pop("provider", None)
        event.pop("provider_event_id", None)
        event.pop("event_id", None)
        clean.append(event)
    if not clean:
        return {
            "contract": REALOGRAM_V2_CONTRACT,
            "available": False,
            "blockers": ["no_valid_events"],
            "duplicate_event_count": len(duplicates),
            "invalid_event_count": len(invalid),
            "field_truth": False,
            "auto_execute_allowed": False,
        }

    base = evaluate_temporal_realogram(
        plan_payload=plan_payload,
        events=clean,
        as_of=as_of,
        stale_after_minutes=stale_after_minutes,
    )
    actions = [
        action
        for index, alert in enumerate(base.get("alerts") or [])
        if (action := _action_for_alert(alert, index)) is not None
    ]
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    actions.sort(key=lambda row: (priority_order[row["priority"]], row["action_id"]))
    return {
        "contract": REALOGRAM_V2_CONTRACT,
        "available": bool(base.get("available")),
        "preview_only": True,
        "base_realogram": base,
        "provider_event_counts": dict(sorted(provider_counts.items())),
        "supported_providers": sorted(SUPPORTED_PROVIDERS),
        "accepted_event_count": len(clean),
        "duplicate_event_count": len(duplicates),
        "invalid_event_count": len(invalid),
        "duplicates": duplicates[:500],
        "invalid_events": invalid[:500],
        "provenance_fields_complete": provenance_complete and not invalid,
        "server_connector_provenance_verified": False,
        "action_count": len(actions),
        "action_queue": actions[:10_000],
        "field_truth": False,
        "production_evidence": False,
        "auto_execute_allowed": False,
        "auto_correct_allowed": False,
        "evidence_boundary": (
            "provider labels and source references are request supplied in this preview; "
            "server-bound connector provenance and field acceptance remain required"
        ),
    }
