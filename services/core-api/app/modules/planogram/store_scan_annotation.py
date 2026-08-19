"""Human-reviewed Store Scan annotation preview.

The capture is recomputed from measured input and bound to its scan fingerprint.
Human annotations may classify openings and add operational anchors/zones, but the
result remains a preview-only Architecture V2 draft. It never becomes approved
Store DNA or installation authority in this module.
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


def build_reviewed_store_scan_draft(
    *,
    scan_payload: dict[str, Any],
    expected_scan_fingerprint: str,
    classifications: list[dict[str, Any]],
    operational_elements: list[dict[str, Any]],
    review_note: str | None = None,
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
        return _unavailable(
            "architecture_v2_preview_unavailable",
            scan_fingerprint=scan_fingerprint,
        )
    reviewed = deepcopy(architecture)
    elements = [deepcopy(row) for row in reviewed.get("elements") or [] if isinstance(row, dict)]
    by_id = {str(row.get("element_id") or ""): row for row in elements}
    blockers: list[str] = []

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

    existing_ids = set(by_id)
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

    reviewed["elements"] = elements
    reviewed_store_dna = {
        "architecture": reviewed,
        "review": {
            "contract": ANNOTATION_CONTRACT_VERSION,
            "scan_fingerprint": scan_fingerprint,
            "review_note": review_note,
            "human_reviewed": True,
        },
    }

    validator = getattr(_load_architecture_v2(), "architecture_truth_report_v2", None)
    if not callable(validator):
        raise PlanogramEngineUnavailable("Planogram Architecture V2 validator entrypoint is unavailable")
    report = validator(reviewed_store_dna)
    if not isinstance(report, dict):
        raise PlanogramEngineUnavailable("Planogram Architecture V2 validator returned invalid data")
    blockers.extend(str(row) for row in report.get("blockers") or [])
    blockers = list(dict.fromkeys(blockers))
    reviewed_fingerprint = _fingerprint(reviewed_store_dna)

    return {
        "contract": ANNOTATION_CONTRACT_VERSION,
        "available": True,
        "reviewed_draft_ready": not blockers and report.get("valid") is True,
        "scan_fingerprint": scan_fingerprint,
        "reviewed_draft_fingerprint": reviewed_fingerprint,
        "reviewed_store_dna_v2_preview": reviewed_store_dna,
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
            "human review is bound to the recomputed Store Scan fingerprint; the reviewed "
            "Architecture V2 draft still requires governed Store DNA persistence, maker-checker "
            "approval and real-device/field evidence before production use"
        ),
    }
