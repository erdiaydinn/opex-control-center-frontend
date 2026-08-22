from __future__ import annotations

from uuid import UUID

import pytest

from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.engine_adapter import engine_status
from app.modules.planogram.optimizer_router import post_planogram_optimize_preview
from app.modules.planogram.schemas import PlanogramPreviewRequest

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="optimizer-test-user",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=("module:planogram:view", "action:planogram:create"),
        auth_mode="development",
    )


def product(*, dimensions: bool = True) -> dict[str, object]:
    row: dict[str, object] = {
        "sku": "SNACK",
        "product_name": "Ambient Snack",
        "brand": "Test",
        "category_l1": "Snacks",
        "category_l2": "Snacks",
        "storage_type": "RAF",
        "weight_kg": 0.5,
        "sales_qty_7d": 20,
        "image_url": "https://example.test/snack.jpg",
    }
    if dimensions:
        row.update({"width_cm": 8, "height_cm": 20, "depth_cm": 8})
    return row


def layout() -> dict[str, object]:
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
                    },
                    {
                        "module_id": 2,
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
                                "products": [],
                            }
                        ],
                    },
                ],
            }
        ],
    }


def store_dna() -> dict[str, object]:
    return {
        "source": "user_approved_store_dna",
        "store_code": "TEST",
        "picker_aisle_width_m": 1.2,
        "aisle_module_config": [
            {
                "aisle_id": "A",
                "left_modules": [{"module_id": 1, "side": "L", "shelf_count": 1}],
                "right_modules": [{"module_id": 2, "side": "R", "shelf_count": 1}],
            }
        ],
    }


def request(*, dimensions: bool = True) -> PlanogramPreviewRequest:
    return PlanogramPreviewRequest(
        products=[product(dimensions=dimensions)],
        layout=layout(),
        store_dna=store_dna(),
        mode="HYBRID",
    )


def test_optimizer_route_is_part_of_canonical_core_contract() -> None:
    assert "/v1/planogram/optimize-preview" in app.openapi()["paths"]


def test_engine_status_advertises_basket_aware_v3_without_production_authority() -> None:
    status = engine_status()
    assert status["architecture_contract"] == "store-architecture-v1"
    assert status["optimizer"] == {
        "available": True,
        "contract": "physical-plan-optimizer-v3-picker-tour",
        "fallback_contract": "physical-plan-optimizer-v2",
        "production_authority": False,
        "route_objective": "measured-basket-picker-tour-v1",
        "requires_observed_baskets": True,
    }
    # Existing foundation identity remains stable.
    assert status["contract"] == "physical-truth-gated-deterministic-v1"
    assert status["foundation"] == "deterministic-best-fit-v4.2"


@pytest.mark.asyncio
async def test_truth_shaped_optimizer_request_is_still_unattested_preview() -> None:
    response = await post_planogram_optimize_preview(request(), principal())
    assert response["tenant_id"] == str(TENANT)
    assert response["preview_only"] is True
    assert response["input_authority"] == "request_supplied_unattested"
    assert response["basket_authority"] == "not_supplied"
    assert response["observed_basket_input_count"] == 0
    assert response["production_release_allowed"] is False

    result = response["optimizer_result"]
    # V3 deliberately delegates to V2 when no observed/test baskets exist.
    assert result["optimizer"]["optimizer_version"] == "physical-plan-optimizer-v2"
    assert result["optimizer"]["allowed"] is True
    assert result["optimizer"]["candidate_count"] == 8
    assert result["optimizer"]["baseline_preserved"] is True
    assert result["optimizer"]["route_objective"]["basis"] == "legacy_rank_v1"
    assert result["picker_tour_optimizer"]["optimizer_version"] == (
        "physical-plan-optimizer-v3-picker-tour"
    )
    assert result["picker_tour_optimizer"]["effective"] is False
    assert result["picker_tour_optimizer"]["reason"] == "order_baskets_missing"
    assert result["solver_optimizer_allowed"] is True


@pytest.mark.asyncio
async def test_missing_dimensions_cannot_be_optimized_around() -> None:
    response = await post_planogram_optimize_preview(
        request(dimensions=False),
        principal(),
    )
    assert response["production_release_allowed"] is False
    result = response["optimizer_result"]
    assert result["solver_optimizer_allowed"] is False
    assert result["optimizer"]["allowed"] is False
    assert result["optimizer"]["blocked_by_physical_truth"] is True
    assert result["optimizer"]["candidate_count"] == 1
    assert result["optimizer"]["selected_strategy"] == "baseline"
    assert result["picker_tour_optimizer"]["effective"] is False
