from __future__ import annotations

from app.modules.planogram.store_scan import normalize_store_scan
from app.modules.planogram.store_scan_fixture_layout import (
    build_scanned_fixture_layout_preview,
)


def scan() -> dict[str, object]:
    return {
        "store_code": "COLD-STORE",
        "provider": "apple_roomplan",
        "source_ref": "scan-session:cold-001",
        "floor_width_m": 14,
        "floor_depth_m": 10,
        "elements": [
            {
                "element_id": "wall-1",
                "element_type": "wall",
                "x_m": 0.2,
                "y_m": 4.0,
                "width_m": 2.0,
                "depth_m": 0.1,
                "rotation_deg": 0,
                "confidence": 0.99,
            },
            {
                "element_id": "chiller-1",
                "element_type": "chiller",
                "x_m": 7.0,
                "y_m": 5.0,
                "width_m": 1.2,
                "depth_m": 0.7,
                "rotation_deg": 17,
                "confidence": 0.96,
                "label": "+4 chilled cabinet",
            },
            {
                "element_id": "freezer-1",
                "element_type": "freezer",
                "x_m": 10.0,
                "y_m": 6.0,
                "width_m": 1.4,
                "depth_m": 0.8,
                "rotation_deg": -12,
                "confidence": 0.95,
                "label": "-18 freezer",
            },
        ],
    }


def operational_elements() -> list[dict[str, object]]:
    return [
        {
            "element_id": "picker-entry-1",
            "element_type": "picker_entry",
            "center_x_m": 1.0,
            "center_y_m": 1.0,
            "width_m": 0.4,
            "depth_m": 0.4,
            "rotation_deg": 0,
            "clearance_m": 0,
        },
        {
            "element_id": "inbound-1",
            "element_type": "inbound",
            "center_x_m": 2.0,
            "center_y_m": 8.0,
            "width_m": 1.5,
            "depth_m": 1.0,
            "rotation_deg": 0,
            "clearance_m": 0,
        },
        {
            "element_id": "dispatch-1",
            "element_type": "dispatch",
            "center_x_m": 12.0,
            "center_y_m": 2.0,
            "width_m": 1.5,
            "depth_m": 1.0,
            "rotation_deg": 0,
            "clearance_m": 0,
        },
    ]


def binding(
    scan_id: str,
    fixture_id: str,
    *,
    storage: str,
    fixture_type: str,
    width_cm: float,
    depth_cm: float,
    position: int,
) -> dict[str, object]:
    return {
        "scan_fixture_element_id": scan_id,
        "fixture_id": fixture_id,
        "aisle_id": "COLD",
        "side": "L",
        "position": position,
        "fixture_type": fixture_type,
        "storage_type": storage,
        "shelf_count": 3,
        "fixture_width_cm": width_cm,
        "fixture_height_cm": 190,
        "fixture_depth_cm": depth_cm,
        "shelf_width_cm": width_cm - 10,
        "shelf_height_cm": 55,
        "shelf_depth_cm": depth_cm - 10,
        "shelf_max_weight_kg": 45,
        "shelf_zone_types": ["bottom", "eye", "top"],
        "source_ref": f"fixture-master://{fixture_id}/v1",
        "attested": True,
    }


def test_chiller_and_freezer_are_dual_role_scan_evidence() -> None:
    first = normalize_store_scan(scan())
    second = normalize_store_scan(scan())
    assert first["scan_fingerprint"] == second["scan_fingerprint"]
    assert first["recognized_fixture_count"] == 2
    assert first["recognized_temperature_fixture_count"] == 2

    fixtures = {row["element_id"]: row for row in first["recognized_fixtures"]}
    assert fixtures["chiller-1"]["source_element_type"] == "chiller"
    assert fixtures["chiller-1"]["hinted_storage_type"] == "CHILLED"
    assert fixtures["freezer-1"]["source_element_type"] == "freezer"
    assert fixtures["freezer-1"]["hinted_storage_type"] == "FROZEN"

    architecture_ids = {
        row["element_id"] for row in first["architecture_v2_preview"]["elements"]
    }
    assert {"chiller-1", "freezer-1"} <= architecture_ids


def test_temperature_fixture_hints_build_chilled_and_frozen_product_capacity() -> None:
    normalized = normalize_store_scan(scan())
    result = build_scanned_fixture_layout_preview(
        scan_payload=scan(),
        expected_scan_fingerprint=normalized["scan_fingerprint"],
        classifications=[],
        operational_elements=operational_elements(),
        fixture_bindings=[
            binding(
                "chiller-1",
                "CHILLER-CAT-1",
                storage="CHILLED",
                fixture_type="chilled_cabinet",
                width_cm=120,
                depth_cm=70,
                position=1,
            ),
            binding(
                "freezer-1",
                "FREEZER-CAT-1",
                storage="FROZEN",
                fixture_type="frozen_freezer",
                width_cm=140,
                depth_cm=80,
                position=2,
            ),
        ],
    )
    assert result["available"] is True
    assert result["layout_draft_ready"] is True
    assert result["recognized_temperature_fixture_count"] == 2
    modules = result["physical_layout_preview"]["aisles"][0]["modules"]
    assert [row["storage_type"] for row in modules] == ["CHILLED", "FROZEN"]
    assert modules[0]["scan_hinted_storage_type"] == "CHILLED"
    assert modules[1]["scan_hinted_storage_type"] == "FROZEN"
    assert modules[0]["rotation_deg"] == 17
    assert modules[1]["rotation_deg"] == -12


def test_temperature_fixture_cannot_be_bound_to_wrong_storage_class() -> None:
    normalized = normalize_store_scan(scan())
    result = build_scanned_fixture_layout_preview(
        scan_payload=scan(),
        expected_scan_fingerprint=normalized["scan_fingerprint"],
        classifications=[],
        operational_elements=operational_elements(),
        fixture_bindings=[
            binding(
                "chiller-1",
                "AMBIENT-CAT-1",
                storage="AMBIENT",
                fixture_type="steel_rack",
                width_cm=120,
                depth_cm=70,
                position=1,
            ),
            binding(
                "freezer-1",
                "FREEZER-CAT-1",
                storage="FROZEN",
                fixture_type="frozen_freezer",
                width_cm=140,
                depth_cm=80,
                position=2,
            ),
        ],
    )
    assert result["layout_draft_ready"] is False
    assert (
        "scan_fixture_storage_hint_mismatch:chiller-1:CHILLED:AMBIENT"
        in result["blockers"]
    )
    assert result["physical_layout_authority"] is False
    assert result["store_dna_authority"] is False
