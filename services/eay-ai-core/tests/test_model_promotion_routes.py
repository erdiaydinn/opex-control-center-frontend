from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app import model_promotion_routes
from app.entrypoint import compose_app
from app.model_promotion_gate import PromotionRecord, PromotionRequest
from app.model_promotion_routes import PromotionApiRequest

TOKEN = "t" * 48


def _record() -> PromotionRecord:
    return PromotionRecord(
        id="promotion-1",
        fingerprint="1" * 64,
        release_proof_fingerprint="2" * 64,
        offline_eval_fingerprint="3" * 64,
        release_evaluation_evidence_fingerprint="4" * 64,
        historical_legal_eval_fingerprint="5" * 64,
        safety_eval_fingerprint="6" * 64,
        eval_dataset_sha256="7" * 64,
        training_manifest_chain_sha256="8" * 64,
        model_record_id="model-1",
        artifact_sha256="9" * 64,
        artifact_provenance_fingerprint="a" * 64,
        training_job_fingerprint="b" * 64,
        training_execution_receipt_fingerprint="c" * 64,
        canary_evidence_fingerprint="d" * 64,
        approved_by="release-manager",
        approval_reference="REL-1",
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )


class _Gate:
    def __init__(self, *, failure: Exception | None = None):
        self.failure = failure
        self.promoted_payload: PromotionRequest | None = None
        self.required_model: str | None = None

    def promote(self, payload: PromotionRequest) -> PromotionRecord:
        if self.failure:
            raise self.failure
        self.promoted_payload = payload
        return _record()

    def require_current_production(self, *, model_record_id: str) -> PromotionRecord:
        if self.failure:
            raise self.failure
        self.required_model = model_record_id
        return _record()


def _request() -> PromotionApiRequest:
    return PromotionApiRequest(
        model_record_id="model-1",
        canary_evidence_fingerprint="d" * 64,
        release_evaluation_evidence_fingerprint="4" * 64,
        approval_reference="REL-1",
    )


def _authorization(monkeypatch) -> str:
    monkeypatch.setenv("EAY_MODEL_PROMOTION_API_TOKEN", TOKEN)
    monkeypatch.setenv("EAY_MODEL_PROMOTION_OPERATOR_ID", "release-manager")
    return f"Bearer {TOKEN}"


def test_governed_promotion_routes_exist_once_after_recomposition():
    app = compose_app()
    app = compose_app()
    post = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/v1/model-promotions"
        and "POST" in getattr(route, "methods", set())
    ]
    get = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/v1/model-promotions/{model_record_id}"
        and "GET" in getattr(route, "methods", set())
    ]
    assert len(post) == 1
    assert len(get) == 1
    assert post[0].endpoint.__module__ == "app.main"
    assert get[0].endpoint.__module__ == "app.main"


def test_post_uses_governed_gate_and_deployment_authoritative_operator(monkeypatch):
    gate = _Gate()
    monkeypatch.setattr(model_promotion_routes, "promotion_gate", gate)
    record = model_promotion_routes.promote_model(
        _request(),
        authorization=_authorization(monkeypatch),
    )
    assert record.fingerprint == "1" * 64
    assert gate.promoted_payload is not None
    assert gate.promoted_payload.model_record_id == "model-1"
    assert gate.promoted_payload.approved_by == "release-manager"


def test_post_is_disabled_when_release_authority_is_not_configured(monkeypatch):
    monkeypatch.delenv("EAY_MODEL_PROMOTION_API_TOKEN", raising=False)
    monkeypatch.delenv("EAY_MODEL_PROMOTION_OPERATOR_ID", raising=False)
    with pytest.raises(HTTPException) as exc:
        model_promotion_routes.promote_model(_request(), authorization=None)
    assert exc.value.status_code == 503
    assert exc.value.detail == "model_promotion_api_not_configured"


def test_post_rejects_invalid_bearer_even_when_configured(monkeypatch):
    _authorization(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        model_promotion_routes.promote_model(
            _request(),
            authorization="Bearer definitely-not-the-release-secret",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "model_promotion_authorization_invalid"


def test_get_reverifies_current_production(monkeypatch):
    gate = _Gate()
    monkeypatch.setattr(model_promotion_routes, "promotion_gate", gate)
    record = model_promotion_routes.get_current_production_promotion("model-1")
    assert record.release_proof_fingerprint == "2" * 64
    assert gate.required_model == "model-1"


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (KeyError("model_not_found"), 404),
        (ValueError("production_promotion_requires_canary_status"), 409),
    ],
)
def test_api_maps_fail_closed_gate_errors(monkeypatch, failure, status):
    monkeypatch.setattr(model_promotion_routes, "promotion_gate", _Gate(failure=failure))
    with pytest.raises(HTTPException) as exc:
        model_promotion_routes.promote_model(
            _request(),
            authorization=_authorization(monkeypatch),
        )
    assert exc.value.status_code == status
