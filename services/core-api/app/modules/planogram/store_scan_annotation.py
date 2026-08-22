"""Human-reviewed Store Scan annotation preview.

The capture is recomputed from measured input and bound to its scan fingerprint.
Human annotations may classify openings, resolve uncertain measured regions and
add operational anchors/zones, but the result remains a preview-only Architecture
V2 draft. It never becomes approved Store DNA or installation authority here.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from types import ModuleType
from typing import Any

from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    _load_modules,
    _module_from_root,
)
from app.modules.planogram.store_scan import normalize_store_scan

ANNOTATION_CONTRACT_VERSION = "planogram-store-scan-human-review-v1"
REQUIRED_OPERATIONAL_TYPES = {"picker_entry", "inbound", "dispatch"}
CONFIRMABLE_TYPES = {"wall", "column", "door", "opening", "chiller", "freezer", "fixture"}
ARCHITECTURE_TYPES = {"wall", "column", "door", "opening", "chiller", "freezer"}
EQUIPMENT_TYPES = {"fixture", "chiller", "freezer"}


@lru_cache(maxsize=1)
def _load_architecture_v2() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "architecture_truth_v2.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Planogram Architecture V2 validator is unavailable")
    return _module_from_root("architecture_truth_v2", root)


def _fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _unavailable(reason: str, *, scan_fingerprint: str | None = None) -> dict[str, Any]:
    return {
        "contract": ANNOTATION_CONTRACT_VERSION,
        "available": False,
        "reviewed_draft_ready": False,
        "reason": reason,
        "scan_fingerprint": scan_fingerprint,
        "preview_only": True,
        "store_dna_authority": False,
        "production_authority": False,
        "installation_approval_allowed": False,
        "auto_store_dna_promotion_allowed": False,
    }


def _architecture_source(scan_payload: dict[str, Any]) -> str:
    provider = str(scan_payload.get("provider") or "").strip().lower()
    if provider in {"apple_roomplan", "arcore_depth"}:
        return "lidar_scan"
    if provider == "cad_import":
        return "cad_import"
    return "manual_survey"


def _empty_architecture(scan_payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        floor_width_m = float(scan_payload.get("floor_width_m"))
        floor_depth_m = float(scan_payload.get("floor_depth_m"))
    except (TypeError, ValueError):
        return None
    if floor_width_m <= 0 or floor_depth_m <= 0:
        return None
    return {
        "schema_version": 2,
        "coordinate_system": "cartesian_m_centered_rect",
        "source": _architecture_source(scan_payload),
        "source_ref": str(scan_payload.get("source_ref") or ""),
        "floor_width_m": floor_width_m,
        "floor_depth_m": floor_depth_m,
        "elements": [],
    }


def _equipment_storage_hint(element_type: str) -> str | None:
    if element_type == "chiller":
        return "CHILLED"
    if element_type == "freezer":
        return "FROZEN"
    return None


def _resolved_architecture_element(
    region: dict[str, Any],
    element_type: str,
    clearance_m: float,
) -> dict[str, Any]:
    return {
        "element_id": str(region.get("element_id") or ""),
        "element_type": element_type,
        "center_x_m": float(region.get("center_x_m") or 0.0),
        "center_y_m": float(region.get("center_y_m") or 0.0),
        "width_m": float(region.get("width_m") or 0.0),
        "depth_m": float(region.get("depth_m") or 0.0),
        "rotation_deg": float(region.get("rotation_deg") or 0.0),
        "clearance_m": float(clearance_m or 0.0),
        "label": region.get("label"),
        "scan_confidence": float(region.get("confidence") or 0.0),
        "uncertainty_confirmed": True,
        "human_classified": element_type != str(region.get("source_element_type") or ""),
    }


def _resolved_fixture(region: dict[str, Any], element_type: str) -> dict[str, Any]:
    return {
        "element_id": str(region.get("element_id") or ""),
        "center_x_m": float(region.get("center_x_m") or 0.0),
        "center_y_m": float(region.get("center_y_m") or 0.0),
        "width_m": float(region.get("width_m") or 0.0),
        "depth_m": float(region.get("depth_m") or 0.0),
        "rotation_deg": float(region.get("rotation_deg") or 0.0),
        "confidence": float(region.get("confidence") or 0.0),
        "label": region.get("label"),
        "source_element_type": element_type,
        "hinted_storage_type": _equipment_storage_hint(element_type),
        "human_uncertainty_confirmed": True,
    }


def build_reviewed_store_scan_draft(
    *,
    scan_payload: dict[str, Any],
    expected_scan_fingerprint: str,
    classifications: list[dict[str, Any]],
    operational_elements: list[dict[str, Any]],
    review_note: str | None = None,
    uncertainty_resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recompute the scan, verify its fingerprint, then apply bounded human review."""
    normalized = normalize_store_scan(deepcopy(scan_payload))
    scan_fingerprint = str(normalized.get("scan_fingerprint") or "").lower()
    expected = str(expected_scan_fingerprint or "").strip().lower()
    if not scan_fingerprint or scan_fingerprint != expected:
        return _unavailable(
            "scan_fingerprint_mismatch",
            scan_fingerprint=scan_fingerprint or None,
        )

    architecture = normalized.get("architecture_v2_preview")
    if not isinstance(architecture, dict):
        architecture = _empty_architecture(scan_payload)
    if not isinstance(architecture, dict):
        return _unavailable(
            "architecture_v2_preview_unavailable",
            scan_fingerprint=scan_fingerprint,
        )

    reviewed = deepcopy(architecture)
    elements = [deepcopy(row) for row in reviewed.get("elements") or [] if isinstance(row, dict)]
    by_id = {str(row.get("element_id") or ""): row for row in elements}
    recognized_fixtures = [
        deepcopy(row)
        for row in normalized.get("recognized_fixtures") or []
        if isinstance(row, dict)
    ]
    fixture_ids = {str(row.get("element_id") or "") for row in recognized_fixtures}
    blockers: list[str] = []

    uncertain_regions = [
        row for row in normalized.get("uncertain_regions") or [] if isinstance(row, dict)
    ]
    uncertain_by_id = {str(row.get("element_id") or ""): row for row in uncertain_regions}
    raw_resolutions = [row for row in (uncertainty_resolutions or []) if isinstance(row, dict)]
    resolution_ids = [str(row.get("element_id") or "") for row in raw_resolutions]
    if len(resolution_ids) != len(set(resolution_ids)):
        blockers.append("scan_uncertainty_resolution_duplicate_target")
    resolutions_by_id = {
        str(row.get("element_id") or ""): row
        for row in raw_resolutions
    }
    for element_id in resolutions_by_id:
        if element_id not in uncertain_by_id:
            blockers.append(f"scan_uncertainty_target_invalid:{element_id}")

    confirmed_count = 0
    rejected_count = 0
    decision_records: list[dict[str, Any]] = []
    for region in uncertain_regions:
        element_id = str(region.get("element_id") or "")
        resolution = resolutions_by_id.get(element_id)
        if resolution is None:
            blockers.append(f"scan_uncertainty_unresolved:{element_id}")
            continue
        decision = str(resolution.get("decision") or "").strip().lower()
        if decision == "reject":
            rejected_count += 1
            decision_records.append({"element_id": element_id, "decision": "reject"})
            continue
        if decision != "confirm":
            blockers.append(f"scan_uncertainty_decision_invalid:{element_id}")
            continue

        source_type = str(region.get("source_element_type") or "unknown").strip().lower()
        classified_type = str(resolution.get("classified_type") or "").strip().lower()
        if source_type == "unknown" and not classified_type:
            blockers.append(f"scan_uncertainty_type_required:{element_id}")
            continue
        resolved_type = classified_type or source_type
        if resolved_type not in CONFIRMABLE_TYPES:
            blockers.append(f"scan_uncertainty_type_invalid:{element_id}:{resolved_type}")
            continue
        if element_id in by_id or element_id in fixture_ids:
            blockers.append(f"scan_uncertainty_duplicate_element_id:{element_id}")
            continue

        clearance_m = float(resolution.get("clearance_m") or 0.0)
        if resolved_type in ARCHITECTURE_TYPES:
            architecture_row = _resolved_architecture_element(
                region,
                resolved_type,
                clearance_m,
            )
            elements.append(architecture_row)
            by_id[element_id] = architecture_row
        if resolved_type in EQUIPMENT_TYPES:
            fixture_row = _resolved_fixture(region, resolved_type)
            recognized_fixtures.append(fixture_row)
            fixture_ids.add(element_id)

        confirmed_count += 1
        decision_records.append(
            {
                "element_id": element_id,
                "decision": "confirm",
                "resolved_type": resolved_type,
                "clearance_m": clearance_m,
            }
        )

    classifications_by_id = {
        str(row.get("element_id") or ""): row
        for row in classifications
        if isinstance(row, dict)
    }
    for element_id, classification in classifications_by_id.items():
        target = by_id.get(element_id)
        if target is None or target.get("element_type") != "opening":
            blockers.append(f"scan_classification_target_invalid:{element_id}")
            continue
        target["element_type"] = classification.get("classified_type")
        target["clearance_m"] = float(classification.get("clearance_m") or 0.0)
        target["human_classified"] = True

    for row in elements:
        if row.get("element_type") == "opening":
            blockers.append(f"scan_opening_unclassified:{row.get('element_id')}")

    existing_ids = {str(row.get("element_id") or "") for row in elements}
    for raw in operational_elements:
        if not isinstance(raw, dict):
            continue
        element_id = str(raw.get("element_id") or "")
        if element_id in existing_ids:
            blockers.append(f"scan_annotation_duplicate_element_id:{element_id}")
            continue
        existing_ids.add(element_id)
        elements.append(
            {
                "element_id": element_id,
                "element_type": raw.get("element_type"),
                "center_x_m": raw.get("center_x_m"),
                "center_y_m": raw.get("center_y_m"),
                "width_m": raw.get("width_m"),
                "depth_m": raw.get("depth_m"),
                "rotation_deg": raw.get("rotation_deg", 0.0),
                "clearance_m": raw.get("clearance_m", 0.0),
                "label": raw.get("label"),
                "human_annotated": True,
            }
        )

    present_types = {str(row.get("element_type") or "") for row in elements}
    for required in sorted(REQUIRED_OPERATIONAL_TYPES):
        if required not in present_types:
            blockers.append(f"scan_{required}_annotation_required")

    unresolved_count = max(0, len(uncertain_regions) - confirmed_count - rejected_count)
    uncertainty_review = {
        "total": len(uncertain_regions),
        "resolved": confirmed_count + rejected_count,
        "confirmed": confirmed_count,
        "rejected": rejected_count,
        "unresolved": unresolved_count,
        "production_authority": False,
        "store_dna_authority": False,
        "decisions": sorted(decision_records, key=lambda row: str(row.get("element_id") or "")),
    }

    reviewed["elements"] = elements
    reviewed_store_dna = {
        "architecture": reviewed,
        "review": {
            "contract": ANNOTATION_CONTRACT_VERSION,
            "scan_fingerprint": scan_fingerprint,
            "review_note": review_note,
            "human_reviewed": True,
            "uncertainty_review": uncertainty_review,
        },
    }

    validator = getattr(_load_architecture_v2(), "architecture_truth_report_v2", None)
    if not callable(validator):
        raise PlanogramEngineUnavailable(
            "Planogram Architecture V2 validator entrypoint is unavailable"
        )
    report = validator(reviewed_store_dna)
    if not isinstance(report, dict):
        raise PlanogramEngineUnavailable(
            "Planogram Architecture V2 validator returned invalid data"
        )
    blockers.extend(str(row) for row in report.get("blockers") or [])
    blockers = list(dict.fromkeys(blockers))
    reviewed_fingerprint = _fingerprint(
        {
            "reviewed_store_dna": reviewed_store_dna,
            "reviewed_recognized_fixtures": sorted(
                recognized_fixtures,
                key=lambda row: str(row.get("element_id") or ""),
            ),
        }
    )

    return {
        "contract": ANNOTATION_CONTRACT_VERSION,
        "available": True,
        "reviewed_draft_ready": not blockers and report.get("valid") is True,
        "scan_fingerprint": scan_fingerprint,
        "reviewed_draft_fingerprint": reviewed_fingerprint,
        "reviewed_store_dna_v2_preview": reviewed_store_dna,
        "reviewed_recognized_fixtures": recognized_fixtures,
        "uncertainty_review": uncertainty_review,
        "architecture_truth_v2": report,
        "blockers": blockers,
        "preview_only": True,
        "human_review_recorded": True,
        "store_dna_authority": False,
        "maker_checker_approved": False,
        "production_authority": False,
        "installation_approval_allowed": False,
        "auto_store_dna_promotion_allowed": False,
        "v1_persistence_compatible": report.get("non_orthogonal_element_count") == 0,
        "evidence_boundary": (
            "human review and every uncertainty decision are bound to the recomputed Store Scan "
            "fingerprint; the reviewed Architecture V2 draft still requires governed Store DNA "
            "persistence, maker-checker approval and real-device/field evidence before production"
        ),
    }
