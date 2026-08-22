from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

FIXTURE_CATALOG_CONTRACT_VERSION = "planogram-fixture-catalog-v1"
FIXTURE_CODE_PATTERN = re.compile(r"^[A-Z0-9._:-]{2,80}$")
STORAGE_TYPES = {"AMBIENT", "CHILLED", "FROZEN", "PALLET"}
MEASURED_SOURCES = {
    "manual_survey",
    "cad_import",
    "floorplan_import",
    "lidar_scan",
    "surveyed_fixture_catalog",
}


class FixtureCatalogStateError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_fixture_code(value: str) -> str:
    code = str(value or "").strip().upper()
    if not FIXTURE_CODE_PATTERN.fullmatch(code):
        raise ValueError("fixture_code must match ^[A-Z0-9._:-]{2,80}$")
    return code


def canonical_fixture_record(payload: dict[str, Any]) -> dict[str, Any]:
    fixture_code = normalize_fixture_code(str(payload.get("fixture_code") or ""))
    fixture_name = str(payload.get("fixture_name") or "").strip()
    fixture_type = str(payload.get("fixture_type") or "").strip().upper()
    storage_type = str(payload.get("storage_type") or "").strip().upper()
    source_ref = str(payload.get("source_ref") or "").strip()
    measured_source = str(payload.get("measured_source") or "").strip()

    if not fixture_name:
        raise ValueError("fixture_name is required")
    if not fixture_type:
        raise ValueError("fixture_type is required")
    if storage_type not in STORAGE_TYPES:
        raise ValueError("storage_type is invalid")
    if measured_source not in MEASURED_SOURCES:
        raise ValueError("measured_source is invalid")
    if len(source_ref) < 3:
        raise ValueError("source_ref is required")

    shelf_count = int(payload.get("shelf_count") or 0)
    if shelf_count < 1 or shelf_count > 30:
        raise ValueError("shelf_count must be between 1 and 30")

    def positive_float(name: str, maximum: float) -> float:
        raw = payload.get(name)
        value = float(raw) if raw is not None else 0.0
        if value <= 0 or value > maximum:
            raise ValueError(f"{name} must be > 0 and <= {maximum:g}")
        return round(value, 4)

    fixture_width_cm = positive_float("fixture_width_cm", 2000)
    fixture_height_cm = positive_float("fixture_height_cm", 2000)
    fixture_depth_cm = positive_float("fixture_depth_cm", 2000)
    shelf_width_cm = positive_float("shelf_width_cm", 2000)
    shelf_height_cm = positive_float("shelf_height_cm", 1000)
    shelf_depth_cm = positive_float("shelf_depth_cm", 2000)
    shelf_max_weight_kg = positive_float("shelf_max_weight_kg", 5000)

    zone_types = [str(item).strip().lower() for item in payload.get("shelf_zone_types") or []]
    allowed_zones = {"bottom", "lower", "eye", "upper", "top"}
    if len(zone_types) != shelf_count or any(item not in allowed_zones for item in zone_types):
        raise ValueError("shelf_zone_types must contain one valid zone per shelf")
    if shelf_width_cm > fixture_width_cm * 1.05:
        raise ValueError("shelf_width_cm exceeds fixture width")
    if shelf_depth_cm > fixture_depth_cm * 1.05:
        raise ValueError("shelf_depth_cm exceeds fixture depth")
    if shelf_height_cm * shelf_count > fixture_height_cm * 1.25:
        raise ValueError("shelf vertical geometry exceeds fixture height")

    return {
        "contract_version": FIXTURE_CATALOG_CONTRACT_VERSION,
        "fixture_code": fixture_code,
        "fixture_name": fixture_name,
        "fixture_type": fixture_type,
        "storage_type": storage_type,
        "fixture_width_cm": fixture_width_cm,
        "fixture_height_cm": fixture_height_cm,
        "fixture_depth_cm": fixture_depth_cm,
        "shelf_count": shelf_count,
        "shelf_width_cm": shelf_width_cm,
        "shelf_height_cm": shelf_height_cm,
        "shelf_depth_cm": shelf_depth_cm,
        "shelf_max_weight_kg": shelf_max_weight_kg,
        "shelf_zone_types": zone_types,
        "measured_source": measured_source,
        "source_ref": source_ref,
    }


def fixture_record_fingerprint(record: dict[str, Any]) -> str:
    canonical = canonical_fixture_record(record)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def clone_fixture_record(record: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(canonical_fixture_record(record))


def approved_fixture_to_scanned_binding(
    approved: dict[str, Any],
    *,
    scan_fixture_element_id: str,
    aisle_id: str,
    side: str,
    position: int,
    expected_record_sha256: str | None = None,
) -> dict[str, Any]:
    if str(approved.get("status")) != "approved":
        raise FixtureCatalogStateError("fixture_catalog_version_not_approved")

    stored_sha = str(approved.get("record_sha256") or "")
    if expected_record_sha256 and stored_sha != expected_record_sha256:
        raise FixtureCatalogStateError("fixture_catalog_version_stale_or_changed")

    record = dict(approved.get("record") or {})
    canonical = canonical_fixture_record(record)
    computed_sha = fixture_record_fingerprint(canonical)
    if computed_sha != stored_sha:
        raise FixtureCatalogStateError("fixture_catalog_record_fingerprint_mismatch")

    return {
        "scan_fixture_element_id": scan_fixture_element_id,
        "fixture_id": f"{canonical['fixture_code']}@v{approved['version_number']}",
        "aisle_id": aisle_id,
        "side": side,
        "position": position,
        "fixture_type": canonical["fixture_type"],
        "storage_type": canonical["storage_type"],
        "shelf_count": canonical["shelf_count"],
        "fixture_width_cm": canonical["fixture_width_cm"],
        "fixture_height_cm": canonical["fixture_height_cm"],
        "fixture_depth_cm": canonical["fixture_depth_cm"],
        "shelf_width_cm": canonical["shelf_width_cm"],
        "shelf_height_cm": canonical["shelf_height_cm"],
        "shelf_depth_cm": canonical["shelf_depth_cm"],
        "shelf_max_weight_kg": canonical["shelf_max_weight_kg"],
        "shelf_zone_types": canonical["shelf_zone_types"],
        "source_ref": (
            f"server-approved-fixture-catalog:{approved['id']}:{stored_sha}:"
            f"{canonical['source_ref']}"
        ),
        "attested": True,
    }
