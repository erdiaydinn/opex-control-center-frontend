from __future__ import annotations

from architecture_truth import (
    MAX_ROUTE_HOTSPOTS,
    ROUTE_OBJECTIVE_VERSION,
    architecture_route_objective,
    architecture_truth_report,
    layout_architecture_report,
)


def architecture(*, with_wall: bool = False) -> dict[str, object]:
    elements: list[dict[str, object]] = [
        {
            "element_id": "ENTRY-1",
            "element_type": "picker_entry",
            "x_m": 0.25,
            "y_m": 0.25,
            "width_m": 0.5,
            "depth_m": 0.5,
            "rotation_deg": 0,
        },
        {
            "element_id": "EXIT-1",
            "element_type": "emergency_exit",
            "x_m": 8.5,
            "y_m": 6.5,
            "width_m": 1.0,
            "depth_m": 0.5,
            "rotation_deg": 0,
            "clearance_m": 1.0,
        },
    ]
    if with_wall:
        elements.append(
            {
                "element_id": "WALL-1",
                "element_type": "wall",
                "x_m": 2.0,
                "y_m": 0.0,
                "width_m": 0.5,
                "depth_m": 3.0,
                "rotation_deg": 0,
            }
        )
    return {
        "source": "user_approved_store_dna",
        "architecture": {
            "schema_version": 1,
            "coordinate_system": "cartesian_m",
            "source": "manual_survey",
            "source_ref": "survey://TEST/2026-08-17",
            "floor_width_m": 10.0,
            "floor_depth_m": 8.0,
            "elements": elements,
        },
    }


def layout(*, x_m: float = 4.0, y_m: float = 1.0) -> dict[str, object]:
    return {
        "aisles": [
            {
                "aisle_id": "A01",
                "modules": [
                    {
                        "module_id": "A01-L01",
                        "side": "L",
                        "x_m": x_m,
                        "y_m": y_m,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "rotation_deg": 0,
                        "shelves": [
                            {
                                "shelf_width_cm": 100,
                                "shelf_depth_cm": 50,
                                "products": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def result() -> dict[str, object]:
    return {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A01",
                    "modules": [
                        {
                            "module_id": "A01-L01",
                            "shelves": [
                                {
                                    "shelf_no": 1,
                                    "products": [
                                        {
                                            "sku": "FAST-SKU",
                                            "sales_qty_7d": 10,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    }


def duplicate_layout() -> dict[str, object]:
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "x_m": 2.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "shelves": [{"shelf_width_cm": 100, "shelf_depth_cm": 50}],
                    }
                ],
            },
            {
                "aisle_id": "B",
                "modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "x_m": 6.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "shelves": [{"shelf_width_cm": 100, "shelf_depth_cm": 50}],
                    }
                ],
            },
        ]
    }


def duplicate_result() -> dict[str, object]:
    return {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [{"products": [{"sku": "A-SKU"}]}],
                        }
                    ],
                },
                {
                    "aisle_id": "B",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [{"products": [{"sku": "B-SKU"}]}],
                        }
                    ],
                },
            ]
        }
    }


def test_measured_architecture_is_authoritative() -> None:
    report = architecture_truth_report(architecture())
    assert report["present"] is True
    assert report["valid"] is True
    assert report["authoritative"] is True
    assert report["picker_entry_count"] == 1
    assert len(report["fingerprint"]) == 64


def test_declared_architecture_fails_closed_without_measured_source() -> None:
    dna = architecture()
    dna["architecture"]["source"] = "synthetic"
    report = architecture_truth_report(dna)
    assert report["valid"] is False
    assert "architecture_source_not_measured" in report["blockers"]


def test_module_cannot_occupy_emergency_exit_clearance() -> None:
    report = layout_architecture_report(
        layout(x_m=8.0, y_m=6.0),
        architecture(),
    )
    assert report["valid"] is False
    assert "layout_architecture_hard_violation" in report["blockers"]
    assert any(
        row["element_type"] == "emergency_exit" for row in report["violations"]
    )


def test_route_objective_uses_obstacle_aware_metres_and_explains_hotspots() -> None:
    products = [{"sku": "FAST-SKU", "sales_qty_7d": 10}]
    routed = architecture_route_objective(
        result(),
        products,
        layout(),
        architecture(with_wall=True),
        resolution_m=0.5,
    )
    direct = architecture_route_objective(
        result(),
        products,
        layout(),
        architecture(with_wall=False),
        resolution_m=0.5,
    )

    assert routed["available"] is True
    assert routed["basis"] == ROUTE_OBJECTIVE_VERSION
    assert routed["metric"] == "sales_weighted_single_origin_walk_m"
    assert routed["value"] > direct["value"]
    assert routed["architecture_fingerprint"] != direct["architecture_fingerprint"]
    assert routed["picker_entry_m"] == [0.5, 0.5]
    assert routed["module_distance_count"] == 1
    assert routed["module_distances_m"]["A01::A01-L01"] > 0
    assert routed["route_hotspot_limit"] == MAX_ROUTE_HOTSPOTS
    assert len(routed["route_hotspots"]) == 1
    hotspot = routed["route_hotspots"][0]
    assert hotspot["module_id"] == "A01::A01-L01"
    assert hotspot["sales_weight"] == 10
    assert hotspot["weighted_cost"] == routed["value"]
    assert hotspot["path_m"][0] == [0.5, 0.5]
    assert len(hotspot["path_m"]) >= 2


def test_route_primitive_scopes_duplicate_module_ids_by_aisle() -> None:
    routed = architecture_route_objective(
        duplicate_result(),
        [
            {"sku": "A-SKU", "sales_qty_7d": 10},
            {"sku": "B-SKU", "sales_qty_7d": 20},
        ],
        duplicate_layout(),
        architecture(),
        resolution_m=0.5,
    )

    assert routed["available"] is True
    assert routed["module_distance_count"] == 2
    assert set(routed["module_distances_m"]) == {"A::1", "B::1"}
    assert routed["module_distances_m"]["B::1"] > routed["module_distances_m"]["A::1"]
    assert routed["route_hotspots"][0]["module_id"] == "B::1"
    assert len(routed["route_hotspots"]) <= MAX_ROUTE_HOTSPOTS
