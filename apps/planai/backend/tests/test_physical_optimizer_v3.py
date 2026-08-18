from __future__ import annotations

from copy import deepcopy

import physical_optimizer_v3 as v3


def plan(*, unplaced_sales: float = 0.0, strategy: str = "baseline") -> dict:
    unplaced = []
    if unplaced_sales > 0:
        unplaced = [{"sku": "LOST", "sales_qty_7d": unplaced_sales}]
    return {
        "solver_optimizer_allowed": True,
        "production_ready": True,
        "publishable": True,
        "summary": {"placed": 1, "unplaced": len(unplaced)},
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [
                                {
                                    "shelf_no": 1,
                                    "products": [
                                        {
                                            "sku": "SKU-1",
                                            "sales_qty_7d": 10,
                                            "_test_strategy": strategy,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "unplaced": unplaced,
        "diagnostics": {"summary": {"strict_rule_violation_count": 0}},
        "operational_physical_validation": {"violation_count": 0},
        "physical_truth": {"blockers": []},
    }


def test_basket_fingerprint_ignores_raw_order_ids() -> None:
    first = [
        {"order_id": "customer-order-1", "skus": ["B", "A"]},
        {"order_id": "customer-order-2", "items": [{"sku": "C"}]},
    ]
    second = [
        {"order_id": "other-id", "skus": ["A", "B"]},
        {"order_id": "another-id", "skus": ["C"]},
    ]

    assert v3.order_basket_fingerprint(first) == v3.order_basket_fingerprint(second)


def test_no_baskets_delegates_to_v2_without_fabricating_demand(monkeypatch) -> None:
    delegated = plan()

    def fake_v2(**kwargs):
        return deepcopy(delegated)

    monkeypatch.setattr(v3.v2, "optimize_production_plan", fake_v2)
    result = v3.optimize_production_plan(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        orders=[],
        require_images=False,
    )

    meta = result["picker_tour_optimizer"]
    assert meta["allowed"] is False
    assert meta["effective"] is False
    assert meta["reason"] == "order_baskets_missing"
    assert meta["order_basket_fingerprint"] is None
    assert meta["production_evidence"] is False


def test_tour_metric_breaks_ties_only_after_physical_and_placement_truth(monkeypatch) -> None:
    calls = []

    def fake_generate(*, scoring_config=None, **kwargs):
        strategy = "baseline" if scoring_config is None else f"candidate-{len(calls) + 1}"
        calls.append(strategy)
        return plan(strategy=strategy)

    def fake_components(result, source_products, layout, store_dna, orders):
        strategy = result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"][0]["_test_strategy"]
        p95 = 30.0 if strategy == "baseline" else 12.0
        base = {
            "hard_violation_count": 0,
            "weighted_unplaced_sales": 0.0,
            "unplaced_sku_count": 0,
            "coverage_shortfall": 0.0,
            "picking_route_cost": p95,
            "brand_fragmentation": 0,
            "capacity_pressure": 0.0,
            "tour_unsimulated_order_count": 0,
            "tour_p95_m": p95,
            "tour_average_m": p95 - 2,
        }
        return base, {"basis": "architecture-grid-astar-v1"}, {
            "available": True,
            "coverage_pct": 100.0,
            "unsimulated_order_count": 0,
            "p95_m": p95,
            "average_m": p95 - 2,
            "p50_m": p95 - 5,
            "p90_m": p95 - 1,
            "max_m": p95 + 2,
            "input_order_count": 2,
            "simulated_order_count": 2,
        }

    monkeypatch.setattr(v3, "generate_production_plan", fake_generate)
    monkeypatch.setattr(v3, "objective_components", fake_components)

    result = v3.optimize_production_plan(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        orders=[{"order_id": "O", "skus": ["SKU-1"]}],
        require_images=False,
    )

    meta = result["picker_tour_optimizer"]
    assert meta["allowed"] is True
    assert meta["effective"] is True
    assert meta["candidate_count"] == len(v3.STRATEGIES)
    assert meta["selected_strategy"] != "baseline"
    assert meta["selected_tour"]["p95_m"] == 12.0
    assert meta["baseline_preserved"] is True
    assert meta["improved"] is True


def test_shorter_tour_cannot_beat_high_sales_unplacement(monkeypatch) -> None:
    generated = 0

    def fake_generate(*, scoring_config=None, **kwargs):
        nonlocal generated
        generated += 1
        if scoring_config is None:
            return plan(strategy="baseline")
        return plan(unplaced_sales=100, strategy=f"candidate-{generated}")

    def fake_components(result, source_products, layout, store_dna, orders):
        unplaced = bool(result.get("unplaced"))
        base = {
            "hard_violation_count": 0,
            "weighted_unplaced_sales": 100.0 if unplaced else 0.0,
            "unplaced_sku_count": 1 if unplaced else 0,
            "coverage_shortfall": 0.0,
            "picking_route_cost": 1.0 if unplaced else 50.0,
            "brand_fragmentation": 0,
            "capacity_pressure": 0.0,
            "tour_unsimulated_order_count": 0,
            "tour_p95_m": 1.0 if unplaced else 50.0,
            "tour_average_m": 1.0 if unplaced else 45.0,
        }
        tour = {
            "available": True,
            "coverage_pct": 100.0,
            "unsimulated_order_count": 0,
            "p95_m": base["tour_p95_m"],
            "average_m": base["tour_average_m"],
            "p50_m": base["tour_average_m"],
            "p90_m": base["tour_p95_m"],
            "max_m": base["tour_p95_m"],
            "input_order_count": 1,
            "simulated_order_count": 1,
        }
        return base, {"basis": "architecture-grid-astar-v1"}, tour

    monkeypatch.setattr(v3, "generate_production_plan", fake_generate)
    monkeypatch.setattr(v3, "objective_components", fake_components)

    result = v3.optimize_production_plan(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        orders=[{"order_id": "O", "skus": ["SKU-1"]}],
        require_images=False,
    )

    meta = result["picker_tour_optimizer"]
    assert meta["selected_strategy"] == "baseline"
    assert meta["improved"] is False
    assert meta["selected_objective"]["weighted_unplaced_sales"] == 0.0


def test_unsimulated_orders_rank_before_tour_distance() -> None:
    full_coverage = {
        "hard_violation_count": 0,
        "weighted_unplaced_sales": 0,
        "unplaced_sku_count": 0,
        "tour_unsimulated_order_count": 0,
        "tour_p95_m": 100,
        "tour_average_m": 90,
        "coverage_shortfall": 0,
        "brand_fragmentation": 0,
        "capacity_pressure": 0,
    }
    partial_coverage = {
        **full_coverage,
        "tour_unsimulated_order_count": 1,
        "tour_p95_m": 1,
        "tour_average_m": 1,
    }

    assert v3.objective_key(full_coverage) < v3.objective_key(partial_coverage)
