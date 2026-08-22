from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.modules.planogram.scenario_adapter as scenario_adapter
import app.modules.planogram.scenario_router as scenario_router
from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.scenario_schemas import PlanogramPhysicalLayoutCandidatePreviewRequest

TENANT = UUID("11111111-1111-4111-8111-111111111111")
FINGERPRINT = "a" * 64


def principal() -> Principal:
    return Principal(
        subject="scenario-replay-test-user",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=("module:planogram:view", "action:planogram:create"),
        auth_mode="development",
    )


def request(*, baskets: bool = True) -> PlanogramPhysicalLayoutCandidatePreviewRequest:
    return PlanogramPhysicalLayoutCandidatePreviewRequest(
        products=[{"sku": "SKU-1"}],
        layout={"aisles": []},
        store_dna={"architecture": {"schema_version": 1}},
        mode="HYBRID",
        order_baskets=[{"skus": ["SKU-1"]}] if baskets else [],
        layout_fingerprint=FINGERPRINT,
    )


def safe_result() -> dict:
    return {
        "available": True,
        "preview_only": True,
        "layout_fingerprint": FINGERPRINT,
        "physical_layout": {"aisles": []},
        "optimizer_result": {"planogram": {"aisles": []}},
        "production_authority": False,
        "execution_authority": False,
        "physical_relocation_authority": False,
        "installation_approved": False,
        "capex_approved": False,
        "global_optimum_claim": False,
    }


def test_schema_rejects_extra_candidate_payload() -> None:
    payload = request().model_dump(mode="python")
    payload["candidate_layout"] = {"aisles": []}
    with pytest.raises(ValidationError):
        PlanogramPhysicalLayoutCandidatePreviewRequest(**payload)


def test_adapter_rejects_non_preview_authority(monkeypatch) -> None:
    unsafe = safe_result()
    unsafe["execution_authority"] = True
    monkeypatch.setattr(
        scenario_adapter,
        "_load_candidate_preview",
        lambda: SimpleNamespace(preview_physical_layout_candidate=lambda **kwargs: unsafe),
    )
    with pytest.raises(PlanogramEngineUnavailable):
        scenario_adapter.generate_physical_layout_candidate_preview(
            products=[],
            layout={},
            store_dna={},
            orders=[],
            layout_fingerprint=FINGERPRINT,
            mode="HYBRID",
        )


@pytest.mark.asyncio
async def test_router_requires_anonymized_baskets() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await scenario_router.post_planogram_physical_layout_candidate_preview(
            request(baskets=False), principal(), 16, 12
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_router_passes_fingerprint_only(monkeypatch) -> None:
    captured = {}

    def fake_preview(**kwargs):
        captured.update(kwargs)
        return safe_result()

    monkeypatch.setattr(scenario_router, "generate_physical_layout_candidate_preview", fake_preview)
    response = await scenario_router.post_planogram_physical_layout_candidate_preview(
        request(), principal(), 16, 12
    )
    assert captured["layout_fingerprint"] == FINGERPRINT
    assert captured["orders"] == [{"skus": ["SKU-1"]}]
    assert "candidate_layout" not in captured
    assert response["candidate_selection_authority"] == "server_recomputed_fingerprint_match_only"
    assert response["production_release_allowed"] is False


def test_runtime_openapi_mounts_candidate_replay_endpoint() -> None:
    assert "/v1/planogram/physical-layout-candidate-preview" in app.openapi()["paths"]
