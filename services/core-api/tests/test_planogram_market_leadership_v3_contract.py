from __future__ import annotations

from uuid import UUID

import pytest

import app.modules.planogram.optimizer_router as optimizer_router
from app.core.security import Principal
from app.modules.planogram.schemas import PlanogramPreviewRequest

TENANT = UUID("11111111-1111-4111-8111-111111111111")


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
