from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

import app.modules.planogram.optimizer_router as optimizer_router
import app.modules.planogram.physical_layout_adapter as layout_adapter
from app.core.security import Principal
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.schemas import PlanogramPreviewRequest

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="physical-layout-v5-test-user",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=("module:planogram:view", "action:planogram:create"),
        auth_mode="development",
    )


def request(*, baskets: bool = True) -> PlanogramPreviewRequest:
    return PlanogramPreviewRequest(
        products=[
            {
                "sku": "SKU-1",
                "product_name": "Product 1",
                "width_cm": 10,
                "height_cm": 20,
                "depth_cm": 8,
            }
        ],
        layout={
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": 1,
                            "x_m": 1.0,
                            "y_m": 1.0,
                            "width_m": 1.0,
                            "depth_m": 0.5,
                            "relocatable": True,
                        }
                    ],
                }
            ]
        },
        store_dna={
            "architecture": {
                "schema_version": 1,
                "coordinate_system": "cartesian_m",
            }
        },
        mode="HYBRID",
        order_baskets=[{"skus": [" sku-1 "]}] if baskets else [],
    )


def safe_result() -> dict:
    return {
        "physical_layout": {"aisles": []},
        "physical_layout_optimizer": {
            "optimizer_version": "physical-layout-optimizer-v5-relocation-search",
            "allowed": True,
            "effective": True,
            "production_authority": False,
            "physical_relocation_authority": False,
            "installation_approved": False,
            "selected_layout_label": "baseline",
        },
    }


def test_adapter_forces_all_execution_authority_false(monkeypatch) -> None:
    def optimize(**kwargs):
        assert kwargs["max_layout_candidates"] == 16
        assert kwargs["max_allocation_candidates"] == 12
        return safe_result()

    monkeypatch.setattr(
        layout_adapter,
        "_load_physical_layout_optimizer",
        lambda: SimpleNamespace(optimize_physical_layout=optimize),
    )

    result = layout_adapter.generate_physical_layout_search_preview(
        products=[{"sku": "SKU-1"}],
        layout={},
        store_dna={},
        orders=[{"skus": ["SKU-1"]}],
        mode="HYBRID",
    )

    assert result["production_authority"] is False
    assert result["physical_relocation_authority"] is False
    assert result["installation_approved"] is False
    assert result["capex_approved"] is False


def test_adapter_rejects_relocation_authority_leak(monkeypatch) -> None:
    unsafe = safe_result()
    unsafe["physical_layout_optimizer"]["physical_relocation_authority"] = True

    monkeypatch.setattr(
        layout_adapter,
        "_load_physical_layout_optimizer",
        lambda: SimpleNamespace(
            optimize_physical_layout=lambda **kwargs: unsafe
        ),
    )

    with pytest.raises(PlanogramEngineUnavailable):
        layout_adapter.generate_physical_layout_search_preview(
            products=[{"sku": "SKU-1"}],
            layout={},
            store_dna={},
            orders=[{"skus": ["SKU-1"]}],
            mode="HYBRID",
        )


@pytest.mark.asyncio
async def test_router_requires_anonymized_baskets() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await optimizer_router.post_planogram_physical_layout_search_preview(
            request(baskets=False),
            principal(),
            16,
            12,
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_router_is_proposal_only_and_passes_bounded_budgets(monkeypatch) -> None:
    captured = {}

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {
            **safe_result(),
            "production_authority": False,
            "physical_relocation_authority": False,
            "installation_approved": False,
            "capex_approved": False,
        }

    monkeypatch.setattr(
        optimizer_router,
        "generate_physical_layout_search_preview",
        fake_search,
    )
    response = await optimizer_router.post_planogram_physical_layout_search_preview(
        request(baskets=True),
        principal(),
        7,
        10,
    )

    assert captured["orders"] == [{"skus": ["SKU-1"]}]
    assert captured["max_layout_candidates"] == 7
    assert captured["max_allocation_candidates"] == 10
    assert response["relocation_policy_authority"] == "request_supplied_unattested"
    assert response["production_release_allowed"] is False
    assert response["physical_relocation_execution_allowed"] is False
    assert response["installation_approval_allowed"] is False
    assert response["capex_approval_allowed"] is False
    assert response["result"]["physical_relocation_authority"] is False
