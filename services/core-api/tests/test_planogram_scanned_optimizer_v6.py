from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

import app.modules.planogram.scanned_optimizer_adapter as scanned_adapter
import app.modules.planogram.store_scan_fixture_router as fixture_router
from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.store_scan import normalize_store_scan
from app.modules.planogram.store_scan_binding_schemas import (
    PlanogramStoreScanOptimizePreviewRequest,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="scanned-v6-test-user",
        tenant_id=TENANT,
        roles=("operator",),
        permissions=("action:planogram:create",),
        auth_mode="test",
    )


def scan() -> dict[str, object]:
    return {
        "store_code": "TEST-STORE",
        "provider": "apple_roomplan",
        "source_ref": "scan-session:v6-001",
        "floor_width_m": 12,
        "floor_depth_m": 9,
        "elements": [
            {
                "element_id": "fixture-1",
                "element_type": "fixture",
                "x_m": 2,
                "y_m": 2,
                "width_m": 1.2,
                "depth_m": 0.6,
                "rotation_deg": 17,
                "confidence": 0.95,
            },
        ],
    }


def request() -> PlanogramStoreScanOptimizePreviewRequest:
    fingerprint = normalize_store_scan(scan())["scan_fingerprint"]
    return PlanogramStoreScanOptimizePreviewRequest(
        scan=scan(),
        expected_scan_fingerprint=fingerprint,
        classifications=[],
        operational_elements=[
            {
                "element_id": "picker-entry",
                "element_type": "picker_entry",
                "center_x_m": 0.8,
                "center_y_m": 0.8,
                "width_m": 0.4,
                "depth_m": 0.4,
            },
            {
                "element_id": "inbound",
                "element_type": "inbound",
                "center_x_m": 1,
                "center_y_m": 7,
                "width_m": 1.5,
                "depth_m": 1,
            },
            {
                "element_id": "dispatch",
                "element_type": "dispatch",
                "center_x_m": 10,
                "center_y_m": 1,
                "width_m": 1.5,
                "depth_m": 1,
            },
        ],
        fixture_bindings=[
            {
                "scan_fixture_element_id": "fixture-1",
                "fixture_id": "GONDOLA-001",
                "aisle_id": "A01",
                "side": "L",
                "position": 1,
                "fixture_type": "steel_rack",
                "storage_type": "AMBIENT",
                "shelf_count": 2,
                "fixture_width_cm": 120,
                "fixture_height_cm": 160,
                "fixture_depth_cm": 60,
                "shelf_width_cm": 110,
                "shelf_height_cm": 60,
                "shelf_depth_cm": 50,
                "shelf_max_weight_kg": 40,
                "shelf_zone_types": ["lower", "eye"],
                "source_ref": "fixture-master://GONDOLA-001/v1",
                "attested": True,
            }
        ],
        products=[
            {
                "sku": "SKU-1",
                "storage_type": "AMBIENT",
                "width_cm": 40,
                "height_cm": 30,
                "depth_cm": 20,
                "weight_g": 500,
                "weekly_sales": 100,
            }
        ],
        order_baskets=[{"skus": ["SKU-1"]}],
        mode="HYBRID",
    )


def test_scanned_v6_route_is_mounted() -> None:
    assert "/v1/planogram/store-scan/optimize-preview" in app.openapi()["paths"]


def test_scanned_v6_schema_rejects_client_layout_store_dna_or_authority() -> None:
    raw = request().model_dump(mode="python")
    for field, value in (
        ("layout", {"aisles": []}),
        ("store_dna", {"architecture": {}}),
        ("selected_planogram", {"aisles": []}),
        ("production_authority", True),
        ("installation_approved", True),
        ("global_optimum_claim", True),
    ):
        with pytest.raises(ValidationError):
            PlanogramStoreScanOptimizePreviewRequest(**{**raw, field: value})


@pytest.mark.asyncio
async def test_scanned_v6_router_passes_only_recomputed_scan_binding_and_baskets(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_preview(**kwargs):
        captured.update(kwargs)
        return {
            "available": True,
            "preview_only": True,
            "production_authority": False,
            "store_dna_authority": False,
            "physical_layout_authority": False,
            "installation_approved": False,
            "relocation_execution_allowed": False,
            "capex_approved": False,
            "global_optimum_claim": False,
            "field_evidence": False,
            "scanned_layout": {"layout_draft_ready": True},
            "optimizer": {"allowed": True, "production_authority": False},
        }

    monkeypatch.setattr(
        fixture_router,
        "generate_scanned_store_optimizer_preview",
        fake_preview,
    )
    payload = request()
    response = await fixture_router.post_store_scan_optimize_preview(
        payload,
        principal(),
        24,
    )
    assert captured["orders"] == [{"skus": ["SKU-1"]}]
    assert captured["products"][0]["sku"] == "SKU-1"
    assert captured["uncertainty_resolutions"] == []
    assert "layout" not in captured
    assert "store_dna" not in captured
    assert response["preview_only"] is True
    assert response["input_authority"] == (
        "fingerprint_bound_scanned_v2_optimizer_unattested"
    )
    assert response["production_release_allowed"] is False
    assert response["installation_approval_allowed"] is False
    assert response["relocation_execution_allowed"] is False
    assert response["capex_approval_allowed"] is False
    assert response["global_optimum_claim"] is False
    assert response["field_evidence"] is False


def test_scanned_v6_adapter_propagates_uncertainty_resolution_to_layout(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        scanned_adapter,
        "build_scanned_fixture_layout_preview",
        lambda **kwargs: captured.update(kwargs)
        or {
            "available": False,
            "layout_draft_ready": False,
        },
    )
    scanned_adapter.generate_scanned_store_optimizer_preview(
        scan_payload={},
        expected_scan_fingerprint="a" * 64,
        classifications=[],
        operational_elements=[],
        fixture_bindings=[],
        products=[],
        orders=[],
        uncertainty_resolutions=[
            {"element_id": "uncertain-1", "decision": "reject"}
        ],
    )
    assert captured["uncertainty_resolutions"] == [
        {"element_id": "uncertain-1", "decision": "reject"}
    ]


def test_scanned_v6_adapter_rejects_optimizer_authority_leak(monkeypatch) -> None:
    monkeypatch.setattr(
        scanned_adapter,
        "build_scanned_fixture_layout_preview",
        lambda **_: {
            "available": True,
            "layout_draft_ready": True,
            "physical_layout_preview": {"aisles": []},
            "reviewed_store_dna_v2_preview": {"architecture": {}},
        },
    )
    monkeypatch.setattr(
        scanned_adapter,
        "_load_scanned_optimizer",
        lambda: SimpleNamespace(
            optimize_scanned_store=lambda **_: {
                "allowed": True,
                "production_authority": True,
                "store_dna_authority": False,
                "installation_approved": False,
                "relocation_execution_allowed": False,
                "capex_approved": False,
                "global_optimum_claim": False,
                "field_evidence": False,
            }
        ),
    )
    with pytest.raises(PlanogramEngineUnavailable, match="production_authority"):
        scanned_adapter.generate_scanned_store_optimizer_preview(
            scan_payload={},
            expected_scan_fingerprint="a" * 64,
            classifications=[],
            operational_elements=[],
            fixture_bindings=[],
            products=[],
            orders=[],
        )
