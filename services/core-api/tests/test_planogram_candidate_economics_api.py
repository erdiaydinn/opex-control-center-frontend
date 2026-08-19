from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

import app.modules.planogram.economics_adapter as economics_adapter
import app.modules.planogram.economics_router as economics_router
from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.economics_schemas import (
    PlanogramPhysicalCandidateEconomicsPreviewRequest,
)
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable

TENANT = UUID("11111111-1111-4111-8111-111111111111")
FINGERPRINT = "a" * 64


def principal() -> Principal:
    return Principal(
        subject="candidate-economics-test-user",
        tenant_id=TENANT,
        roles=("operator",),
        permissions=("action:planogram:create", "action:planogram:approve"),
        auth_mode="test",
    )


def request() -> PlanogramPhysicalCandidateEconomicsPreviewRequest:
    range_row = {
        "low": 1,
        "base": 1,
        "high": 1,
        "source_ref": "src://evidence",
        "attested": True,
    }
    return PlanogramPhysicalCandidateEconomicsPreviewRequest(
        products=[{"sku": "SKU-1"}],
        layout={"aisles": []},
        store_dna={"store_code": "TEST"},
        order_baskets=[{"skus": ["SKU-1"]}],
        layout_fingerprint=FINGERPRINT,
        economics={
            "currency": "EUR",
            "orders_per_day": range_row,
            "operating_days_per_year": range_row,
            "effective_seconds_per_meter": range_row,
            "loaded_labor_cost_per_hour": range_row,
            "capex_items": [
                {
                    "label": "move",
                    "amount": 1,
                    "currency": "EUR",
                    "source_ref": "quote://move",
                    "attested": True,
                }
            ],
        },
    )


def route_permissions(path: str) -> set[str]:
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


def test_candidate_economics_route_is_mounted_with_dual_authority() -> None:
    path = "/v1/planogram/physical-layout-candidate-economics-preview"
    assert path in app.openapi()["paths"]
    assert route_permissions(path) == {
        "action:planogram:create",
        "action:planogram:approve",
    }


def test_candidate_economics_schema_rejects_client_route_or_authority() -> None:
    payload = request().model_dump(mode="python")
    for field, value in (
        ("route_saving_m", 999),
        ("candidate_layout", {"aisles": []}),
        ("finance_approved", True),
        ("realized_savings_proven", True),
    ):
        with pytest.raises(ValidationError):
            PlanogramPhysicalCandidateEconomicsPreviewRequest(**{**payload, field: value})


@pytest.mark.asyncio
async def test_router_passes_fingerprint_and_sourced_assumptions_only(monkeypatch) -> None:
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {
            "available": True,
            "preview_only": True,
            "layout_fingerprint": FINGERPRINT,
            "production_evidence": False,
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
        "generate_physical_layout_candidate_economics_preview",
        fake,
    )
    response = await economics_router.post_planogram_physical_layout_candidate_economics_preview(
        request(), principal(), principal(), 16, 12
    )
    assert captured["layout_fingerprint"] == FINGERPRINT
    assert captured["orders"] == [{"skus": ["SKU-1"]}]
    assert "route_saving_m" not in captured
    assert response["candidate_selection_authority"] == (
        "server_recomputed_fingerprint_match_only"
    )
    assert response["finance_approval_allowed"] is False
    assert response["realized_savings_proven"] is False


def test_adapter_rejects_candidate_finance_authority_leak(monkeypatch) -> None:
    monkeypatch.setattr(
        economics_adapter,
        "_load_candidate_economics",
        lambda: SimpleNamespace(
            evaluate_physical_layout_candidate_economics=lambda **kwargs: {
                "available": True,
                "production_evidence": False,
                "finance_approved": True,
                "investment_decision_allowed": False,
                "realized_savings_proven": False,
            }
        ),
    )
    with pytest.raises(PlanogramEngineUnavailable, match="finance-approval boundary"):
        economics_adapter.generate_physical_layout_candidate_economics_preview(
            products=[],
            layout={},
            store_dna={},
            orders=[],
            mode="HYBRID",
            layout_fingerprint=FINGERPRINT,
            assumptions={},
        )
