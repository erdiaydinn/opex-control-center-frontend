from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from . import replan_router
from . import router as workforce_router
from .replan_authority import (
    CostAssumption,
    KpiSensitivity,
    ReplanBaseline,
    ReplanScenarioRequest,
    ScenarioShock,
    build_replan_scenario,
)


def _scenario():
    baseline = ReplanBaseline(
        demand_snapshot_fingerprint="a" * 64,
        capacity_snapshot_fingerprint="b" * 64,
        dpi_snapshot_fingerprint="c" * 64,
        optimizer_proposal_fingerprint="d" * 64,
        required_man_hours=Decimal("10"),
        effective_man_hours=Decimal("10.7"),
        demand_pressure_index=Decimal("10") / Decimal("10.7"),
        current_optimizer_cost_minor_units=0,
    )
    return build_replan_scenario(
        ReplanScenarioRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            model_version="workforce-replan-v1",
            baseline=baseline,
            shocks=(
                ScenarioShock(
                    shock_id="absence",
                    shock_type="absence",
                    capacity_loss_man_hours=Decimal("1"),
                    source_ref="scenario://absence/E11",
                ),
            ),
            kpi_sensitivities=(
                KpiSensitivity(
                    kpi_key="picking_seconds_per_order",
                    delta_per_dpi_point=Decimal("100"),
                    model_version="workforce-replan-v1",
                    source_ref="model://sanitized/picking",
                ),
            ),
            cost_assumption=CostAssumption(
                incremental_cost_minor_units_per_man_hour=Decimal("1000"),
                model_version="workforce-replan-v1",
                source_ref="model://sanitized/cost",
            ),
        )
    )


def _payload() -> dict:
    return {
        "location_id": "WH-001",
        "model_version": "workforce-replan-v1",
        "shocks": [
            {
                "shock_id": "absence",
                "shock_type": "absence",
                "capacity_loss_man_hours": 1,
                "source_ref": "scenario://absence/E11",
            }
        ],
    }


def test_what_if_api_returns_recommendation_kpi_cost_delta_without_apply(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(replan_router.router, prefix="/api/workforce")
    monkeypatch.setattr(workforce_router, "_canonical_warehouse_id", lambda value: value)
    monkeypatch.setattr(workforce_router, "_warehouse_scope", lambda request, role: None)
    scenario = _scenario()
    monkeypatch.setattr(
        replan_router,
        "compute_and_persist_replan_scenario",
        lambda **kwargs: (
            scenario,
            {
                "scenario_id": "SCN-test",
                "proposal_id": "RPL-test",
                "proposal_fingerprint": "e" * 64,
                "automatic_apply_permitted": False,
                "scenario_idempotent_replay": False,
                "proposal_idempotent_replay": False,
            },
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/api/workforce/scenarios",
        json=_payload(),
        headers={
            "X-OPEX-Role": "regional_manager",
            "X-OPEX-Permissions": "workforce.schedule.propose",
            "X-OPEX-User": "manager-a",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scenario_effective_man_hours"] == 9.7
    assert body["scenario_gap_man_hours"] == 0.3
    assert body["cost_delta_minor_units"] == 300
    assert body["predicted_kpi_deltas"]["picking_seconds_per_order"] > 0
    assert body["recommendation"] == "rerun_constraint_optimizer_for_capacity_loss"
    assert body["automatic_apply_permitted"] is False


def test_browser_cannot_supply_tenant_baseline_sensitivity_or_cost_authority() -> None:
    app = FastAPI()
    app.include_router(replan_router.router, prefix="/api/workforce")
    client = TestClient(app)
    for forbidden_field, value in (
        ("tenant_id", "attacker"),
        ("baseline_required_man_hours", 999),
        ("kpi_sensitivities", [{"kpi_key": "x", "delta_per_dpi_point": 999}]),
        ("cost_assumption", {"incremental_cost_minor_units_per_man_hour": 0}),
    ):
        payload = _payload()
        payload[forbidden_field] = value
        response = client.post(
            "/api/workforce/scenarios",
            json=payload,
            headers={"X-OPEX-Role": "admin"},
        )
        assert response.status_code == 422, (forbidden_field, response.text)


def test_replan_api_has_no_apply_or_publish_mutation_surface() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/workforce/scenarios" in paths
    assert "/api/workforce/depots/{location_id}/scenarios/latest" in paths
    assert "/api/workforce/scenarios/{scenario_id}/apply" not in paths
    assert "/api/workforce/replan-proposals/{proposal_id}/apply" not in paths
    assert "/api/workforce/schedules/publish-from-scenario" not in paths


def test_scenario_create_requires_propose_permission() -> None:
    app = FastAPI()
    app.include_router(replan_router.router, prefix="/api/workforce")
    client = TestClient(app)
    response = client.post(
        "/api/workforce/scenarios",
        json=_payload(),
        headers={"X-OPEX-Role": "viewer"},
    )
    assert response.status_code == 403
