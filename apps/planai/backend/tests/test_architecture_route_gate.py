from __future__ import annotations

from physical_engine import generate_production_plan
from physical_optimizer_v2 import optimize_production_plan
from tests.test_physical_engine import product


def spatial_layout() -> dict[str, object]:
    return {
        "store_code": "TEST",
        "aisles": [
            {
                "aisle_id": "A",
                "row": 1,
                "position": 1,
                "modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "x_m": 2.0,
                        "y_m": 1.0,
                        "rotation_deg": 0,
                        "module_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 35,
                                "shelf_depth_cm": 50,
                                "max_weight_kg": 45,
                                "zone_type": "bottom",
                                "allowed_storage_type": "AMBIENT",
                                "products": [],
                            }
                        ],
                    }
                ],
            },
            {
                "aisle_id": "PALLET",
                "row": 2,
                "position": 1,
                "modules": [
                    {
                        # Intentional duplicate legacy module id. Spatial identity
                        # must be aisle-qualified or this overwrites A/1.
                        "module_id": 1,
                        "side": "L",
                        "x_m": 8.0,
                        "y_m": 1.0,
                        "rotation_deg": 0,
                        "module_type": "pallet",
                        "fixture_type": "pallet",
                        "storage_type": "PALLET",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 120,
                                "shelf_height_cm": 120,
                                "shelf_depth_cm": 100,
                                "max_weight_kg": 800,
                                "zone_type": "bottom",
                                "allowed_storage_type": "PALLET",
                                "products": [],
                            }
                        ],
                    }
                ],
            },
        ],
    }


def spatial_dna(*, blocking_wall: bool = False) -> dict[str, object]:
    elements: list[dict[str, object]] = [
        {
            "element_id": "ENTRY",
            "element_type": "picker_entry",
            "x_m": 0.25,
            "y_m": 0.25,
            "width_m": 0.5,
            "depth_m": 0.5,
            "rotation_deg": 0,
        }
    ]
    if blocking_wall:
        elements.append(
            {
                "element_id": "WALL-CROSS",
                "element_type": "wall",
                "x_m": 5.0,
                "y_m": 0.0,
                "width_m": 0.5,
                "depth_m": 8.0,
                "rotation_deg": 0,
            }
        )
    return {
        "source": "approved_store_dna",
        "store_code": "TEST",
        "picker_aisle_width_m": 1.2,
        "aisle_module_config": [
            {
                "aisle_id": "A",
                "left_modules": [{"module_id": 1, "side": "L", "shelf_count": 1}],
                "right_modules": [],
            },
            {
                "aisle_id": "PALLET",
                "left_modules": [{"module_id": 1, "side": "L", "shelf_count": 1}],
                "right_modules": [],
            },
        ],
        "architecture": {
            "schema_version": 1,
            "coordinate_system": "cartesian_m",
            "source": "manual_survey",
            "source_ref": "survey://TEST/route-gate-v1",
            "floor_width_m": 12.0,
            "floor_depth_m": 8.0,
            "elements": elements,
        },
    }


def truth_products() -> list[dict[str, object]]:
    return [
        product("SNACK", "Ambient Snack", category="Snacks"),
        product("WATER", "Water 6 x 1.5 L"),
    ]


def test_duplicate_legacy_module_ids_keep_distinct_spatial_identity() -> None:
    result = generate_production_plan(
        truth_products(),
        spatial_layout(),
        spatial_dna(),
    )

    route = result["architecture_route_objective"]
    assert route["available"] is True
    assert route["metric"] == "sales_weighted_single_origin_walk_m"
    assert route["module_distance_count"] == 2
    assert result["solver_optimizer_allowed"] is True
    assert result["publishable"] is True


def test_declared_architecture_with_unreachable_fixture_fails_closed() -> None:
    result = generate_production_plan(
        truth_products(),
        spatial_layout(),
        spatial_dna(blocking_wall=True),
    )

    route = result["architecture_route_objective"]
    assert route["available"] is False
    assert route["reason"] == "placed_module_unreachable"
    assert route["unreachable_module_ids"] == ["PALLET::1"]
    assert result["solver_optimizer_allowed"] is False
    assert result["publishable"] is False
    assert result["production_ready"] is False
    assert "architecture_route_unavailable:placed_module_unreachable" in result[
        "physical_truth"
    ]["blockers"]


def test_optimizer_cannot_search_around_unreachable_declared_architecture() -> None:
    result = optimize_production_plan(
        truth_products(),
        spatial_layout(),
        spatial_dna(blocking_wall=True),
    )

    assert result["optimizer"]["allowed"] is False
    assert result["optimizer"]["blocked_by_physical_truth"] is True
    assert result["optimizer"]["candidate_count"] == 1
    assert result["optimizer"]["selected_strategy"] == "baseline"
    assert result["production_ready"] is False
