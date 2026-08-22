from __future__ import annotations

from copy import deepcopy

import blind_benchmark as blind_v1
import blind_benchmark_v2 as blind_v2


def products(*, fast_width_cm: float = 20.0) -> list[dict]:
    return [
        {
            "sku": "FAST",
            "product_name": "Fast Snack",
            "brand": "EAY Test",
            "category_l1": "Snacks",
            "category_l2": "Snacks",
            "storage_type": "AMBIENT",
            "catalog_storage_type": "AMBIENT",
            "weight_kg": 0.2,
            "width_cm": fast_width_cm,
            "height_cm": 20,
            "depth_cm": 10,
            "dimension_source": "master",
            "image_url": "https://example.test/fast.jpg",
            "sales_qty_7d": 100,
        },
        {
            "sku": "SLOW",
            "product_name": "Slow Snack",
            "brand": "EAY Test",
            "category_l1": "Snacks",
            "category_l2": "Snacks",
            "storage_type": "AMBIENT",
            "catalog_storage_type": "AMBIENT",
            "weight_kg": 0.2,
            "width_cm": 20,
            "height_cm": 20,
            "depth_cm": 10,
            "dimension_source": "master",
            "image_url": "https://example.test/slow.jpg",
            "sales_qty_7d": 10,
        },
    ]


def shelf() -> dict:
    return {
        "shelf_no": 1,
        "shelf_width_cm": 100,
        "shelf_height_cm": 40,
        "shelf_depth_cm": 50,
        "max_weight_kg": 40,
        "zone_type": "eye",
        "allowed_storage_type": "AMBIENT",
        "products": [],
    }


def layout_v1() -> dict:
    return {
        "store_code": "BLIND",
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "module_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "x_m": 1.5,
                        "y_m": 2.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "shelves": [shelf()],
                    },
                    {
                        "module_id": 2,
                        "side": "R",
                        "module_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "x_m": 7.5,
                        "y_m": 2.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "shelves": [shelf()],
                    },
                ],
            }
        ],
    }


def store_v1() -> dict:
    return {
        "source": "user_approved_store_dna",
        "store_code": "BLIND",
        "picker_aisle_width_m": 1.2,
        "aisle_module_config": [
            {
                "aisle_id": "A",
                "left_modules": [{"module_id": 1, "side": "L", "shelf_count": 1}],
                "right_modules": [{"module_id": 2, "side": "R", "shelf_count": 1}],
            }
        ],
        "architecture": {
            "schema_version": 1,
            "coordinate_system": "cartesian_m",
            "source": "manual_survey",
            "source_ref": "survey://BLIND/v1",
            "floor_width_m": 10,
            "floor_depth_m": 6,
            "elements": [
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
                    "x_m": 0.25,
                    "y_m": 1.05,
                    "width_m": 0.5,
                    "depth_m": 0.5,
                },
            ],
        },
    }


def layout_v2() -> dict:
    layout = layout_v1()
    near, far = layout["aisles"][0]["modules"]
    near.pop("x_m")
    near.pop("y_m")
    near.update({"center_x_m": 2.0, "center_y_m": 2.0, "rotation_deg": 17})
    far.pop("x_m")
    far.pop("y_m")
    far.update({"center_x_m": 8.0, "center_y_m": 2.0, "rotation_deg": -17})
    return layout


def store_v2() -> dict:
    store = store_v1()
    store["architecture"] = {
        "schema_version": 2,
        "coordinate_system": "cartesian_m_centered_rect",
        "source": "lidar_scan",
        "source_ref": "scan://BLIND/v2",
        "floor_width_m": 10,
        "floor_depth_m": 6,
        "elements": [
            {
                "element_id": "ENTRY",
                "element_type": "picker_entry",
                "center_x_m": 0.5,
                "center_y_m": 0.5,
                "width_m": 0.5,
                "depth_m": 0.5,
                "rotation_deg": 11,
            },
            {
                "element_id": "EXIT",
                "element_type": "picker_exit",
                "center_x_m": 0.5,
                "center_y_m": 1.3,
                "width_m": 0.5,
                "depth_m": 0.5,
                "rotation_deg": -13,
            },
            {
                "element_id": "ANGLED-WALL",
                "element_type": "wall",
                "center_x_m": 5.0,
                "center_y_m": 4.8,
                "width_m": 0.2,
                "depth_m": 1.5,
                "rotation_deg": 17,
            },
        ],
    }
    return store


def candidate(
    layout: dict,
    *,
    fast_near: bool,
    fast_facing: int = 1,
    fast_overrides: dict | None = None,
) -> dict:
    planogram = deepcopy(layout)
    modules = planogram["aisles"][0]["modules"]
    near_product = "FAST" if fast_near else "SLOW"
    far_product = "SLOW" if fast_near else "FAST"
    near_row = {"sku": near_product, "facing_count": 1}
    far_row = {"sku": far_product, "facing_count": 1}
    if near_product == "FAST":
        near_row["facing_count"] = fast_facing
        near_row.update(fast_overrides or {})
    else:
        far_row["facing_count"] = fast_facing
        far_row.update(fast_overrides or {})
    modules[0]["shelves"][0]["products"] = [near_row]
    modules[1]["shelves"][0]["products"] = [far_row]
    return {"planogram": planogram}


def fast_orders(count: int = 8) -> list[dict]:
    return [
        {"order_id": f"O-{index}", "skus": ["FAST"]}
        for index in range(count)
    ]


def test_v1_real_simulator_prefers_high_frequency_sku_near_picker_anchors() -> None:
    layout = layout_v1()
    result = blind_v1.benchmark_candidates(
        products=products(),
        layout=layout,
        store_dna=store_v1(),
        orders=fast_orders(),
        candidate_a=candidate(layout, fast_near=True),
        candidate_b=candidate(layout, fast_near=False),
    )

    assert result["available"] is True
    assert result["winner_on_repository_objective"] == "A"
    assert result["candidate_a"]["objective"]["hard_violation_count"] == 0
    assert result["candidate_b"]["objective"]["hard_violation_count"] == 0
    assert result["candidate_a"]["tour"]["average_m"] < result["candidate_b"]["tour"]["average_m"]
    assert result["production_evidence"] is False
    assert result["market_leadership_proven"] is False
    assert result["promotion_allowed"] is False


def test_candidate_cannot_shrink_master_dimensions_to_escape_capacity() -> None:
    layout = layout_v1()
    result = blind_v1.benchmark_candidates(
        products=products(fast_width_cm=60),
        layout=layout,
        store_dna=store_v1(),
        orders=fast_orders(),
        candidate_a=candidate(layout, fast_near=True),
        candidate_b=candidate(
            layout,
            fast_near=True,
            fast_facing=2,
            fast_overrides={"width_cm": 1, "height_cm": 1, "depth_cm": 1},
        ),
    )

    assert result["available"] is True
    assert result["winner_on_repository_objective"] == "A"
    assert "candidate_shelf_capacity_overflow" in result["candidate_b"]["blockers"]
    violation = result["candidate_b"]["capacity_violations"][0]
    assert violation["used_width_cm"] == 120.0
    assert violation["shelf_width_cm"] == 100.0
    assert result["candidate_b"]["objective"]["hard_violation_count"] > 0


def test_duplicate_and_unknown_skus_are_hard_blockers_not_new_truth() -> None:
    layout = layout_v1()
    bad = candidate(layout, fast_near=True)
    modules = bad["planogram"]["aisles"][0]["modules"]
    modules[1]["shelves"][0]["products"] = [
        {"sku": "FAST"},
        {"sku": "UNKNOWN"},
        {"sku": "SLOW"},
    ]

    result = blind_v1.benchmark_candidates(
        products=products(),
        layout=layout,
        store_dna=store_v1(),
        orders=fast_orders(),
        candidate_a=candidate(layout, fast_near=True),
        candidate_b=bad,
    )

    blockers = result["candidate_b"]["blockers"]
    assert any(row.startswith("candidate_duplicate_sku_placement:FAST") for row in blockers)
    assert any(row.startswith("candidate_unknown_sku:UNKNOWN") for row in blockers)
    assert result["winner_on_repository_objective"] == "A"


def test_v2_real_oriented_simulator_ranks_without_production_authority() -> None:
    layout = layout_v2()
    v1_result = blind_v1.benchmark_candidates(
        products=products(),
        layout=layout,
        store_dna=store_v2(),
        orders=fast_orders(),
        candidate_a=candidate(layout, fast_near=True),
        candidate_b=candidate(layout, fast_near=False),
    )
    assert v1_result["available"] is False
    assert v1_result["reason"] == "architecture_v2_picker_benchmark_pending"

    result = blind_v2.benchmark_candidates_v2(
        products=products(),
        layout=layout,
        store_dna=store_v2(),
        orders=fast_orders(),
        candidate_a=candidate(layout, fast_near=True),
        candidate_b=candidate(layout, fast_near=False),
    )

    assert result["available"] is True
    assert result["winner_on_repository_objective"] == "A"
    assert result["spatial_contract"] == "store-architecture-v2-oriented-polygons"
    assert result["candidate_a"]["tour"]["average_m"] < result["candidate_b"]["tour"]["average_m"]
    assert result["non_orthogonal_element_count"] >= 1
    assert result["non_orthogonal_module_count"] == 2
    assert result["production_authority"] is False
    assert result["production_evidence"] is False
    assert result["market_leadership_proven"] is False
    assert result["promotion_allowed"] is False
