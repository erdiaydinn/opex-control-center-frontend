from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from . import dpi_router
from . import router as workforce_router


def _snapshot() -> dict[str, object]:
    return {
        "id": "DPI-test",
        "tenant_id": "tenant-a",
        "location_id": "WH-001",
        "interval_start": "2026-08-17T09:00:00+00:00",
        "model_version": "workforce-dpi-v1",
        "demand_snapshot_fingerprint": "a" * 64,
        "capacity_snapshot_fingerprint": "b" * 64,
        "required_man_hours": Decimal("10"),
        "effective_man_hours": Decimal("10.7"),
        "skill_deficit_man_hours": Decimal("0"),
        "demand_pressure_index": Decimal("0.9345794392523364485981308411"),
        "capacity_gap_man_hours": Decimal("0"),
        "capacity_sufficient": True,
        "kpi_bad": True,
        "bad_kpi_keys": ["picking_seconds_per_order"],
        "manpower_shortage": False,
        "root_cause": "execution_or_process",
        "automatic_extra_people_permitted": False,
        "staffing_review_required": False,
        "kpi_observations": [],
        "explanation": ["effective capacity is sufficient for governed demand"],
        "input_fingerprint": "c" * 64,
        "snapshot_fingerprint": "d" * 64,
        "created_by": "dpi-engine",
        "created_at": "2026-08-17T09:01:00+00:00",
    }


def test_dpi_read_api_returns_non_manpower_root_cause(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(dpi_router.router, prefix="/api/workforce")
    monkeypatch.setattr(workforce_router, "_canonical_warehouse_id", lambda value: value)
    monkeypatch.setattr(workforce_router, "_warehouse_scope", lambda request, role: None)
    monkeypatch.setattr(dpi_router, "get_latest_dpi_snapshot", lambda location_id: _snapshot())

    client = TestClient(app)
    response = client.get(
        "/api/workforce/depots/WH-001/dpi/latest",
        headers={
            "X-OPEX-Role": "regional_manager",
            "X-OPEX-Permissions": "workforce.pressure.read",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["required_man_hours"] == 10.0
    assert body["effective_man_hours"] == 10.7
    assert body["capacity_sufficient"] is True
    assert body["kpi_bad"] is True
    assert body["manpower_shortage"] is False
    assert body["automatic_extra_people_permitted"] is False
    assert body["root_cause"] == "execution_or_process"


def test_dpi_api_has_no_browser_compute_or_staffing_write_surface() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/workforce/depots/{location_id}/dpi/latest" in paths
    assert "/api/workforce/dpi-snapshots" not in paths
    assert "/api/workforce/dpi/recommend-staffing" not in paths


def test_dpi_read_denies_missing_permission(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(dpi_router.router, prefix="/api/workforce")
    client = TestClient(app)

    response = client.get(
        "/api/workforce/depots/WH-001/dpi/latest",
        headers={"X-OPEX-Role": "viewer"},
    )
    assert response.status_code == 403
