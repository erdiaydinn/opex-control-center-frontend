from __future__ import annotations

from copy import deepcopy

import physical_layout_candidate_preview as candidate_preview
import physical_layout_optimizer_v5 as v5


def layout() -> dict:
    shelf = {
        "shelf_width_cm": 100,
        "shelf_height_cm": 40,
        "shelf_depth_cm": 50,
        "max_weight_kg": 50,
        "allowed_storage_type": "AMBIENT",
        "zone_type": "eye",
    }
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": "1",
                        "fixture_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "relocatable": True,
                        "x_m": 1.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "shelves": [deepcopy(shelf)],
                    },
                    {
                        "module_id": "2",
                        "fixture_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "relocatable": True,
                        "x_m": 5.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "shelves": [deepcopy(shelf)],
                    },
                ],
            }
        ]
    }


def optimizer_result() -> dict:
    return {
        "market_search_optimizer": {
            "selected_objective": {
                "hard_violation_count": 0,
                "weighted_unplaced_sales": 0,
                "unplaced_sku_count": 0,
                "tour_unsimulated_order_count": 0,
                "tour_p95_m": 20,
                "tour_average_m": 18,
                "coverage_shortfall": 0,
                "brand_fragmentation": 0,
                "capacity_pressure": 0,
            },
            "selected_strategy": "test",
        },
        "planogram": {"aisles": []},
    }


def test_invalid_fingerprint_fails_closed_without_running_search(monkeypatch) -> None:
    monkeypatch.setattr(
        candidate_preview.v5,
        "optimize_physical_layout",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("search must not run")),
    )
    result = candidate_preview.preview_physical_layout_candidate(
        products=[],
        layout={},
        store_dna={},
        orders=[],
        layout_fingerprint="not-a-fingerprint",
    )
    assert result["available"] is False
    assert result["reason"] == "layout_fingerprint_invalid"
    assert result["production_authority"] is False


def test_replay_accepts_only_fingerprint_from_recomputed_search(monkeypatch) -> None:
    baseline = layout()
    swapped = v5._swap_spatial_pose(baseline, "A::1", "A::2")
    fingerprint = v5._layout_fingerprint(swapped)
    captured = {}

    monkeypatch.setattr(
        candidate_preview.v5,
        "optimize_physical_layout",
        lambda **kwargs: {
            "physical_layout_optimizer": {
                "candidates": [
                    {
                        "label": "swap::A::1<->A::2",
                        "layout_fingerprint": fingerprint,
                        "production_authority": False,
                        "objective": {"hard_violation_count": 0},
                    }
                ]
            }
        },
    )
    monkeypatch.setattr(
        candidate_preview,
        "layout_architecture_report",
        lambda candidate_layout, store_dna: {"valid": True, "blockers": []},
    )

    def fake_optimizer(**kwargs):
        captured["layout"] = deepcopy(kwargs["layout"])
        return optimizer_result()

    monkeypatch.setattr(
        candidate_preview.allocation_v4,
        "optimize_production_plan",
        fake_optimizer,
    )

    result = candidate_preview.preview_physical_layout_candidate(
        products=[{"sku": "SKU"}],
        layout=baseline,
        store_dna={"architecture": {"schema_version": 1}},
        orders=[{"skus": ["SKU"]}],
        layout_fingerprint=fingerprint,
    )

    assert result["available"] is True
    assert result["preview_only"] is True
    assert result["layout_fingerprint"] == fingerprint
    assert v5._layout_fingerprint(captured["layout"]) == fingerprint
    assert result["physical_layout"] == captured["layout"]
    assert result["production_authority"] is False
    assert result["execution_authority"] is False
    assert result["physical_relocation_authority"] is False
    assert result["installation_approved"] is False
    assert result["capex_approved"] is False
    assert result["global_optimum_claim"] is False


def test_unknown_or_authoritative_candidate_cannot_be_replayed(monkeypatch) -> None:
    fingerprint = "a" * 64
    monkeypatch.setattr(
        candidate_preview.v5,
        "optimize_physical_layout",
        lambda **kwargs: {
            "physical_layout_optimizer": {
                "candidates": [
                    {
                        "label": "baseline",
                        "layout_fingerprint": fingerprint,
                        "production_authority": True,
                        "objective": {"hard_violation_count": 0},
                    }
                ]
            }
        },
    )

    result = candidate_preview.preview_physical_layout_candidate(
        products=[],
        layout=layout(),
        store_dna={},
        orders=[],
        layout_fingerprint=fingerprint,
    )
    assert result["available"] is False
    assert result["reason"] == "layout_fingerprint_not_in_recomputed_v5_search"
