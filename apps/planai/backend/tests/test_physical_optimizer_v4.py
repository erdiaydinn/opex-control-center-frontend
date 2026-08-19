from __future__ import annotations

from copy import deepcopy

import blind_benchmark as blind
import blind_benchmark_v2 as blind_v2
import physical_optimizer_v4 as v4


def objective(*, hard: int = 0, p95: float = 40.0, unplaced: float = 0.0) -> dict:
    return {
        "hard_violation_count": hard,
        "weighted_unplaced_sales": unplaced,
        "unplaced_sku_count": 1 if unplaced else 0,
        "tour_unsimulated_order_count": 0,
        "tour_p95_m": p95,
        "tour_average_m": max(0.0, p95 - 5),
        "coverage_shortfall": 0.0,
        "picking_route_cost": p95,
        "brand_fragmentation": 0,
        "capacity_pressure": 0.0,
    }


def tour(p95: float = 40.0) -> dict:
    return {
        "available": True,
        "input_order_count": 1,
        "simulated_order_count": 1,
        "coverage_pct": 100.0,
        "unsimulated_order_count": 0,
        "average_m": max(0.0, p95 - 5),
        "p50_m": max(0.0, p95 - 7),
        "p90_m": max(0.0, p95 - 1),
        "p95_m": p95,
        "max_m": p95 + 2,
    }


def benchmark_product(sku: str, *, width_cm: float = 8.0, sales: float = 10.0) -> dict:
    return {
        "sku": sku,
        "product_name": sku,
        "brand": "Benchmark",
        "category_l1": "Snacks",
        "category_l2": "Snacks",
        "catalog_storage_condition_raw": "RAF",
        "storage_type": "RAF",
        "width_cm": width_cm,
        "height_cm": 18.0,
        "depth_cm": 6.0,
        "weight_kg": 0.2,
        "sales_qty_7d": sales,
        "dimension_source": "master",
        "image_url": f"https://example.test/{sku}.jpg",
        "catalog_global_product_id": f"CAT-{sku}",
    }


def benchmark_layout() -> dict:
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
                        "module_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 35,
                                "shelf_depth_cm": 50,
                                "max_weight_kg": 45,
                                "zone_type": "eye",
                                "allowed_storage_type": "AMBIENT",
                            }
                        ],
                    },
                    {
                        "module_id": 2,
                        "x_m": 7.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "side": "R",
                        "module_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 35,
                                "shelf_depth_cm": 50,
                                "max_weight_kg": 45,
                                "zone_type": "eye",
                                "allowed_storage_type": "AMBIENT",
                            }
                        ],
                    },
                ],
            }
        ]
    }


def benchmark_store_dna(*, schema_version: int = 1) -> dict:
    coordinate_system = "cartesian_m" if schema_version == 1 else "cartesian_m_centered_rect"
    return {
        "source": "user_approved_store_dna",
        "store_code": "TEST",
        "picker_aisle_width_m": 1.2,
        "aisle_module_config": [
            {
                "aisle_id": "A",
                "left_modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "fixture_type": "steel_rack",
                        "shelf_count": 1,
                    }
                ],
                "right_modules": [
                    {
                        "module_id": 2,
                        "side": "R",
                        "fixture_type": "steel_rack",
                        "shelf_count": 1,
                    }
                ],
            }
        ],
        "architecture": {
            "schema_version": schema_version,
            "coordinate_system": coordinate_system,
            "source": "manual_survey",
            "source_ref": f"survey://BENCHMARK/v{schema_version}",
            "floor_width_m": 10.0,
            "floor_depth_m": 6.0,
            "elements": [
                {
                    "element_id": "ENTRY",
                    "element_type": "picker_entry",
                    "x_m": 0.25,
                    "y_m": 0.25,
                    "width_m": 0.5,
                    "depth_m": 0.5,
                    "rotation_deg": 0,
                },
                {
                    "element_id": "EXIT",
                    "element_type": "picker_exit",
                    # Return-to-origin picking makes fixture distance observable;
                    # a through-route exit would make collinear fixtures degenerate.
                    "x_m": 0.25,
                    "y_m": 0.25,
                    "width_m": 0.5,
                    "depth_m": 0.5,
                    "rotation_deg": 0,
                },
            ],
        },
    }


def benchmark_candidate(module_for_fast_sku: int) -> dict:
    other_module = 2 if module_for_fast_sku == 1 else 1
    return {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": module_for_fast_sku,
                            "side": "L" if module_for_fast_sku == 1 else "R",
                            "module_type": "regular_shelf",
                            "storage_type": "AMBIENT",
                            "shelves": [
                                {
                                    "shelf_no": 1,
                                    "shelf_width_cm": 100,
                                    "zone_type": "eye",
                                    "allowed_storage_type": "AMBIENT",
                                    "products": [{"sku": "FAST", "facing_count": 1}],
                                }
                            ],
                        },
                        {
                            "module_id": other_module,
                            "side": "R" if other_module == 2 else "L",
                            "module_type": "regular_shelf",
                            "storage_type": "AMBIENT",
                            "shelves": [
                                {
                                    "shelf_no": 1,
                                    "shelf_width_cm": 100,
                                    "zone_type": "eye",
                                    "allowed_storage_type": "AMBIENT",
                                    "products": [{"sku": "SLOW", "facing_count": 1}],
                                }
                            ],
                        },
                    ],
                }
            ]
        }
    }


def test_search_profiles_expand_v3_without_randomness() -> None:
    first = v4.search_profiles()
    second = v4.search_profiles()

    assert first == second
    assert first[0] == ("baseline", None)
    assert len(first) > len(v4.v3.STRATEGIES)
    keys = [v4._config_key(config) for _, config in first]
    assert len(keys) == len(set(keys))
    assert len(first) <= v4.MAX_SEARCH_CANDIDATES


def test_missing_baskets_delegates_to_v3(monkeypatch) -> None:
    delegated = {"solver_optimizer_allowed": True, "source": "v3"}

    def fake_v3(**kwargs):
        return deepcopy(delegated)

    monkeypatch.setattr(v4.v3, "optimize_production_plan", fake_v3)
    result = v4.optimize_production_plan(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        orders=[],
        require_images=False,
    )

    assert result["source"] == "v3"
    meta = result["market_search_optimizer"]
    assert meta["effective"] is False
    assert meta["reason"] == "order_baskets_missing"
    assert meta["production_authority"] is False


def test_v4_can_select_better_candidate_beyond_v3_fixed_portfolio(monkeypatch) -> None:
    generated = 0

    def fake_generate(*, scoring_config=None, **kwargs):
        nonlocal generated
        token = generated
        generated += 1
        return {
            "solver_optimizer_allowed": True,
            "token": token,
            "scoring_config": scoring_config,
        }

    def fake_components(result, source_products, layout, store_dna, orders):
        token = result["token"]
        # The best candidate deliberately sits beyond the original V3 portfolio.
        p95 = 8.0 if token == 12 else 40.0 + token
        return objective(p95=p95), {"basis": "test-route"}, tour(p95)

    monkeypatch.setattr(v4, "generate_production_plan", fake_generate)
    monkeypatch.setattr(v4.v3, "objective_components", fake_components)

    result = v4.optimize_production_plan(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        orders=[{"skus": ["SKU-1"]}],
        require_images=False,
        max_candidates=24,
    )

    meta = result["market_search_optimizer"]
    assert meta["effective"] is True
    assert meta["candidate_count"] == 24
    assert meta["candidate_count"] > len(v4.v3.STRATEGIES)
    assert result["token"] == 12
    assert meta["selected_strategy"] != "baseline"
    assert meta["selected_tour"]["p95_m"] == 8.0
    assert meta["improved"] is True
    assert meta["production_authority"] is False


def test_hard_violation_always_beats_shorter_tour(monkeypatch) -> None:
    generated = 0

    def fake_generate(*, scoring_config=None, **kwargs):
        nonlocal generated
        token = generated
        generated += 1
        return {"solver_optimizer_allowed": True, "token": token}

    def fake_components(result, source_products, layout, store_dna, orders):
        token = result["token"]
        if token == 1:
            return objective(hard=1, p95=1), {"basis": "test-route"}, tour(1)
        p95 = 30.0 + token
        return objective(p95=p95), {"basis": "test-route"}, tour(p95)

    monkeypatch.setattr(v4, "generate_production_plan", fake_generate)
    monkeypatch.setattr(v4.v3, "objective_components", fake_components)

    result = v4.optimize_production_plan(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        orders=[{"skus": ["SKU-1"]}],
        require_images=False,
        max_candidates=12,
    )

    assert result["token"] == 0
    meta = result["market_search_optimizer"]
    assert meta["selected_strategy"] == "baseline"
    assert meta["baseline_preserved"] is True
    unsafe = next(row for row in meta["candidates"] if row["strategy"] != "baseline")
    assert unsafe["hard_violation_count"] in {0, 1}


def test_candidate_budget_is_bounded() -> None:
    assert v4.MAX_SEARCH_CANDIDATES == 32
    assert len(v4.search_profiles()) <= v4.MAX_SEARCH_CANDIDATES


def test_blind_candidate_cannot_override_master_dimensions_and_capacity_truth() -> None:
    prepared = blind.prepare_production_products(
        [benchmark_product("FAST", width_cm=60), benchmark_product("SLOW", width_cm=50)]
    )
    candidate = benchmark_candidate(1)
    products = candidate["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"]
    products[0]["width_cm"] = 1
    products[0]["facing_count"] = 2
    second = candidate["planogram"]["aisles"][0]["modules"][1]["shelves"][0]["products"]
    second.append({"sku": "FAST"})
    second.append({"sku": "UNKNOWN"})

    hydrated = blind._hydrate_candidate(
        candidate=candidate,
        prepared_products=prepared,
        layout=benchmark_layout(),
    )

    assert hydrated["available"] is True
    assert "candidate_shelf_capacity_overflow" in hydrated["blockers"]
    assert any(blocker.startswith("candidate_duplicate_sku_placement:FAST") for blocker in hydrated["blockers"])
    assert any(blocker.startswith("candidate_unknown_sku:UNKNOWN") for blocker in hydrated["blockers"])
    fast = hydrated["result"]["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"][0]
    assert fast["width_cm"] == 60
    assert fast["facing_count"] == 2


def test_real_candidate_evaluation_rewards_nearer_fast_sku_under_same_truth() -> None:
    prepared = blind.prepare_production_products(
        [benchmark_product("FAST", sales=100), benchmark_product("SLOW", sales=1)]
    )
    orders = [
        {"skus": ["FAST"]},
        {"skus": ["FAST"]},
        {"skus": ["FAST", "SLOW"]},
    ]
    near = blind._candidate_evaluation(
        candidate=benchmark_candidate(1),
        prepared_products=prepared,
        layout=benchmark_layout(),
        store_dna=benchmark_store_dna(),
        orders=orders,
    )
    far = blind._candidate_evaluation(
        candidate=benchmark_candidate(2),
        prepared_products=prepared,
        layout=benchmark_layout(),
        store_dna=benchmark_store_dna(),
        orders=orders,
    )

    assert near["available"] is True
    assert far["available"] is True
    assert near["objective"]["hard_violation_count"] == 0
    assert far["objective"]["hard_violation_count"] == 0
    assert near["tour"]["coverage_pct"] == 100.0
    assert far["tour"]["coverage_pct"] == 100.0
    assert near["objective"]["tour_average_m"] < far["objective"]["tour_average_m"]


def test_oriented_v2_blind_benchmark_preserves_real_angles_and_route_ranking() -> None:
    layout = benchmark_layout()
    layout["aisles"][0]["modules"][0]["rotation_deg"] = 17.0
    layout["aisles"][0]["modules"][1]["rotation_deg"] = 343.0
    store_dna = benchmark_store_dna(schema_version=2)
    store_dna["architecture"]["elements"].append(
        {
            "element_id": "WALL-17",
            "element_type": "wall",
            "x_m": 4.0,
            "y_m": 4.0,
            "width_m": 1.5,
            "depth_m": 0.1,
            "rotation_deg": 17.0,
        }
    )
    result = blind_v2.benchmark_candidates_v2(
        products=[
            benchmark_product("FAST", sales=100),
            benchmark_product("SLOW", sales=1),
        ],
        layout=layout,
        store_dna=store_dna,
        orders=[{"skus": ["FAST"]}, {"skus": ["FAST", "SLOW"]}],
        candidate_a=benchmark_candidate(1),
        candidate_b=benchmark_candidate(2),
    )

    assert result["available"] is True
    assert result["spatial_contract"] == "store-architecture-v2-oriented-polygons"
    assert result["non_orthogonal_element_count"] == 1
    assert result["non_orthogonal_module_count"] == 2
    assert result["winner_on_repository_objective"] == "A"
    assert result["candidate_a"]["tour"]["coverage_pct"] == 100.0
    assert result["candidate_a"]["tour_evidence"]["simulation_version"] == (
        "picker-tour-simulation-v2-oriented-polygons"
    )
    assert result["production_authority"] is False
    assert result["production_evidence"] is False
    assert result["market_leadership_proven"] is False
