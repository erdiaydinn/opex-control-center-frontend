"""Fail-closed Store Scan normalization for camera/LiDAR/AR depth capture.

Native clients may use Apple RoomPlan, ARCore Depth, CAD import or another
measured capture path. Core does not trust raw scans as Store DNA authority.
This module converts only high-confidence, currently representable geometry
into a preview architecture draft and reports every gap that still requires
human review or a richer geometry contract.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

STORE_SCAN_CONTRACT_VERSION = "planogram-store-scan-v1"
SUPPORTED_PROVIDERS = {
    "apple_roomplan",
    "arcore_depth",
    "cad_import",
    "manual_survey",
}
PROMOTABLE_TYPES = {"wall", "column", "door", "chiller", "freezer"}
STRUCTURAL_TYPES = {"wall", "column", "door", "opening"}
ORTHOGONAL_ROTATIONS = (0.0, 90.0, 180.0, 270.0, 360.0)
ORTHOGONAL_TOLERANCE_DEG = 2.0
MIN_STRUCTURAL_CONFIDENCE = 0.75
MIN_EQUIPMENT_CONFIDENCE = 0.65


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _nearest_orthogonal(value: float) -> tuple[int, float]:
    normalized = value % 360.0
    candidates = (0.0, 90.0, 180.0, 270.0)
    selected = min(candidates, key=lambda candidate: min(abs(normalized - candidate), 360.0 - abs(normalized - candidate)))
    distance = min(abs(normalized - selected), 360.0 - abs(normalized - selected))
    return int(selected), distance


def normalize_store_scan(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "").strip().lower()
    source_ref = str(payload.get("source_ref") or "").strip()
    floor_width_m = _number(payload.get("floor_width_m"))
    floor_depth_m = _number(payload.get("floor_depth_m"))
    scan_elements = payload.get("elements") or []

    blockers: list[str] = []
    warnings: list[str] = []
    if provider not in SUPPORTED_PROVIDERS:
        blockers.append("scan_provider_unsupported")
    if not source_ref:
        blockers.append("scan_source_ref_missing")
    if floor_width_m is None or floor_width_m <= 0 or floor_depth_m is None or floor_depth_m <= 0:
        blockers.append("scan_floorplate_invalid")
    if not isinstance(scan_elements, list) or not scan_elements:
        blockers.append("scan_elements_missing")
        scan_elements = []

    promoted: list[dict[str, Any]] = []
    recognized_fixtures: list[dict[str, Any]] = []
    low_confidence_count = 0
    unsupported_rotation_count = 0
    unsupported_type_count = 0

    for index, raw in enumerate(scan_elements):
        if not isinstance(raw, dict):
            warnings.append(f"scan_element_invalid:index:{index}")
            continue
        element_id = str(raw.get("element_id") or f"scan-{index + 1}").strip()
        element_type = str(raw.get("element_type") or "unknown").strip().lower()
        confidence = _number(raw.get("confidence"))
        confidence = confidence if confidence is not None else 0.0
        x_m = _number(raw.get("x_m"))
        y_m = _number(raw.get("y_m"))
        width_m = _number(raw.get("width_m"))
        depth_m = _number(raw.get("depth_m"))
        rotation = _number(raw.get("rotation_deg"))
        rotation = rotation if rotation is not None else 0.0

        if None in (x_m, y_m, width_m, depth_m) or width_m <= 0 or depth_m <= 0:
            warnings.append(f"scan_element_geometry_invalid:{element_id}")
            continue

        threshold = (
            MIN_STRUCTURAL_CONFIDENCE
            if element_type in STRUCTURAL_TYPES
            else MIN_EQUIPMENT_CONFIDENCE
        )
        if confidence < threshold:
            low_confidence_count += 1
            warnings.append(f"scan_element_low_confidence:{element_id}")
            continue

        if element_type == "fixture":
            recognized_fixtures.append(
                {
                    "element_id": element_id,
                    "x_m": x_m,
                    "y_m": y_m,
                    "width_m": width_m,
                    "depth_m": depth_m,
                    "rotation_deg": rotation,
                    "confidence": confidence,
                    "label": raw.get("label"),
                }
            )
            continue

        if element_type == "opening":
            # Openings are retained as scan evidence but are not silently turned
            # into doors; operational semantics require human confirmation.
            unsupported_type_count += 1
            warnings.append(f"scan_opening_requires_classification:{element_id}")
            continue

        if element_type not in PROMOTABLE_TYPES:
            unsupported_type_count += 1
            warnings.append(f"scan_element_type_not_promotable:{element_id}:{element_type}")
            continue

        orthogonal, angular_error = _nearest_orthogonal(rotation)
        if angular_error > ORTHOGONAL_TOLERANCE_DEG:
            unsupported_rotation_count += 1
            warnings.append(
                f"scan_non_orthogonal_geometry_requires_architecture_v2:{element_id}"
            )
            continue

        promoted.append(
            {
                "element_id": element_id,
                "element_type": element_type,
                "x_m": x_m,
                "y_m": y_m,
                "width_m": width_m,
                "depth_m": depth_m,
                "rotation_deg": orthogonal,
                "clearance_m": 0.0,
                "label": raw.get("label"),
                "scan_confidence": confidence,
            }
        )

    if not any(item["element_type"] == "wall" for item in promoted):
        blockers.append("scan_wall_geometry_missing")
    if unsupported_rotation_count:
        blockers.append("scan_contains_non_orthogonal_geometry")

    # Store Scan cannot infer operational authority. These anchors are explicit
    # human/operational annotations before a draft may enter maker/checker flow.
    blockers.extend(
        [
            "picker_entry_annotation_required",
            "operational_zone_annotation_required",
            "human_scan_review_required",
        ]
    )

    architecture_preview = None
    if floor_width_m and floor_depth_m and promoted:
        architecture_preview = {
            "schema_version": 1,
            "coordinate_system": "cartesian_m",
            "source": "lidar_scan" if provider in {"apple_roomplan", "arcore_depth"} else (
                "cad_import" if provider == "cad_import" else "manual_survey"
            ),
            "source_ref": source_ref,
            "floor_width_m": floor_width_m,
            "floor_depth_m": floor_depth_m,
            "elements": promoted,
        }

    return {
        "contract": STORE_SCAN_CONTRACT_VERSION,
        "provider": provider or None,
        "preview_only": True,
        "raw_media_persisted": False,
        "production_evidence": False,
        "architecture_preview": architecture_preview,
        "recognized_fixture_count": len(recognized_fixtures),
        "recognized_fixtures": recognized_fixtures,
        "scan_element_count": len(scan_elements),
        "promoted_element_count": len(promoted),
        "low_confidence_count": low_confidence_count,
        "unsupported_rotation_count": unsupported_rotation_count,
        "unsupported_type_count": unsupported_type_count,
        "promotable_to_store_dna": False,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": warnings[:200],
        "next_required_action": "human_review_and_operational_annotation",
    }
