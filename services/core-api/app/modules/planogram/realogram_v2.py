"""Multi-source temporal realogram normalization and action-queue preview."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from app.modules.planogram.temporal_realogram import evaluate_temporal_realogram

REALOGRAM_V2_CONTRACT = "planogram-temporal-realogram-v2-multisource-action-state"
SUPPORTED_PROVIDERS = {
    "shelf_cv",
    "iot_shelf",
    "wms",
    "scanner",
    "picker_app",
    "cold_chain_sensor",
    "manual_verified",
}
ACTION_PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
RESOLVABLE_BY_LATER_SCAN = {"sku_misplaced", "facing_mismatch"}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _event_key(event: dict[str, Any]) -> tuple[str, str]:
    provider = _text(event.get("provider")).lower()
    provider_event_id = _text(event.get("provider_event_id") or event.get("event_id"))
    if provider_event_id:
        return provider, provider_event_id
    digest = hashlib.sha256(
        json.dumps(
            event,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return provider, digest


def _action_signature(alert: dict[str, Any]) -> str:
    location = alert.get("location") or {}
    material = {
        "alert_code": _text(alert.get("alert_code")),
        "sku": _text(alert.get("sku")).upper(),
        "flow_id": _text(alert.get("flow_id")),
        "aisle_id": _text(location.get("aisle_id") or alert.get("aisle_id")),
        "module_id": _text(location.get("module_id") or alert.get("module_id")),
        "shelf_no": _text(location.get("shelf_no") or alert.get("shelf_no")),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _action_for_alert(alert: dict[str, Any]) -> dict[str, Any] | None:
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
    signature = _action_signature(alert)
    return {
        "action_id": f"realogram-{signature[:16]}",
        "action_signature": signature,
        "priority": priority,
        "action": action,
        "alert_code": code,
        "sku": sku or None,
        "flow_id": _text(alert.get("flow_id")) or None,
        "last_observed_at": _text(alert.get("observed_at")) or None,
        "status": "open",
        "auto_execute_allowed": False,
    }


def _latest_sku_state(base: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get("sku")).upper(): row
        for row in base.get("sku_summaries") or []
        if _text(row.get("sku"))
    }


def _resolve_action_state(
    action: dict[str, Any],
    *,
    latest_by_sku: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    row = dict(action)
    sku = _text(row.get("sku")).upper()
    summary = latest_by_sku.get(sku) or {}
    code = row.get("alert_code")

    if code == "confirmed_oos" and int(summary.get("open_oos_count") or 0) == 0:
        row["status"] = "resolved"
        row["resolution"] = "replenishment_observed_after_oos"
        return row, True

    if code in RESOLVABLE_BY_LATER_SCAN:
        latest_scan = summary.get("latest_scan") or {}
        scan_time = _text(latest_scan.get("observed_at"))
        alert_time = _text(row.get("last_observed_at"))
        if scan_time and alert_time and scan_time > alert_time:
            row["status"] = "resolved"
            row["resolution"] = "later_usable_shelf_scan_observed"
            return row, True

    return row, False


def _action_state(
    base: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return open and resolved actions after stable-key deduplication."""
    dedup: dict[str, dict[str, Any]] = {}
    raw_count = 0
    for alert in base.get("alerts") or []:
        action = _action_for_alert(alert)
        if action is None:
            continue
        raw_count += 1
        key = action["action_signature"]
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = action
            continue
        current_time = _text(action.get("last_observed_at"))
        existing_time = _text(existing.get("last_observed_at"))
        if current_time >= existing_time:
            dedup[key] = action

    latest_by_sku = _latest_sku_state(base)
    open_actions: list[dict[str, Any]] = []
    resolved_actions: list[dict[str, Any]] = []
    for action in dedup.values():
        resolved, is_resolved = _resolve_action_state(
            action,
            latest_by_sku=latest_by_sku,
        )
        if is_resolved:
            resolved_actions.append(resolved)
        else:
            open_actions.append(resolved)

    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        return (
            ACTION_PRIORITY.get(str(row.get("priority")), 99),
            str(row.get("action_id")),
        )

    open_actions.sort(key=sort_key)
    resolved_actions.sort(key=sort_key)
    return open_actions, resolved_actions, raw_count - len(dedup)


def evaluate_temporal_realogram_v2(
    *,
    plan_payload: dict[str, Any],
    events: list[dict[str, Any]],
    as_of: str | None = None,
    stale_after_minutes: int = 240,
    trusted_connector_provenance: bool = False,
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
    open_actions, resolved_actions, action_dedup_count = _action_state(base)

    connector_verified = bool(trusted_connector_provenance)
    field_truth = bool(
        base.get("available")
        and provenance_complete
        and not invalid
        and connector_verified
    )
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
        "server_connector_provenance_verified": connector_verified,
        "action_state_contract": "stable-id-dedup-open-resolved-v1",
        "action_dedup_count": action_dedup_count,
        "open_action_count": len(open_actions),
        "resolved_action_count": len(resolved_actions),
        "action_count": len(open_actions),
        "action_queue": open_actions[:10_000],
        "resolved_actions": resolved_actions[:10_000],
        "field_truth": field_truth,
        "production_evidence": False,
        "auto_execute_allowed": False,
        "auto_correct_allowed": False,
        "evidence_boundary": (
            "provider labels and source references remain request supplied unless the "
            "caller is a server-bound trusted connector; action lifecycle is auditable "
            "but execution and production evidence still require field acceptance"
        ),
    }
