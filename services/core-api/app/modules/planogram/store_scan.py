"""Fail-closed Store Scan normalization for camera/LiDAR/AR depth capture.

Native clients may use Apple RoomPlan, ARCore Depth, CAD import or another
measured capture path. Core does not trust raw scans as Store DNA authority.
This module emits both the legacy orthogonal V1 preview and an oriented V2
preview so arbitrary scan angles are preserved rather than silently snapped.
Low-confidence/unknown geometry is retained as fingerprint-bound uncertainty
rather than disappearing or silently becoming physical truth.
"""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from typing import Any

STORE_SCAN_CONTRACT_VERSION = "planogram-store-scan-v1"
SUPPORTED_PROVIDERS = {
    "apple_roomplan",
    "arcore_depth",
    "cad_import",
    "manual_survey",
}
V1_PROMOTABLE_TYPES = {"wall", "column", "door", "chiller", "freezer"}
V2_GEOMETRY_TYPES = V1_PROMOTABLE_TYPES | {"opening"}
STRUCTURAL_TYPES = {"wall", "column", "door", "opening"}
PRODUCT_BEARING_EQUIPMENT_TYPES = {"fixture", "chiller", "freezer"}
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
    selected = min(
        candidates,
        key=lambda candidate: min(
            abs(normalized - candidate),
            360.0 - abs(normalized - candidate),
        ),
    )
    distance = min(abs(normalized - selected), 360.0 - abs(normalized - selected))
    return int(selected), distance


def _source(provider: str) -> str:
    if provider in {"apple_roomplan", "arcore_depth"}:
        return "lidar_scan"
    if provider == "cad_import":
        return "cad_import"
    return "manual_survey"


def _equipment_storage_hint(element_type: str) -> str | None:
    if element_type == "chiller":
        return "CHILLED"
    if element_type == "freezer":
        return "FROZEN"
    return None


def _scan_fingerprint(
    *,
    provider: str,
    source_ref: str,
    floor_width_m: float | None,
    floor_depth_m: float | None,
    v2_elements: list[dict[str, Any]],
    recognized_fixtures: list[dict[str, Any]],
    uncertain_regions: list[dict[str, Any]],
) -> str:
    """Fingerprint all normalized measured evidence without persisting raw media."""
    payload = {
        "contract": STORE_SCAN_CONTRACT_VERSION,
        "provider": provider,
        "source_ref": source_ref,
        "floor_width_m": floor_width_m,
        "floor_depth_m": floor_depth_m,
        "architecture_v2_elements": sorted(
            v2_elements,
            key=lambda row: str(row.get("element_id") or ""),
        ),
        "recognized_fixtures": sorted(
            recognized_fixtures,
            key=lambda row: str(row.get("element_id") or ""),
        ),
        "uncertain_regions": sorted(
            uncertain_regions,
            key=lambda row: str(row.get("element_id") or ""),
        ),
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


def _uncertain_region(
    *,
    element_id: str,
    element_type: str,
    x_m: float,
    y_m: float,
    width_m: float,
    depth_m: float,
    rotation: float,
    confidence: float,
    threshold: float,
    label: Any,
) -> dict[str, Any]:
    reason = (
        "unknown_type_requires_classification"
        if element_type == "unknown"
        else "below_type_confidence_threshold"
    )
    return {
        "element_id": element_id,
        "source_element_type": element_type,
        "center_x_m": x_m + width_m / 2.0,
        "center_y_m": y_m + depth_m / 2.0,
        "width_m": width_m,
        "depth_m": depth_m,
        "rotation_deg": rotation,
        "confidence": confidence,
        "required_confidence": threshold,
        "label": label,
        "reason": reason,
        "review_required": True,
        "geometry_authority": False,
        "fixture_authority": False,
        "store_dna_authority": False,
        "production_authority": False,
    }


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
    if (
        floor_width_m is None
        or floor_width_m <= 0
        or floor_depth_m is None
        or floor_depth_m <= 0
    ):
        blockers.append("scan_floorplate_invalid")
    if not isinstance(scan_elements, list) or not scan_elements:
        blockers.append("scan_elements_missing")
        scan_elements = []

    v1_elements: list[dict[str, Any]] = []
    v2_elements: list[dict[str, Any]] = []
    recognized_fixtures: list[dict[str, Any]] = []
    uncertain_regions: list[dict[str, Any]] = []
    low_confidence_count = 0
    non_orthogonal_count = 0
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

        if (
            None in (x_m, y_m, width_m, depth_m)
            or width_m <= 0
            or depth_m <= 0
        ):
            warnings.append(f"scan_element_geometry_invalid:{element_id}")
            continue

        threshold = (
            MIN_STRUCTURAL_CONFIDENCE
            if element_type in STRUCTURAL_TYPES
            else MIN_EQUIPMENT_CONFIDENCE
        )
        requires_uncertainty_review = confidence < threshold or element_type == "unknown"
        if requires_uncertainty_review:
            if confidence < threshold:
                low_confidence_count += 1
                warnings.append(f"scan_element_low_confidence:{element_id}")
            if element_type == "unknown":
                unsupported_type_count += 1
                warnings.append(f"scan_element_unknown_requires_classification:{element_id}")
            uncertain_regions.append(
                _uncertain_region(
                    element_id=element_id,
                    element_type=element_type,
                    x_m=float(x_m),
                    y_m=float(y_m),
                    width_m=float(width_m),
                    depth_m=float(depth_m),
                    rotation=rotation,
                    confidence=confidence,
                    threshold=threshold,
                    label=raw.get("label"),
                )
            )
            continue

        if element_type in PRODUCT_BEARING_EQUIPMENT_TYPES:
            recognized_fixtures.append(
                {
                    "element_id": element_id,
                    "center_x_m": x_m + width_m / 2.0,
                    "center_y_m": y_m + depth_m / 2.0,
                    "width_m": width_m,
                    "depth_m": depth_m,
                    "rotation_deg": rotation,
                    "confidence": confidence,
                    "label": raw.get("label"),
                    "source_element_type": element_type,
                    "hinted_storage_type": _equipment_storage_hint(element_type),
                }
            )
            # Generic fixtures are layout evidence only. Chiller/freezer are
            # dual-role: architecture equipment plus product-bearing binding cues.
            if element_type == "fixture":
                continue

        if element_type not in V2_GEOMETRY_TYPES:
            unsupported_type_count += 1
            warnings.append(
                f"scan_element_type_not_representable:{element_id}:{element_type}"
            )
            continue

        v2_elements.append(
            {
                "element_id": element_id,
                "element_type": element_type,
                "center_x_m": x_m + width_m / 2.0,
                "center_y_m": y_m + depth_m / 2.0,
                "width_m": width_m,
                "depth_m": depth_m,
                "rotation_deg": rotation,
                "clearance_m": 0.0,
                "label": raw.get("label"),
                "scan_confidence": confidence,
            }
        )

        if element_type == "opening":
            warnings.append(f"scan_opening_requires_classification:{element_id}")
            continue

        orthogonal, angular_error = _nearest_orthogonal(rotation)
        if angular_error > ORTHOGONAL_TOLERANCE_DEG:
            non_orthogonal_count += 1
            warnings.append(f"scan_non_orthogonal_preserved_in_v2:{element_id}")
            continue

        if element_type in V1_PROMOTABLE_TYPES:
            v1_elements.append(
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

    if not any(item["element_type"] == "wall" for item in v2_elements):
        blockers.append("scan_wall_geometry_missing")
    if non_orthogonal_count:
        blockers.append("store_dna_v1_cannot_promote_non_orthogonal_geometry")
    if uncertain_regions:
        blockers.append("scan_uncertain_regions_require_review")

    blockers.extend(
        [
            "picker_entry_annotation_required",
            "operational_zone_annotation_required",
            "human_scan_review_required",
        ]
    )

    architecture_preview = None
    architecture_v2_preview = None
    if floor_width_m and floor_depth_m and v1_elements:
        architecture_preview = {
            "schema_version": 1,
            "coordinate_system": "cartesian_m",
            "source": _source(provider),
            "source_ref": source_ref,
            "floor_width_m": floor_width_m,
            "floor_depth_m": floor_depth_m,
            "elements": v1_elements,
        }
    if floor_width_m and floor_depth_m and v2_elements:
        architecture_v2_preview = {
            "schema_version": 2,
            "coordinate_system": "cartesian_m_centered_rect",
            "source": _source(provider),
            "source_ref": source_ref,
            "floor_width_m": floor_width_m,
            "floor_depth_m": floor_depth_m,
            "elements": v2_elements,
        }

    fingerprint = _scan_fingerprint(
        provider=provider,
        source_ref=source_ref,
        floor_width_m=floor_width_m,
        floor_depth_m=floor_depth_m,
        v2_elements=v2_elements,
        recognized_fixtures=recognized_fixtures,
        uncertain_regions=uncertain_regions,
    )
    temperature_fixture_count = sum(
        1
        for row in recognized_fixtures
        if row.get("hinted_storage_type") in {"CHILLED", "FROZEN"}
    )

    return {
        "contract": STORE_SCAN_CONTRACT_VERSION,
        "provider": provider or None,
        "scan_fingerprint": fingerprint,
        "preview_only": True,
        "raw_media_persisted": False,
        "production_evidence": False,
        "architecture_preview": architecture_preview,
        "architecture_v2_preview": architecture_v2_preview,
        "architecture_v2_preview_available": architecture_v2_preview is not None,
        "recognized_fixture_count": len(recognized_fixtures),
        "recognized_temperature_fixture_count": temperature_fixture_count,
        "recognized_fixtures": recognized_fixtures,
        "uncertain_region_count": len(uncertain_regions),
        "unresolved_uncertainty_count": len(uncertain_regions),
        "uncertain_regions": uncertain_regions,
        "scan_element_count": len(scan_elements),
        "v1_promoted_element_count": len(v1_elements),
        "v2_preserved_element_count": len(v2_elements),
        "low_confidence_count": low_confidence_count,
        "unsupported_rotation_count": non_orthogonal_count,
        "unsupported_type_count": unsupported_type_count,
        "promotable_to_store_dna": False,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": warnings[:200],
        "next_required_action": "human_review_and_uncertainty_resolution",
    }
