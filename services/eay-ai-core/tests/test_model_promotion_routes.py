from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.entrypoint import app
from app.model_promotion_gate import PromotionRecord, PromotionRequest
from app import model_promotion_routes


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


def _request() -> PromotionRequest:
    return PromotionRequest(
        model_record_id="model-1",
        canary_evidence_fingerprint="d" * 64,
        release_evaluation_evidence_fingerprint="4" * 64,
        approved_by="release-manager",
        approval_reference="REL-1",
    )


def test_governed_promotion_routes_exist_once_on_production_entrypoint():
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
    assert post[0].endpoint.__module__ == "app.model_promotion_routes"
    assert get[0].endpoint.__module__ == "app.model_promotion_routes"


def test_post_uses_only_governed_promotion_gate(monkeypatch):
    gate = _Gate()
    monkeypatch.setattr(model_promotion_routes, "promotion_gate", gate)
    record = model_promotion_routes.promote_model(_request())
    assert record.fingerprint == "1" * 64
    assert gate.promoted_payload is not None
    assert gate.promoted_payload.model_record_id == "model-1"


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
        model_promotion_routes.promote_model(_request())
    assert exc.value.status_code == status
