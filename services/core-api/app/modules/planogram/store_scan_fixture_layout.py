"""Build a physical layout preview from reviewed Store Scan fixture bindings.

Every module derives its pose from measured scan evidence and its shelf/capacity
contract from a human-confirmed, source-referenced catalog binding. Missing,
ambiguous or dimension-inconsistent bindings fail closed. Confirmed uncertainty
is included only through fingerprint-bound review. The result remains preview-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.modules.planogram.store_scan_annotation import build_reviewed_store_scan_draft

FIXTURE_LAYOUT_CONTRACT_VERSION = "planogram-scanned-fixture-layout-v1"
MAX_DIMENSION_DELTA_RATIO = 0.15
MIN_DIMENSION_DELTA_M = 0.12


def _unavailable(
    reason: str,
    *,
    scan_fingerprint: str | None = None,
) -> dict[str, Any]:
    return {
        "contract": FIXTURE_LAYOUT_CONTRACT_VERSION,
        "available": False,
        "layout_draft_ready": False,
        "reason": reason,
        "scan_fingerprint": scan_fingerprint,
        "preview_only": True,
        "physical_layout_authority": False,
        "store_dna_authority": False,
        "v4_v5_production_eligible": False,
        "relocation_execution_allowed": False,
        "installation_approval_allowed": False,
        "capex_approval_allowed": False,
    }


def _dimension_matches(scan_m: float, catalog_cm: float) -> bool:
    catalog_m = float(catalog_cm) / 100.0
    tolerance = max(MIN_DIMENSION_DELTA_M, catalog_m * MAX_DIMENSION_DELTA_RATIO)
    return abs(float(scan_m) - catalog_m) <= tolerance


def _shelves(binding: dict[str, Any]) -> list[dict[str, Any]]:
    storage = str(binding.get("storage_type") or "AMBIENT").upper()
    zones = list(binding.get("shelf_zone_types") or [])
    count = int(binding.get("shelf_count") or 0)
    return [
        {
            "shelf_no": index + 1,
            "shelf_width_cm": float(binding["shelf_width_cm"]),
            "shelf_height_cm": float(binding["shelf_height_cm"]),
            "shelf_depth_cm": float(binding["shelf_depth_cm"]),
            "max_weight_kg": float(binding["shelf_max_weight_kg"]),
            "allowed_storage_type": storage,
            "zone_type": zones[index],
            "products": [],
        }
        for index in range(count)
    ]


def build_scanned_fixture_layout_preview(
    *,
    scan_payload: dict[str, Any],
    expected_scan_fingerprint: str,
    classifications: list[dict[str, Any]],
    operational_elements: list[dict[str, Any]],
    fixture_bindings: list[dict[str, Any]],
    review_note: str | None = None,
    uncertainty_resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recompute review then bind all reviewed recognized fixtures to catalog truth."""
    reviewed = build_reviewed_store_scan_draft(
        scan_payload=deepcopy(scan_payload),
        expected_scan_fingerprint=expected_scan_fingerprint,
        classifications=deepcopy(classifications),
        operational_elements=deepcopy(operational_elements),
        review_note=review_note,
        uncertainty_resolutions=deepcopy(uncertainty_resolutions or []),
    )
    scan_fingerprint = str(reviewed.get("scan_fingerprint") or "") or None
    if not reviewed.get("available"):
        return _unavailable(
            "reviewed_scan_unavailable",
            scan_fingerprint=scan_fingerprint,
        )
    if not reviewed.get("reviewed_draft_ready"):
        result = _unavailable(
            "reviewed_scan_not_ready",
            scan_fingerprint=scan_fingerprint,
        )
        result["review_blockers"] = list(reviewed.get("blockers") or [])
        result["uncertainty_review"] = reviewed.get("uncertainty_review")
        return result

    recognized = {
        str(row.get("element_id") or ""): row
        for row in reviewed.get("reviewed_recognized_fixtures") or []
        if isinstance(row, dict)
    }
    bindings = {
        str(row.get("scan_fixture_element_id") or ""): row
        for row in fixture_bindings
        if isinstance(row, dict)
    }
    blockers: list[str] = []
    bound_modules: list[dict[str, Any]] = []

    for target in sorted(bindings):
        if target not in recognized:
            blockers.append(f"scan_fixture_binding_target_unknown:{target}")

    for element_id, fixture in sorted(recognized.items()):
        binding = bindings.get(element_id)
        if binding is None:
            blockers.append(f"scan_fixture_binding_missing:{element_id}")
            continue
        if binding.get("attested") is not True:
            blockers.append(f"scan_fixture_binding_not_attested:{element_id}")
            continue
        source_ref = str(binding.get("source_ref") or "").strip()
        if not source_ref:
            blockers.append(f"scan_fixture_binding_source_ref_missing:{element_id}")
            continue
        if not _dimension_matches(float(fixture["width_m"]), float(binding["fixture_width_cm"])):
            blockers.append(f"scan_fixture_width_mismatch:{element_id}")
        if not _dimension_matches(float(fixture["depth_m"]), float(binding["fixture_depth_cm"])):
            blockers.append(f"scan_fixture_depth_mismatch:{element_id}")

        storage = str(binding.get("storage_type") or "AMBIENT").upper()
        hinted_storage = str(fixture.get("hinted_storage_type") or "").strip().upper()
        if hinted_storage and storage != hinted_storage:
            blockers.append(
                f"scan_fixture_storage_hint_mismatch:{element_id}:{hinted_storage}:{storage}"
            )

        fixture_type = str(binding.get("fixture_type") or "").strip()
        fixture_text = fixture_type.lower()
        if storage == "CHILLED" and not any(
            token in fixture_text for token in ("chilled", "cooler", "fridge", "+4")
        ):
            blockers.append(f"scan_fixture_storage_type_mismatch:{element_id}:CHILLED")
        if storage == "FROZEN" and not any(
            token in fixture_text for token in ("frozen", "freezer", "-18")
        ):
            blockers.append(f"scan_fixture_storage_type_mismatch:{element_id}:FROZEN")
        if storage == "PALLET" and not any(
            token in fixture_text for token in ("pallet", "palet", "hdr", "heavy")
        ):
            blockers.append(f"scan_fixture_storage_type_mismatch:{element_id}:PALLET")

        bound_modules.append(
            {
                "aisle_id": str(binding["aisle_id"]),
                "module": {
                    "module_id": str(binding["fixture_id"]),
                    "side": str(binding["side"]),
                    "position": int(binding["position"]),
                    "x_m": float(fixture["center_x_m"]),
                    "y_m": float(fixture["center_y_m"]),
                    "width_m": float(fixture["width_m"]),
                    "depth_m": float(fixture["depth_m"]),
                    "rotation_deg": float(fixture.get("rotation_deg") or 0.0),
                    "fixture_type": fixture_type,
                    "storage_type": storage,
                    "relocatable": False,
                    "utility_relocation_attested": False,
                    "scan_fixture_element_id": element_id,
                    "scan_source_element_type": str(
                        fixture.get("source_element_type") or "fixture"
                    ),
                    "scan_hinted_storage_type": hinted_storage or None,
                    "scan_confidence": float(fixture.get("confidence") or 0.0),
                    "scan_uncertainty_human_confirmed": bool(
                        fixture.get("human_uncertainty_confirmed")
                    ),
                    "catalog_source_ref": source_ref,
                    "catalog_attested": True,
                    "fixture_catalog_geometry": {
                        "width_cm": float(binding["fixture_width_cm"]),
                        "height_cm": float(binding["fixture_height_cm"]),
                        "depth_cm": float(binding["fixture_depth_cm"]),
                    },
                    "shelves": _shelves(binding),
                },
            }
        )

    aisles: dict[str, list[dict[str, Any]]] = {}
    for row in bound_modules:
        aisles.setdefault(row["aisle_id"], []).append(row["module"])
    layout = {
        "source": "fingerprint_bound_scanned_fixture_review",
        "scan_fingerprint": scan_fingerprint,
        "reviewed_draft_fingerprint": reviewed.get("reviewed_draft_fingerprint"),
        "aisles": [
            {
                "aisle_id": aisle_id,
                "modules": sorted(
                    modules,
                    key=lambda row: (str(row.get("side")), int(row.get("position") or 0)),
                ),
            }
            for aisle_id, modules in sorted(aisles.items())
        ],
    }
    recognized_count = len(recognized)
    bound_count = sum(1 for element_id in recognized if element_id in bindings)
    coverage_pct = round(bound_count * 100.0 / recognized_count, 2) if recognized_count else 100.0
    blockers = list(dict.fromkeys(blockers))
    ready = not blockers and bound_count == recognized_count

    return {
        "contract": FIXTURE_LAYOUT_CONTRACT_VERSION,
        "available": True,
        "layout_draft_ready": ready,
        "scan_fingerprint": scan_fingerprint,
        "reviewed_draft_fingerprint": reviewed.get("reviewed_draft_fingerprint"),
        "recognized_fixture_count": recognized_count,
        "recognized_temperature_fixture_count": sum(
            1
            for row in recognized.values()
            if row.get("hinted_storage_type") in {"CHILLED", "FROZEN"}
        ),
        "bound_fixture_count": bound_count,
        "fixture_binding_coverage_pct": coverage_pct,
        "physical_layout_preview": layout,
        "reviewed_store_dna_v2_preview": reviewed.get("reviewed_store_dna_v2_preview"),
        "uncertainty_review": reviewed.get("uncertainty_review"),
        "blockers": blockers,
        "preview_only": True,
        "physical_layout_authority": False,
        "store_dna_authority": False,
        "v4_v5_production_eligible": False,
        "architecture_v2_optimizer_bridge_required": True,
        "relocation_execution_allowed": False,
        "installation_approval_allowed": False,
        "capex_approval_allowed": False,
        "evidence_boundary": (
            "fixture poses come from the fingerprint-bound measured scan after explicit human "
            "uncertainty resolution and shelf/capacity truth comes from human-confirmed catalog "
            "bindings; governed Store DNA approval is still required"
        ),
    }
