from __future__ import annotations

from architecture_truth_v2 import (
    ARCHITECTURE_V2_CONTRACT_VERSION,
    ROUTE_V2_OBJECTIVE_VERSION,
    architecture_truth_report_v2,
    layout_architecture_report_v2,
    route_between_points_v2,
)


def store_dna_v2() -> dict:
    return {
        "architecture": {
            "schema_version": 2,
            "coordinate_system": "cartesian_m_centered_rect",
            "source": "lidar_scan",
            "source_ref": "scan-session:angle-fixture-001",
            "floor_width_m": 12,
            "floor_depth_m": 8,
            "elements": [
                {
                    "element_id": "ENTRY",
                    "element_type": "picker_entry",
                    "center_x_m": 1,
                    "center_y_m": 1,
                    "width_m": 0.5,
                    "depth_m": 0.5,
                    "rotation_deg": 12,
                },
                {
                    "element_id": "ANGLED-WALL",
                    "element_type": "wall",
                    "center_x_m": 5,
                    "center_y_m": 4,
                    "width_m": 0.2,
                    "depth_m": 5,
                    "rotation_deg": 17,
                },
                {
                    "element_id": "EXIT",
                    "element_type": "emergency_exit",
                    "center_x_m": 11,
                    "center_y_m": 7,
                    "width_m": 0.8,
                    "depth_m": 0.2,
                    "rotation_deg": 33,
                    "clearance_m": 1.0,
                },
            ],
        }
    }


def test_v2_preserves_non_orthogonal_measured_geometry() -> None:
    report = architecture_truth_report_v2(store_dna_v2())

    assert report["contract"] == ARCHITECTURE_V2_CONTRACT_VERSION
    assert report["valid"] is True
    assert report["authoritative"] is False
    assert report["preview_only"] is True
    assert report["non_orthogonal_element_count"] == 3
    assert report["blockers"] == []


def test_v2_detects_collision_against_true_rotated_polygon() -> None:
    layout = {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": "COLLIDE",
                        "center_x_m": 5,
                        "center_y_m": 4,
                        "width_m": 1,
                        "depth_m": 0.6,
                        "rotation_deg": 17,
                    },
                    {
                        "module_id": "SAFE",
                        "center_x_m": 9,
                        "center_y_m": 1.5,
                        "width_m": 1,
                        "depth_m": 0.6,
                        "rotation_deg": 23,
                    },
                ],
            }
        ]
    }

    report = layout_architecture_report_v2(layout, store_dna_v2())

    assert report["contract"] == ARCHITECTURE_V2_CONTRACT_VERSION
    assert report["valid"] is False
    assert report["coordinate_coverage_pct"] == 100
    assert report["non_orthogonal_module_count"] == 2
    collisions = [
        row for row in report["violations"]
        if row["type"] == "module_architecture_collision"
    ]
    assert collisions == [
        {
            "type": "module_architecture_collision",
            "module_id": "A::COLLIDE",
            "element_id": "ANGLED-WALL",
            "element_type": "wall",
        }
    ]


def test_v2_route_detours_around_rotated_wall() -> None:
    result = route_between_points_v2(
        store_dna_v2(),
        target_x_m=9,
        target_y_m=7,
        resolution_m=0.25,
    )

    assert result["contract"] == ROUTE_V2_OBJECTIVE_VERSION
    assert result["available"] is True
    assert result["preview_only"] is True
    assert result["distance_m"] > result["straight_line_m"]
    assert result["detour_m"] > 0
    assert len(result["path_m"]) > 2


def test_v2_remains_fail_closed_for_outside_rotated_geometry() -> None:
    store = store_dna_v2()
    store["architecture"]["elements"].append(
        {
            "element_id": "OUTSIDE",
            "element_type": "column",
            "center_x_m": 11.9,
            "center_y_m": 7.9,
            "width_m": 1,
            "depth_m": 1,
            "rotation_deg": 45,
        }
    )

    report = architecture_truth_report_v2(store)

    assert report["valid"] is False
    assert "architecture_element_outside_floorplate:OUTSIDE" in report["blockers"]



def test_v2_module_dimension_contract_prefers_module_centimeters() -> None:
    layout = {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": "MODULE-CM",
                        "center_x_m": 5,
                        "center_y_m": 4,
                        "module_width_cm": 150,
                        "module_depth_cm": 65,
                        "width_cm": 20,
                        "depth_cm": 20,
                        "rotation_deg": 17,
                        "shelves": [
                            {
                                "shelf_width_cm": 100,
                                "shelf_depth_cm": 50,
                            }
                        ],
                    }
                ],
            }
        ]
    }

    report = layout_architecture_report_v2(layout, store_dna_v2())

    collisions = [
        row
        for row in report["violations"]
        if row["type"] == "module_architecture_collision"
    ]
    assert collisions == [
        {
            "type": "module_architecture_collision",
            "module_id": "A::MODULE-CM",
            "element_id": "ANGLED-WALL",
            "element_type": "wall",
        }
    ]
