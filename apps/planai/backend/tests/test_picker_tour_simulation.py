from __future__ import annotations

from picker_tour_simulation import (
    MAX_EXPLAINED_ORDERS,
    MAX_ORDERS_PER_SIMULATION,
    PICKER_TOUR_SIMULATION_VERSION,
    simulate_picker_tours,
)


def store_dna(*, wall: bool = False) -> dict:
    elements = [
        {
            "element_id": "ENTRY",
            "element_type": "picker_entry",
            "x_m": 0.25,
            "y_m": 0.25,
            "width_m": 0.5,
            "depth_m": 0.5,
        },
        {
            "element_id": "EXIT",
            "element_type": "picker_exit",
            "x_m": 9.0,
            "y_m": 0.25,
            "width_m": 0.5,
            "depth_m": 0.5,
        },
    ]
    if wall:
        elements.append(
            {
                "element_id": "WALL",
                "element_type": "wall",
                "x_m": 4.0,
                "y_m": 0.0,
                "width_m": 0.5,
                "depth_m": 3.0,
            }
        )
    return {
        "architecture": {
            "schema_version": 1,
            "coordinate_system": "cartesian_m",
            "source": "manual_survey",
            "source_ref": "survey://TOUR/1",
            "floor_width_m": 10.0,
            "floor_depth_m": 6.0,
            "elements": elements,
        }
    }


def layout() -> dict:
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": 1,
                        "x_m": 2.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "side": "L",
                        "shelves": [{"shelf_width_cm": 100, "shelf_depth_cm": 50}],
                    },
                    {
                        "module_id": 2,
                        "x_m": 6.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "side": "R",
                        "shelves": [{"shelf_width_cm": 100, "shelf_depth_cm": 50}],
                    },
                ],
            },
            {
                "aisle_id": "B",
                "modules": [
                    {
                        "module_id": 1,
                        "x_m": 6.0,
                        "y_m": 4.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "side": "L",
                        "shelves": [{"shelf_width_cm": 100, "shelf_depth_cm": 50}],
                    }
                ],
            },
        ]
    }


def result() -> dict:
    return {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [{"products": [{"sku": "SKU-A"}, {"sku": "SKU-A2"}]}],
                        },
                        {
                            "module_id": 2,
                            "shelves": [{"products": [{"sku": "SKU-B"}]}],
                        },
                    ],
                },
                {
                    "aisle_id": "B",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [{"products": [{"sku": "SKU-C"}]}],
                        }
                    ],
                },
            ]
        }
    }


def orders() -> list[dict]:
    return [
        {"order_id": "O-1", "skus": ["SKU-A", "SKU-B"]},
        {"order_id": "O-2", "items": [{"sku": "SKU-A2"}, {"sku": "SKU-C"}]},
        {"order_id": "O-3", "skus": ["SKU-A", "SKU-A2"]},
    ]


def test_multi_order_simulation_is_measured_bounded_and_explainable() -> None:
    report = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        resolution_m=0.5,
    )

    assert report["simulation_version"] == PICKER_TOUR_SIMULATION_VERSION
    assert report["available"] is True
    assert report["production_evidence"] is False
    assert report["orders"]["input_count"] == 3
    assert report["orders"]["simulated_count"] == 3
    assert report["orders"]["coverage_pct"] == 100.0
    assert report["distance_m"]["total"] > 0
    assert report["distance_m"]["p50"] > 0
    assert report["distance_m"]["p95"] >= report["distance_m"]["p50"]
    assert len(report["explained_orders"]) == 3
    assert report["explainability_order_limit"] == MAX_EXPLAINED_ORDERS
    assert report["explained_orders"][0]["visit_sequence"]
    assert all(segment["path_m"] for segment in report["explained_orders"][0]["segments"])
    assert report["architecture_fingerprint"]


def test_wall_obstacle_increases_tour_distance() -> None:
    direct = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=store_dna(wall=False),
        orders=[{"order_id": "O", "skus": ["SKU-B"]}],
        resolution_m=0.5,
    )
    obstructed = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=store_dna(wall=True),
        orders=[{"order_id": "O", "skus": ["SKU-B"]}],
        resolution_m=0.5,
    )

    assert direct["available"] is True
    assert obstructed["available"] is True
    assert obstructed["distance_m"]["total"] > direct["distance_m"]["total"]


def test_duplicate_module_ids_across_aisles_remain_distinct_stops() -> None:
    report = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=[{"order_id": "O", "skus": ["SKU-A", "SKU-C"]}],
    )

    sequence = report["explained_orders"][0]["visit_sequence"]
    assert set(sequence) == {"A::1", "B::1"}


def test_missing_sku_never_gets_invented_location() -> None:
    report = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=[
            {"order_id": "GOOD", "skus": ["SKU-A"]},
            {"order_id": "MISSING", "skus": ["UNKNOWN-SKU"]},
        ],
    )

    assert report["orders"]["input_count"] == 2
    assert report["orders"]["simulated_count"] == 1
    assert report["orders"]["coverage_pct"] == 50.0
    assert report["orders"]["missing_sku_occurrence_count"] == 1
    assert report["missing_skus"] == [{"sku": "UNKNOWN-SKU", "occurrences": 1}]


def test_invalid_architecture_fails_closed() -> None:
    invalid = store_dna()
    invalid["architecture"]["source"] = "synthetic"
    report = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=invalid,
        orders=orders(),
    )

    assert report["available"] is False
    assert report["reason"] == "physical_architecture_truth_invalid"
    assert report["production_evidence"] is False


def test_no_orders_fails_closed_instead_of_generating_synthetic_baskets() -> None:
    report = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=[],
    )

    assert report["available"] is False
    assert report["reason"] == "order_baskets_missing"
    assert report["blockers"] == ["observed_or_test_order_baskets_required"]


def test_order_volume_is_bounded() -> None:
    report = simulate_picker_tours(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=[{"order_id": str(index), "skus": ["SKU-A"]} for index in range(MAX_ORDERS_PER_SIMULATION + 1)],
    )

    assert report["available"] is False
    assert report["reason"] == "order_basket_limit_exceeded"
