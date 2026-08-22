from __future__ import annotations

from copy import deepcopy

import physical_layout_optimizer_v5 as v5


def objective(*, hard: int = 0, p95: float = 20.0) -> dict[str, float | int]:
    return {
        "hard_violation_count": hard,
        "weighted_unplaced_sales": 0.0,
        "unplaced_sku_count": 0,
        "tour_unsimulated_order_count": 0,
        "tour_p95_m": p95,
        "tour_average_m": max(0.0, p95 - 3.0),
        "coverage_shortfall": 0.0,
        "brand_fragmentation": 0.0,
        "capacity_pressure": 0.0,
    }


def optimizer_result(*, hard: int = 0, p95: float = 20.0) -> dict:
    return {
        "market_search_optimizer": {
            "optimizer_version": "physical-plan-optimizer-v4-bounded-search",
            "selected_strategy": "test",
            "selected_objective": objective(hard=hard, p95=p95),
            "selected_tour": {
                "p95_m": p95,
                "average_m": max(0.0, p95 - 3.0),
                "coverage_pct": 100.0,
            },
            "candidate_count": 12,
        }
    }


def shelf(*, width: float = 100.0, max_weight: float = 45.0) -> dict:
    return {
        "shelf_no": 1,
        "shelf_width_cm": width,
        "shelf_height_cm": 35.0,
        "shelf_depth_cm": 50.0,
        "max_weight_kg": max_weight,
        "allowed_storage_type": "AMBIENT",
        "zone_type": "eye",
    }


def module(
    module_id: int,
    *,
    x_m: float,
    rotation_deg: float = 0.0,
    relocatable: bool = True,
    storage_type: str = "AMBIENT",
    shelf_width: float = 100.0,
    fixture_type: str = "steel_rack",
    utility_attested: bool = False,
) -> dict:
    return {
        "module_id": module_id,
        "x_m": x_m,
        "y_m": 1.0,
        "width_m": 1.0,
        "depth_m": 0.5,
        "rotation_deg": rotation_deg,
        "relocatable": relocatable,
        "fixture_type": fixture_type,
        "storage_type": storage_type,
        "utility_relocation_attested": utility_attested,
        "shelves": [shelf(width=shelf_width)],
    }


def layout() -> dict:
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    module(1, x_m=2.0, rotation_deg=0.0),
                    module(2, x_m=8.0, rotation_deg=90.0),
                ],
            }
        ]
    }


def store_dna(*, schema_version: int = 1) -> dict:
    return {
        "architecture": {
            "schema_version": schema_version,
            "coordinate_system": "cartesian_m",
        }
    }


def module_by_id(candidate_layout: dict, module_id: int) -> dict:
    for aisle in candidate_layout["aisles"]:
        for row in aisle["modules"]:
            if row["module_id"] == module_id:
                return row
    raise AssertionError(f"missing module {module_id}")


def always_valid(*args, **kwargs) -> dict:
    return {"valid": True, "blockers": []}


def test_equivalent_fixtures_can_pair_across_different_current_rotations() -> None:
    pairs = v5._relocation_pairs(layout())

    assert pairs == [("A::1", "A::2")]


def test_non_relocatable_or_non_equivalent_fixture_never_pairs() -> None:
    candidate = layout()
    candidate["aisles"][0]["modules"][1]["relocatable"] = False
    assert v5._relocation_pairs(candidate) == []

    candidate = layout()
    candidate["aisles"][0]["modules"][1]["shelves"][0][
        "shelf_width_cm"
    ] = 120.0
    assert v5._relocation_pairs(candidate) == []

    candidate = layout()
    candidate["aisles"][0]["modules"][1]["storage_type"] = "CHILLED"
    assert v5._relocation_pairs(candidate) == []


def test_cold_or_utility_fixture_requires_explicit_relocation_attestation() -> None:
    candidate = {
        "aisles": [
            {
                "aisle_id": "C",
                "modules": [
                    module(
                        1,
                        x_m=2.0,
                        fixture_type="chilled_cabinet",
                        storage_type="CHILLED",
                    ),
                    module(
                        2,
                        x_m=6.0,
                        fixture_type="chilled_cabinet",
                        storage_type="CHILLED",
                    ),
                ],
            }
        ]
    }
    assert v5._relocation_pairs(candidate) == []

    for row in candidate["aisles"][0]["modules"]:
        row["utility_relocation_attested"] = True
    assert v5._relocation_pairs(candidate) == [("C::1", "C::2")]


def test_no_eligible_pair_is_truthfully_inactive(monkeypatch) -> None:
    candidate = layout()
    for row in candidate["aisles"][0]["modules"]:
        row["relocatable"] = False

    monkeypatch.setattr(v5, "layout_architecture_report", always_valid)
    monkeypatch.setattr(
        v5.allocation_v4,
        "optimize_production_plan",
        lambda **kwargs: optimizer_result(p95=20.0),
    )

    result = v5.optimize_physical_layout(
        products=[{"sku": "FAST"}],
        layout=candidate,
        store_dna=store_dna(),
        orders=[{"skus": ["FAST"]}],
        require_images=False,
    )
    meta = result["physical_layout_optimizer"]

    assert meta["allowed"] is True
    assert meta["effective"] is False
    assert meta["reason"] == "no_eligible_relocation_pairs"
    assert meta["evaluated_layout_count"] == 1
    assert meta["eligible_relocation_pair_count"] == 0
    assert meta["physical_relocation_authority"] is False
    assert meta["installation_approved"] is False


def test_architecture_invalid_swap_is_rejected_before_reoptimization(monkeypatch) -> None:
    calls = []

    def truth(candidate_layout, _store_dna):
        moved = module_by_id(candidate_layout, 1)["x_m"] == 8.0
        if moved:
            return {
                "valid": False,
                "blockers": ["layout_architecture_hard_violation"],
            }
        return {"valid": True, "blockers": []}

    def optimize(**kwargs):
        calls.append(kwargs["layout"])
        return optimizer_result(p95=20.0)

    monkeypatch.setattr(v5, "layout_architecture_report", truth)
    monkeypatch.setattr(v5.allocation_v4, "optimize_production_plan", optimize)

    result = v5.optimize_physical_layout(
        products=[{"sku": "FAST"}],
        layout=layout(),
        store_dna=store_dna(),
        orders=[{"skus": ["FAST"]}],
        require_images=False,
    )
    meta = result["physical_layout_optimizer"]

    assert len(calls) == 1
    assert meta["selected_layout_label"] == "baseline"
    assert meta["evaluated_layout_count"] == 1
    assert meta["rejected_layout_count"] == 1
    assert meta["rejected_layouts"][0]["reason"] == (
        "layout_architecture_invalid"
    )
    assert meta["improved"] is False


def test_safe_swap_can_win_when_same_evidence_route_objective_improves(monkeypatch) -> None:
    calls = []

    def optimize(**kwargs):
        module_one = module_by_id(kwargs["layout"], 1)
        p95 = 9.0 if module_one["x_m"] == 8.0 else 24.0
        calls.append((module_one["x_m"], kwargs["max_candidates"]))
        return optimizer_result(p95=p95)

    monkeypatch.setattr(v5, "layout_architecture_report", always_valid)
    monkeypatch.setattr(v5.allocation_v4, "optimize_production_plan", optimize)

    result = v5.optimize_physical_layout(
        products=[{"sku": "FAST"}],
        layout=layout(),
        store_dna=store_dna(),
        orders=[{"skus": ["FAST"]}],
        require_images=False,
    )
    meta = result["physical_layout_optimizer"]

    assert calls == [(2.0, 12), (8.0, 12)]
    assert meta["selected_layout_label"] == "swap::A::1<->A::2"
    assert meta["selected_moved_modules"] == ["A::1", "A::2"]
    assert meta["improved"] is True
    assert module_by_id(result["physical_layout"], 1)["x_m"] == 8.0
    assert meta["production_authority"] is False
    assert meta["physical_relocation_authority"] is False
    assert meta["installation_approved"] is False


def test_shorter_route_with_hard_violation_cannot_beat_baseline(monkeypatch) -> None:
    def optimize(**kwargs):
        moved = module_by_id(kwargs["layout"], 1)["x_m"] == 8.0
        return optimizer_result(
            hard=1 if moved else 0,
            p95=1.0 if moved else 50.0,
        )

    monkeypatch.setattr(v5, "layout_architecture_report", always_valid)
    monkeypatch.setattr(v5.allocation_v4, "optimize_production_plan", optimize)

    result = v5.optimize_physical_layout(
        products=[{"sku": "FAST"}],
        layout=layout(),
        store_dna=store_dna(),
        orders=[{"skus": ["FAST"]}],
        require_images=False,
    )
    meta = result["physical_layout_optimizer"]

    assert meta["selected_layout_label"] == "baseline"
    assert meta["baseline_preserved"] is True
    assert meta["improved"] is False


def test_candidate_budgets_are_bounded_and_forwarded(monkeypatch) -> None:
    forwarded = []

    def optimize(**kwargs):
        forwarded.append(kwargs["max_candidates"])
        return optimizer_result(p95=20.0)

    monkeypatch.setattr(v5, "layout_architecture_report", always_valid)
    monkeypatch.setattr(v5.allocation_v4, "optimize_production_plan", optimize)

    result = v5.optimize_physical_layout(
        products=[{"sku": "FAST"}],
        layout=layout(),
        store_dna=store_dna(),
        orders=[{"skus": ["FAST"]}],
        max_layout_candidates=999,
        max_allocation_candidates=999,
        require_images=False,
    )
    meta = result["physical_layout_optimizer"]

    assert meta["layout_candidate_budget"] == v5.MAX_LAYOUT_CANDIDATES == 32
    assert meta["allocation_candidate_budget_per_layout"] == (
        v5.MAX_ALLOCATION_CANDIDATES
    ) == 24
    assert forwarded == [24, 24]
    assert meta["evaluated_layout_count"] <= v5.MAX_LAYOUT_CANDIDATES


def test_v5_refuses_architecture_v2_and_missing_baskets() -> None:
    no_v2 = v5.optimize_physical_layout(
        products=[{"sku": "FAST"}],
        layout=deepcopy(layout()),
        store_dna=store_dna(schema_version=2),
        orders=[{"skus": ["FAST"]}],
        require_images=False,
    )
    assert no_v2["allowed"] is False
    assert no_v2["reason"] == "architecture_v1_required_for_v5_relocation_search"
    assert no_v2["physical_relocation_authority"] is False

    no_baskets = v5.optimize_physical_layout(
        products=[{"sku": "FAST"}],
        layout=deepcopy(layout()),
        store_dna=store_dna(),
        orders=[],
        require_images=False,
    )
    assert no_baskets["allowed"] is False
    assert no_baskets["reason"] == "order_baskets_missing"
    assert no_baskets["physical_relocation_authority"] is False
