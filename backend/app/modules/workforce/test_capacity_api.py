from fastapi import FastAPI
from fastapi.testclient import TestClient

from . import capacity_router
from . import router as workforce_router


def _payload() -> dict:
    workers = [
        {
            "employee_id": f"E{i:02d}",
            "scheduled_hours": 1,
            "skills": ["picking"],
            "source_ref": f"roster://sanitized/E{i:02d}/2026-08-17T09",
        }
        for i in range(1, 11)
    ]
    workers.extend(
        [
            {
                "employee_id": "E11",
                "scheduled_hours": 1,
                "break_hours": 0.3,
                "skills": ["picking"],
                "source_ref": "roster://sanitized/E11/2026-08-17T09",
            },
            {
                "employee_id": "E12",
                "scheduled_hours": 1,
                "absence_hours": 1,
                "skills": ["picking"],
                "source_ref": "roster://sanitized/E12/2026-08-17T09",
            },
            {
                "employee_id": "E13",
                "scheduled_hours": 1,
                "skills": ["inbound"],
                "source_ref": "roster://sanitized/E13/2026-08-17T09",
            },
        ]
    )
    return {
        "location_id": "WH-001",
        "interval_start": "2026-08-17T09:00:00+00:00",
        "interval_minutes": 60,
        "model_version": "workforce-capacity-v1",
        "workers": workers,
        "source_refs": [
            "schedule://sanitized/WH-001/2026-08-17T09",
            "absence://sanitized/WH-001/2026-08-17T09",
            "break://sanitized/WH-001/2026-08-17T09",
            "skills://sanitized/WH-001/2026-08-17T09",
        ],
        "skill_demand": {"picking": 11.7},
    }


def test_capacity_api_returns_acceptance_value_and_uses_server_tenant(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(capacity_router.router, prefix="/api")
    monkeypatch.setattr(capacity_router.persistence, "tenant_id", lambda: "tenant-a")
    monkeypatch.setattr(workforce_router, "_canonical_warehouse_id", lambda value: value)
    monkeypatch.setattr(workforce_router, "_warehouse_scope", lambda request, role: None)
    observed = {}

    def persist(snapshot, *, actor_subject):
        observed["tenant_id"] = snapshot.tenant_id
        observed["actor_subject"] = actor_subject
        observed["effective_capacity"] = snapshot.effective_capacity
        return {"id": "CAP-test", "idempotent_replay": False}

    monkeypatch.setattr(capacity_router, "persist_capacity_snapshot", persist)
    client = TestClient(app)
    response = client.post(
        "/api/workforce/capacity-snapshots",
        json=_payload(),
        headers={"X-OPEX-Role": "admin", "X-OPEX-User": "planner-a"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scheduled_fte"] == 13.0
    assert body["effective_capacity"] == 10.7
    assert body["skill_deficit_man_hours"] == "1"
    assert observed == {
        "tenant_id": "tenant-a",
        "actor_subject": "planner-a",
        "effective_capacity": capacity_router.Decimal("10.7"),
    }


def test_capacity_api_rejects_browser_tenant_authority(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(capacity_router.router, prefix="/api")
    payload = _payload()
    payload["tenant_id"] = "attacker-tenant"
    client = TestClient(app)

    response = client.post(
        "/api/workforce/capacity-snapshots",
        json=payload,
        headers={"X-OPEX-Role": "admin"},
    )
    assert response.status_code == 422


def test_capacity_api_denies_missing_permission(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(capacity_router.router, prefix="/api")
    monkeypatch.setattr(capacity_router.persistence, "tenant_id", lambda: "tenant-a")
    monkeypatch.setattr(workforce_router, "_canonical_warehouse_id", lambda value: value)
    monkeypatch.setattr(workforce_router, "_warehouse_scope", lambda request, role: None)
    client = TestClient(app)

    response = client.post(
        "/api/workforce/capacity-snapshots",
        json=_payload(),
        headers={"X-OPEX-Role": "viewer"},
    )
    assert response.status_code == 403


def test_main_app_registers_capacity_routes() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/workforce/capacity-snapshots" in paths
    assert "/api/workforce/depots/{location_id}/capacity/latest" in paths
