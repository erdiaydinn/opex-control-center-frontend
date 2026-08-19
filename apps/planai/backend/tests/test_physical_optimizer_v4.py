from __future__ import annotations

from copy import deepcopy

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
