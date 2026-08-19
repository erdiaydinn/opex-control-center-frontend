from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

import app.modules.planogram.engine_adapter as engine_adapter
import app.modules.planogram.optimizer_router as optimizer_router
from app.core.security import Principal
from app.modules.planogram.schemas import PlanogramPreviewRequest

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OBJECTIVE_ORDER = (
    "hard_violation_count",
    "weighted_unplaced_sales",
    "unplaced_sku_count",
    "tour_unsimulated_order_count",
    "tour_p95_m",
    "tour_average_m",
    "coverage_shortfall",
    "brand_fragmentation",
    "capacity_pressure",
)


def principal() -> Principal:
    return Principal(
        subject="market-leadership-test-user",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=("module:planogram:view", "action:planogram:create"),
        auth_mode="development",
    )


def base_request(**overrides) -> PlanogramPreviewRequest:
    payload = {
        "products": [
            {
                "sku": "SKU-1",
                "product_name": "Product 1",
                "brand": "Brand",
                "category_l1": "Ambient",
                "category_l2": "Ambient",
                "storage_type": "RAF",
                "sales_qty_7d": 10,
                "width_cm": 10,
                "height_cm": 20,
                "depth_cm": 8,
                "image_url": "https://example.test/sku-1.jpg",
            }
        ],
        "layout": {"store_code": "TEST", "aisles": []},
        "store_dna": {"store_code": "TEST"},
        "mode": "HYBRID",
    }
    payload.update(overrides)
    return PlanogramPreviewRequest(**payload)


def objective(*, p95: float, average: float) -> dict[str, float | int]:
    return {
        "hard_violation_count": 0,
        "weighted_unplaced_sales": 0.0,
        "unplaced_sku_count": 0,
        "tour_unsimulated_order_count": 0,
        "tour_p95_m": p95,
        "tour_average_m": average,
        "coverage_shortfall": 0.0,
        "brand_fragmentation": 0.0,
        "capacity_pressure": 0.0,
    }


def objective_key(row: dict[str, float | int]) -> tuple[float, ...]:
    return tuple(float(row[name]) for name in OBJECTIVE_ORDER)


def test_order_basket_contract_normalizes_skus_and_excludes_order_identity() -> None:
    request = base_request(order_baskets=[{"skus": [" sku-1 ", "SKU-2"]}])

    assert request.order_baskets[0].skus == ["SKU-1", "SKU-2"]
    assert "order_id" not in request.order_baskets[0].model_dump()


@pytest.mark.asyncio
async def test_router_passes_only_anonymized_baskets_to_v3(monkeypatch) -> None:
    captured = {}

    def fake_optimizer(**kwargs):
        captured.update(kwargs)
        return {
            "optimizer": {"optimizer_version": "physical-plan-optimizer-v2"},
            "picker_tour_optimizer": {
                "optimizer_version": "physical-plan-optimizer-v3-picker-tour",
                "effective": True,
            },
        }

    monkeypatch.setattr(optimizer_router, "generate_optimized_preview", fake_optimizer)
    response = await optimizer_router.post_planogram_optimize_preview(
        base_request(order_baskets=[{"skus": ["sku-1", "sku-1"]}]),
        principal(),
    )

    assert captured["orders"] == [{"skus": ["SKU-1", "SKU-1"]}]
    assert response["basket_authority"] == "request_supplied_observed_or_test_unattested"
    assert response["observed_basket_input_count"] == 1
    assert response["production_release_allowed"] is False


def test_v3_v4_adapter_compares_same_evidence_without_promotion(monkeypatch) -> None:
    v3_objective = objective(p95=30.0, average=24.0)
    v4_objective = objective(p95=22.0, average=18.0)

    def canonical_optimize(*args, **kwargs):
        return {
            "picker_tour_optimizer": {
                "optimizer_version": "physical-plan-optimizer-v3-picker-tour",
                "allowed": True,
                "effective": True,
                "selected_strategy": "canonical",
                "candidate_count": 8,
                "selected_objective": v3_objective,
                "selected_tour": {"p95_m": 30.0, "average_m": 24.0},
            }
        }

    def market_optimize(*args, **kwargs):
        assert kwargs["max_candidates"] == 24
        return {
            "market_search_optimizer": {
                "optimizer_version": "physical-plan-optimizer-v4-bounded-search",
                "allowed": True,
                "effective": True,
                "selected_strategy": "search::better",
                "candidate_count": 24,
                "search_budget": 24,
                "pareto_frontier_count": 4,
                "selected_objective": v4_objective,
                "selected_tour": {"p95_m": 22.0, "average_m": 18.0},
                "alternatives": [{"strategy": "search::balanced"}],
            }
        }

    monkeypatch.setattr(
        engine_adapter,
        "_load_optimizer",
        lambda: SimpleNamespace(
            optimize_production_plan=canonical_optimize,
            objective_key=objective_key,
        ),
    )
    monkeypatch.setattr(
        engine_adapter,
        "_load_market_search_optimizer",
        lambda: SimpleNamespace(optimize_production_plan=market_optimize),
    )

    result = engine_adapter.generate_market_leadership_benchmark_preview(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        mode="HYBRID",
        orders=[{"skus": ["SKU-1"]}],
    )

    assert result["winner_on_repository_objective"] == "experimental_v4"
    assert result["objective_delta_experimental_minus_canonical"]["tour_p95_m"] == -8.0
    assert result["experimental_v4"]["candidate_count"] == 24
    assert result["promotion_allowed"] is False
    assert result["production_authority"] is False
    assert result["production_evidence"] is False
    assert "blind_expert_benchmark_required" in result["promotion_blockers"]


@pytest.mark.asyncio
async def test_v4_benchmark_router_requires_baskets() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await optimizer_router.post_planogram_market_benchmark_preview(
            base_request(order_baskets=[]),
            principal(),
            24,
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_v4_benchmark_router_preserves_truth_boundary(monkeypatch) -> None:
    captured = {}

    def fake_benchmark(**kwargs):
        captured.update(kwargs)
        return {
            "benchmark_contract": "planogram-v3-v4-same-evidence-benchmark-v1",
            "preview_only": True,
            "promotion_allowed": False,
        }

    monkeypatch.setattr(
        optimizer_router,
        "generate_market_leadership_benchmark_preview",
        fake_benchmark,
    )
    response = await optimizer_router.post_planogram_market_benchmark_preview(
        base_request(order_baskets=[{"skus": [" sku-1 "]}]),
        principal(),
        16,
    )

    assert captured["orders"] == [{"skus": ["SKU-1"]}]
    assert captured["max_candidates"] == 16
    assert response["observed_basket_input_count"] == 1
    assert response["production_release_allowed"] is False
    assert response["experimental_optimizer_production_authority"] is False
    assert response["benchmark"]["promotion_allowed"] is False
