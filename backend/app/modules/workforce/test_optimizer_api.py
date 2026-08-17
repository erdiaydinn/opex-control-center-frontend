from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from . import optimizer_router
from . import router as workforce_router


def _proposal() -> dict[str, object]:
    return {
        "id": "OPT-test",
        "tenant_id": "tenant-a",
        "location_id": "WH-001",
        "model_version": "workforce-optimizer-v1",
        "dpi_snapshot_fingerprint": "d" * 64,
        "dpi_root_cause": "execution_or_process",
        "dpi_manpower_shortage": False,
        "input_fingerprint": "a" * 64,
        "proposal_fingerprint": "b" * 64,
        "recommendation_type": "no_staffing_change",
        "selected_candidate_ids": [],
        "selected_actions": [],
        "target_gap_man_hours": Decimal("0"),
        "covered_gap_man_hours": Decimal("0"),
        "remaining_gap_man_hours": Decimal("0"),
        "incremental_cost_minor_units": 0,
        "feasible": True,
        "automatic_execution_permitted": False,
        "human_approval_required": False,
        "explanation": ["DPI root cause does not support staffing"],
        "candidate_pool_fingerprint": "c" * 64,
        "created_by": "optimizer-engine",
        "created_at": "2026-08-17T14:01:00+00:00",
    }


def test_optimizer_read_api_returns_non_executing_proposal(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(optimizer_router.router, prefix="/api/workforce")
    monkeypatch.setattr(workforce_router, "_canonical_warehouse_id", lambda value: value)
    monkeypatch.setattr(workforce_router, "_warehouse_scope", lambda request, role: None)
    monkeypatch.setattr(
        optimizer_router,
        "get_latest_optimizer_proposal",
        lambda location_id: _proposal(),
    )

    client = TestClient(app)
    response = client.get(
        "/api/workforce/depots/WH-001/optimizer/latest",
        headers={
            "X-OPEX-Role": "regional_manager",
            "X-OPEX-Permissions": "workforce.pressure.read",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation_type"] == "no_staffing_change"
    assert body["selected_candidate_ids"] == []
    assert body["automatic_execution_permitted"] is False
    assert body["human_approval_required"] is False


def test_optimizer_api_has_no_browser_proposal_or_execution_surface() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/workforce/depots/{location_id}/optimizer/latest" in paths
    assert "/api/workforce/optimizer/proposals" not in paths
    assert "/api/workforce/optimizer/execute" not in paths
    assert "/api/workforce/optimizer/apply" not in paths


def test_optimizer_read_denies_missing_permission() -> None:
    app = FastAPI()
    app.include_router(optimizer_router.router, prefix="/api/workforce")
    client = TestClient(app)
    response = client.get(
        "/api/workforce/depots/WH-001/optimizer/latest",
        headers={"X-OPEX-Role": "viewer"},
    )
    assert response.status_code == 403
