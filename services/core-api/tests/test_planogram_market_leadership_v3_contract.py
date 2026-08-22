from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.modules.planogram.blind_benchmark_adapter as blind_adapter
import app.modules.planogram.cad_adapter as cad_adapter
import app.modules.planogram.engine_adapter as engine_adapter
import app.modules.planogram.optimizer_router as optimizer_router
from app.core.security import Principal
from app.modules.planogram.benchmark_schemas import PlanogramBlindBenchmarkRequest
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


def blind_request(*, schema_version: int = 1) -> PlanogramBlindBenchmarkRequest:
    plan = {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": 1,
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "products": [{"sku": "SKU-1"}],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    return PlanogramBlindBenchmarkRequest(
        products=[
            {
                "sku": "SKU-1",
                "product_name": "Product 1",
                "width_cm": 10,
                "height_cm": 20,
                "depth_cm": 8,
            }
        ],
        layout={"store_code": "TEST", "aisles": [{"aisle_id": "A", "modules": []}]},
        store_dna={
            "store_code": "TEST",
            "architecture": {
                "schema_version": schema_version,
                "coordinate_system": (
                    "cartesian_m"
                    if schema_version == 1
                    else "cartesian_m_centered_rect"
                ),
            },
        },
        order_baskets=[{"skus": [" sku-1 "]}],
        candidate_a={"planogram": plan},
        candidate_b={"planogram": plan},
    )


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


def capacity_safe_planogram() -> dict:
    """Minimal complete physical evidence for V3/V4 benchmark contract tests."""
    return {
        "aisles": [
            {
                "aisle_id": "A1",
                "modules": [
                    {
                        "module_id": "M1",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 40,
                                "shelf_depth_cm": 40,
                                "max_weight_kg": 100,
                                "products": [
                                    {
                                        "sku": "SKU-1",
                                        "facing_count": 1,
                                        "width_cm": 10,
                                        "height_cm": 20,
                                        "depth_cm": 8,
                                        "weight_kg": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def v2_cad_inputs() -> tuple[dict, dict, dict]:
    layout = {
        "store_code": "TEST",
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": "1",
                        "x_m": 2.0,
                        "y_m": 2.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "rotation_deg": 17.0,
                    }
                ],
            }
        ],
    }
    store_dna = {
        "store_code": "TEST",
        "architecture": {
            "schema_version": 2,
            "coordinate_system": "cartesian_m_centered_rect",
            "source": "manual_survey",
            "source_ref": "survey://TEST/v2",
            "floor_width_m": 10.0,
            "floor_depth_m": 8.0,
            "elements": [
                {
                    "element_id": "ENTRY",
                    "element_type": "picker_entry",
                    "x_m": 0.2,
                    "y_m": 0.2,
                    "width_m": 0.5,
                    "depth_m": 0.5,
                    "rotation_deg": 0.0,
                },
                {
                    "element_id": "WALL-17",
                    "element_type": "wall",
                    "x_m": 6.0,
                    "y_m": 5.0,
                    "width_m": 2.0,
                    "depth_m": 0.1,
                    "rotation_deg": 17.0,
                },
            ],
        },
    }
    optimizer_result = {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": "1",
                            "shelves": [
                                {
                                    "shelf_no": 1,
                                    "products": [{"sku": "SKU-1"}],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "architecture_route_objective_v2": {
            "contract": "architecture-polygon-astar-v2",
            "preview_only": True,
            "available": True,
            "distance_m": 4.5,
            "path_m": [[0.45, 0.45], [1.0, 1.0], [2.5, 2.25]],
        },
    }
    return optimizer_result, layout, store_dna


def test_order_basket_contract_normalizes_skus_and_excludes_order_identity() -> None:
    request = base_request(order_baskets=[{"skus": [" sku-1 ", "SKU-2"]}])

    assert request.order_baskets[0].skus == ["SKU-1", "SKU-2"]
    assert "order_id" not in request.order_baskets[0].model_dump()


def test_blind_benchmark_schema_forbids_candidate_identity_fields() -> None:
    payload = blind_request().model_dump(mode="python")
    payload["candidate_a"]["identity"] = "expert"

    with pytest.raises(ValidationError):
        PlanogramBlindBenchmarkRequest(**payload)


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
            "planogram": capacity_safe_planogram(),
            "picker_tour_optimizer": {
                "optimizer_version": "physical-plan-optimizer-v3-picker-tour",
                "allowed": True,
                "effective": True,
                "selected_strategy": "canonical",
                "candidate_count": 8,
                "selected_objective": v3_objective,
                "selected_tour": {"p95_m": 30.0, "average_m": 24.0},
            },
        }

    def market_optimize(*args, **kwargs):
        assert kwargs["max_candidates"] == 24
        return {
            "planogram": capacity_safe_planogram(),
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
            },
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


def test_blind_adapter_dispatches_v1_and_v2_without_claim_authority(monkeypatch) -> None:
    calls = []

    def fake_result(version):
        def run(**kwargs):
            calls.append((version, kwargs["orders"]))
            return {
                "benchmark_version": version,
                "available": True,
                "production_evidence": False,
                "market_leadership_proven": False,
                "promotion_allowed": False,
            }

        return run

    monkeypatch.setattr(
        blind_adapter,
        "_load_v1_benchmark",
        lambda: SimpleNamespace(benchmark_candidates=fake_result("v1")),
    )
    monkeypatch.setattr(
        blind_adapter,
        "_load_v2_benchmark",
        lambda: SimpleNamespace(benchmark_candidates_v2=fake_result("v2")),
    )

    for schema_version in (1, 2):
        request = blind_request(schema_version=schema_version)
        result = blind_adapter.generate_blind_benchmark_preview(
            products=request.products,
            layout=request.layout,
            store_dna=request.store_dna,
            orders=[basket.model_dump(mode="python") for basket in request.order_baskets],
            candidate_a=request.candidate_a.model_dump(mode="python"),
            candidate_b=request.candidate_b.model_dump(mode="python"),
        )
        assert result["architecture_schema_version"] == schema_version
        assert result["production_authority"] is False
        assert result["production_evidence"] is False
        assert result["market_leadership_proven"] is False
        assert result["promotion_allowed"] is False

    assert calls == [("v1", [{"skus": ["SKU-1"]}]), ("v2", [{"skus": ["SKU-1"]}])]


@pytest.mark.asyncio
async def test_blind_router_never_receives_expert_or_ai_identity(monkeypatch) -> None:
    captured = {}

    def fake_blind(**kwargs):
        captured.update(kwargs)
        return {
            "benchmark_version": "test",
            "available": True,
            "winner_on_repository_objective": "A",
            "production_authority": False,
            "production_evidence": False,
            "market_leadership_proven": False,
            "promotion_allowed": False,
        }

    monkeypatch.setattr(
        optimizer_router,
        "generate_blind_benchmark_preview",
        fake_blind,
    )
    response = await optimizer_router.post_planogram_blind_benchmark_preview(
        blind_request(schema_version=2),
        principal(),
    )

    assert captured["orders"] == [{"skus": ["SKU-1"]}]
    assert set(captured) == {
        "products",
        "layout",
        "store_dna",
        "orders",
        "candidate_a",
        "candidate_b",
    }
    assert response["blind"] is True
    assert response["candidate_identity_fields_accepted"] is False
    assert response["production_release_allowed"] is False
    assert response["market_leadership_claim_allowed"] is False
    assert response["benchmark"]["market_leadership_proven"] is False


def test_measured_v2_cad_adapter_emits_svg_and_dxf_without_field_authority() -> None:
    optimizer_result, layout, store_dna = v2_cad_inputs()
    cad_adapter._load_cad_exporter.cache_clear()
    cad_adapter._load_dxf_exporter.cache_clear()

    drawing = cad_adapter.generate_cad_preview_document(
        optimizer_result=optimizer_result,
        layout=layout,
        store_dna=store_dna,
        include_dxf=True,
    )

    assert drawing["available"] is True
    assert drawing["preview_only"] is True
    assert drawing["production_authority"] is False
    assert drawing["production_evidence"] is False
    assert drawing["installation_approved"] is False
    assert drawing["spatial_contract"] == "store-architecture-v2-oriented-polygons"
    assert drawing["architecture_element_count"] == 2
    assert drawing["fixture_count"] == 1
    assert drawing["route_count"] == 1
    assert "EAY_ARCH_WALL" in drawing["layers"]
    assert "EAY_FIXTURE" in drawing["layers"]
    assert 'id="EAY_DIMENSION"' in drawing["svg"]
    assert 'data-id="WALL-17"' in drawing["svg"]
    assert drawing["dxf_included"] is True
    assert drawing["dxf_contract"] == "planogram-measured-dxf-preview-v1"
    assert "SECTION" in drawing["dxf"]
    assert "EAY_FIXTURE" in drawing["dxf"]
    assert "EAY_ARCH_WALL" in drawing["dxf"]


@pytest.mark.asyncio
async def test_cad_router_never_grants_installation_or_release_authority(monkeypatch) -> None:
    optimized, _, _ = v2_cad_inputs()
    captured = {}

    def fake_optimizer(**kwargs):
        return {
            **optimized,
            "picker_tour_optimizer": {
                "optimizer_version": "physical-plan-optimizer-v3-picker-tour",
                "selected_strategy": "test",
            },
        }

    def fake_cad(**kwargs):
        captured.update(kwargs)
        return {
            "contract": "planogram-measured-cad-preview-v1",
            "available": True,
            "preview_only": True,
            "production_authority": False,
            "installation_approved": False,
            "svg": "<svg/>",
            "dxf": None,
        }

    monkeypatch.setattr(optimizer_router, "generate_optimized_preview", fake_optimizer)
    monkeypatch.setattr(optimizer_router, "generate_cad_preview_document", fake_cad)
    response = await optimizer_router.post_planogram_cad_preview(
        base_request(order_baskets=[{"skus": ["SKU-1"]}]),
        principal(),
        False,
    )

    assert captured["include_dxf"] is False
    assert response["production_release_allowed"] is False
    assert response["installation_approval_allowed"] is False
    assert response["drawing"]["production_authority"] is False
