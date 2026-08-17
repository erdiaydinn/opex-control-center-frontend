from __future__ import annotations

from architecture_truth import (
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


def test_route_objective_uses_obstacle_aware_metres() -> None:
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
