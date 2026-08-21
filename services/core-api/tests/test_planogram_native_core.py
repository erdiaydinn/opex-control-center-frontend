from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.engine_adapter import engine_status
from app.modules.planogram.router import get_planogram_readiness, post_planogram_preview
from app.modules.planogram.schemas import PlanogramPreviewRequest

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="planogram-test-user",
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


def preview_request(*, dimensions: bool = True) -> PlanogramPreviewRequest:
    return PlanogramPreviewRequest(
        products=[product(dimensions=dimensions)],
        layout=layout(),
        store_dna=store_dna(),
        mode="HYBRID",
    )


def test_canonical_app_registers_native_planogram_routes() -> None:
    paths = set(app.openapi()["paths"])
    required = {
        "/v1/planogram/readiness",
        "/v1/planogram/preview",
        "/v1/planogram/store-dna/workspace",
        "/v1/planogram/store-dna/bootstrap",
        "/v1/planogram/store-dna/{version_id}",
        "/v1/planogram/store-dna/{version_id}/submit",
        "/v1/planogram/store-dna/{version_id}/approve",
        "/v1/planogram/store-dna/{version_id}/reject",
        "/v1/planogram/store-dna/{version_id}/revise",
        "/v1/planogram/store-dna/{store_code}/readiness",
    }
    assert required <= paths


def test_adapter_binds_reviewed_library_contract() -> None:
    status = engine_status()
    assert status["available"] is True
    assert status["contract"] == "physical-truth-gated-deterministic-v1"
    assert status["foundation"] == "deterministic-best-fit-v4.2"
    assert status["legacy_bridge_enabled"] is False
    assert status["production_ai_dimensions_allowed"] is False
    assert status["source_modules"] == {
        "engine": "engine.py",
        "physical_truth": "physical_truth.py",
        "physical_engine": "physical_engine.py",
    }


@pytest.mark.asyncio
async def test_readiness_exposes_store_dna_lifecycle_without_claiming_full_truth() -> None:
    response = await get_planogram_readiness(principal())
    assert response["tenant_id"] == str(TENANT)
    assert response["production_ready"] is False
    assert response["publishable"] is False
    assert response["solver_optimizer_allowed"] is False
    assert (
        response["authority_state"]
        == "server_store_dna_lifecycle_available_physical_truth_incomplete"
    )
    assert response["physical_truth"]["server_attested"] is False


@pytest.mark.asyncio
async def test_missing_dimensions_preview_stays_fail_closed() -> None:
    response = await post_planogram_preview(preview_request(dimensions=False), principal())
    assert response["preview_only"] is True
    assert response["production_release_allowed"] is False
    assert response["input_authority"] == "request_supplied_unattested"
    result = response["engine_result"]
    assert result["production_ready"] is False
    assert result["solver_optimizer_allowed"] is False
    assert result["unplaced"][0]["reason"] == "approved_dimensions_missing"


@pytest.mark.asyncio
async def test_truth_shaped_preview_still_cannot_become_release_authority() -> None:
    response = await post_planogram_preview(preview_request(), principal())
    result = response["engine_result"]
    assert result["solver_optimizer_allowed"] is True
    assert result["physical_truth"]["blockers"] == []
    assert result["summary"]["placed"] == 1
    assert response["preview_only"] is True
    assert response["production_release_allowed"] is False
    assert response["input_authority"] == "request_supplied_unattested"


def test_preview_contract_caps_request_product_count() -> None:
    with pytest.raises(ValidationError):
        PlanogramPreviewRequest(
            products=[product()] * 5001,
            layout=layout(),
            store_dna=store_dna(),
        )
