from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.modules.planogram.economics_adapter as economics_adapter
import app.modules.planogram.economics_router as economics_router
from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.economics_schemas import (
    PlanogramPhysicalEconomicsPreviewRequest,
)
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="planogram-economics-reviewer",
        tenant_id=TENANT_ID,
        roles=("operator",),
        permissions=(
            "action:planogram:create",
            "action:planogram:approve",
        ),
        auth_mode="test",
    )


def assumptions() -> dict[str, object]:
    return {
        "currency": "EUR",
        "orders_per_day": {
            "low": 800,
            "base": 1000,
            "high": 1200,
            "source_ref": "ops://orders/day",
            "attested": True,
        },
        "operating_days_per_year": {
            "low": 340,
            "base": 350,
            "high": 360,
            "source_ref": "ops://calendar/year",
            "attested": True,
        },
        "effective_seconds_per_meter": {
            "low": 0.7,
            "base": 0.9,
            "high": 1.1,
            "source_ref": "study://picker-seconds-per-meter",
            "attested": True,
        },
        "loaded_labor_cost_per_hour": {
            "low": 8,
            "base": 10,
            "high": 12,
            "source_ref": "finance://loaded-labor-cost",
            "attested": True,
        },
        "capex_items": [
            {
                "label": "fixture relocation",
                "amount": 5000,
                "currency": "EUR",
                "source_ref": "quote://fixture-relocation",
                "attested": True,
            }
        ],
    }


def request(*, with_baskets: bool = True) -> PlanogramPhysicalEconomicsPreviewRequest:
    return PlanogramPhysicalEconomicsPreviewRequest(
        products=[{"sku": "SKU-1"}],
        layout={"store_code": "TEST", "aisles": []},
        store_dna={"store_code": "TEST"},
        order_baskets=[{"skus": ["SKU-1"]}] if with_baskets else [],
        economics=assumptions(),
    )


def _route_permissions(path: str) -> set[str]:
    route = next(row for row in economics_router.router.routes if row.path == path)
    required: set[str] = set()
    for dependency in route.dependant.dependencies:
        call = dependency.call
        if call is None:
            continue
        normalized = inspect.getclosurevars(call).nonlocals.get("normalized")
        if isinstance(normalized, str) and normalized:
            required.add(normalized)
    return required


def test_economics_route_is_mounted_and_requires_create_plus_approve() -> None:
    assert "/v1/planogram/physical-layout-economics-preview" in app.openapi()["paths"]
    assert _route_permissions("/v1/planogram/physical-layout-economics-preview") == {
        "action:planogram:create",
        "action:planogram:approve",
    }


def test_economics_request_rejects_client_authority_fields() -> None:
    payload = request().model_dump(mode="python")
    for field in (
        "finance_approved",
        "investment_decision_allowed",
        "production_authority",
        "capex_approved",
        "realized_savings_proven",
    ):
        with pytest.raises(ValidationError):
            PlanogramPhysicalEconomicsPreviewRequest(**{**payload, field: True})

    payload["economics"]["finance_approved"] = True
    with pytest.raises(ValidationError):
        PlanogramPhysicalEconomicsPreviewRequest(**payload)


def test_economics_ranges_must_be_ordered() -> None:
    payload = request().model_dump(mode="python")
    payload["economics"]["orders_per_day"] = {
        **payload["economics"]["orders_per_day"],
        "low": 1200,
        "base": 1000,
        "high": 800,
    }
    with pytest.raises(ValidationError):
        PlanogramPhysicalEconomicsPreviewRequest(**payload)


@pytest.mark.asyncio
async def test_economics_router_requires_anonymized_baskets() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await economics_router.post_planogram_physical_layout_economics_preview(
            request(with_baskets=False),
            principal(),
            principal(),
            16,
            12,
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_economics_router_never_grants_finance_or_investment_authority(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_economics(**kwargs):
        captured.update(kwargs)
        return {
            "preview_only": True,
            "production_authority": False,
            "physical_relocation_authority": False,
            "installation_approved": False,
            "capex_approved": False,
            "finance_approved": False,
            "investment_decision_allowed": False,
            "realized_savings_proven": False,
            "economics": {
                "available": True,
                "production_evidence": False,
                "finance_approved": False,
                "investment_decision_allowed": False,
            },
        }

    monkeypatch.setattr(
        economics_router,
        "generate_physical_layout_economics_preview",
        fake_economics,
    )
    response = await economics_router.post_planogram_physical_layout_economics_preview(
        request(),
        principal(),
        principal(),
        16,
        12,
    )

    assert captured["orders"] == [{"skus": ["SKU-1"]}]
    assert captured["assumptions"]["currency"] == "EUR"
    assert response["preview_only"] is True
    assert response["production_release_allowed"] is False
    assert response["physical_relocation_execution_allowed"] is False
    assert response["installation_approval_allowed"] is False
    assert response["capex_approval_allowed"] is False
    assert response["finance_approval_allowed"] is False
    assert response["investment_decision_allowed"] is False
    assert response["realized_savings_proven"] is False


def test_economics_adapter_rejects_authority_leak(monkeypatch) -> None:
    monkeypatch.setattr(
        economics_adapter,
        "generate_physical_layout_search_preview",
        lambda **_: {"physical_layout_optimizer": {"allowed": True}},
    )
    monkeypatch.setattr(
        economics_adapter,
        "_load_physical_economics",
        lambda: SimpleNamespace(
            evaluate_physical_layout_economics=lambda **_: {
                "available": True,
                "production_evidence": False,
                "finance_approved": True,
                "investment_decision_allowed": False,
            }
        ),
    )

    with pytest.raises(PlanogramEngineUnavailable, match="finance-approval boundary"):
        economics_adapter.generate_physical_layout_economics_preview(
            products=[{"sku": "SKU-1"}],
            layout={},
            store_dna={},
            orders=[{"skus": ["SKU-1"]}],
            mode="HYBRID",
            assumptions=assumptions(),
        )
