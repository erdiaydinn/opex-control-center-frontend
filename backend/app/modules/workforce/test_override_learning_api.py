from fastapi import FastAPI
from fastapi.testclient import TestClient

from . import override_learning_router
from . import router as workforce_router


def _override_payload() -> dict:
    return {
        "location_id": "WH-001",
        "optimizer_proposal_fingerprint": "a" * 64,
        "decision": "modified",
        "reason_code": "break_timing",
        "reason_note": "sanitized",
        "observed_action_type": "call_in",
    }


def test_override_api_records_reason_without_browser_pre_kpi_authority(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(override_learning_router.router, prefix="/api/workforce")
    monkeypatch.setattr(workforce_router, "_canonical_warehouse_id", lambda value: value)
    monkeypatch.setattr(workforce_router, "_warehouse_scope", lambda request, role: None)
    observed = {}

    def record(**kwargs):
        observed.update(kwargs)
        return {
            "id": "OVR-test",
            "tenant_id": "tenant-a",
            "optimizer_proposal_fingerprint": kwargs["optimizer_proposal_fingerprint"],
            "decision": kwargs["decision"],
            "reason_code": kwargs["reason_code"],
            "observed_action_type": kwargs["observed_action_type"],
            "pre_kpi_context_ref": "workforce-dpi://" + "b" * 64,
            "idempotent_replay": False,
        }

    monkeypatch.setattr(override_learning_router, "record_manager_override", record)
    client = TestClient(app)
    response = client.post(
        "/api/workforce/optimizer-overrides",
        json=_override_payload(),
        headers={
            "X-OPEX-Role": "regional_manager",
            "X-OPEX-Permissions": "workforce.schedule.override",
            "X-OPEX-User": "manager-a",
        },
    )
    assert response.status_code == 200, response.text
    assert observed["location_id"] == "WH-001"
    assert observed["actor_subject"] == "manager-a"
    assert "pre_kpi_context_ref" not in observed
    assert response.json()["pre_kpi_context_ref"].startswith("workforce-dpi://")


def test_browser_cannot_supply_tenant_pre_kpi_or_learning_policy() -> None:
    app = FastAPI()
    app.include_router(override_learning_router.router, prefix="/api/workforce")
    client = TestClient(app)
    for key, value in (
        ("tenant_id", "attacker"),
        ("pre_kpi_context_ref", "fake://kpi"),
        ("learning_version", "attacker-v99"),
        ("action_cost_multipliers", {"call_in": 0}),
    ):
        payload = _override_payload()
        payload[key] = value
        response = client.post(
            "/api/workforce/optimizer-overrides",
            json=payload,
            headers={"X-OPEX-Role": "admin"},
        )
        assert response.status_code == 422, (key, response.text)


def test_override_outcome_api_is_append_evidence_not_policy_write(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(override_learning_router.router, prefix="/api/workforce")
    monkeypatch.setattr(
        override_learning_router,
        "record_override_outcome",
        lambda **kwargs: {
            "id": "OUT-test",
            "override_id": kwargs["override_id"],
            "worked": kwargs["worked"],
            "post_kpi_context_ref": kwargs["post_kpi_context_ref"],
            "kpi_deltas": {key: str(value) for key, value in kwargs["kpi_deltas"].items()},
            "idempotent_replay": False,
        },
    )
    client = TestClient(app)
    response = client.post(
        "/api/workforce/optimizer-overrides/OVR-test/outcome",
        json={
            "worked": True,
            "post_kpi_context_ref": "kpi://sanitized/post/OVR-test",
            "kpi_deltas": {"picking_seconds_per_order": -15},
            "source_ref": "outcome://sanitized/OVR-test",
        },
        headers={
            "X-OPEX-Role": "regional_manager",
            "X-OPEX-Permissions": "workforce.schedule.override",
            "X-OPEX-User": "manager-a",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["worked"] is True


def test_learning_api_is_read_only_and_has_no_promote_or_apply_endpoint(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(override_learning_router.router, prefix="/api/workforce")
    monkeypatch.setattr(
        override_learning_router,
        "get_learning_summary",
        lambda: {
            "tenant_id": "tenant-a",
            "latest_draft": {
                "sample_count": 5,
                "frequent_override_reasons": ["break_timing"],
                "automatic_apply_permitted": False,
            },
            "approved_version": {"version": "override-learning-v2"},
        },
    )
    client = TestClient(app)
    response = client.get(
        "/api/workforce/learning",
        headers={
            "X-OPEX-Role": "regional_manager",
            "X-OPEX-Permissions": "workforce.pressure.read",
        },
    )
    assert response.status_code == 200
    assert response.json()["latest_draft"]["frequent_override_reasons"] == ["break_timing"]

    from app.main import app as canonical_app

    paths = set(canonical_app.openapi()["paths"])
    assert "/api/workforce/optimizer-overrides" in paths
    assert "/api/workforce/optimizer-overrides/{override_id}/outcome" in paths
    assert "/api/workforce/learning" in paths
    assert "/api/workforce/learning/promote" not in paths
    assert "/api/workforce/learning/apply" not in paths
    assert "/api/workforce/optimizer/apply-learning" not in paths
