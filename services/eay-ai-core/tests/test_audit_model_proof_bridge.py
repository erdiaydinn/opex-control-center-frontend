from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app import model_promotion_routes as routes
from app.model_promotion_gate import PromotionRecord


TOKEN = "audit-model-proof-test-token-32-bytes-minimum"


def promotion() -> PromotionRecord:
    return PromotionRecord(
        id="promotion-id",
        fingerprint="a" * 64,
        release_proof_fingerprint="b" * 64,
        offline_eval_fingerprint="c" * 64,
        release_evaluation_evidence_fingerprint="d" * 64,
        historical_legal_eval_fingerprint="e" * 64,
        safety_eval_fingerprint="f" * 64,
        eval_dataset_sha256="1" * 64,
        training_manifest_chain_sha256="2" * 64,
        model_record_id="vision-model-record",
        artifact_sha256="3" * 64,
        artifact_provenance_fingerprint="4" * 64,
        training_job_fingerprint="5" * 64,
        training_execution_receipt_fingerprint="6" * 64,
        canary_evidence_fingerprint="7" * 64,
        approved_by="release-operator",
        approval_reference="AUDIT-1",
        created_at=datetime.now(timezone.utc),
    )


def test_internal_proof_reverifies_authority_and_binds_challenge(monkeypatch) -> None:
    monkeypatch.setenv("EAY_MODEL_PROOF_API_TOKEN", TOKEN)
    monkeypatch.setattr(routes, "get_current_production_promotion", lambda _: promotion())
    proof = routes.issue_current_production_model_proof(
        "vision-model-record",
        challenge="8" * 64,
        authorization=f"Bearer {TOKEN}",
    )
    assert proof.model_record_id == "vision-model-record"
    assert proof.challenge == "8" * 64
    assert proof.production_promotion_fingerprint == "a" * 64
    assert proof.production_release_proof_fingerprint == "b" * 64
    assert proof.expires_at > proof.issued_at
    assert len(proof.seal) == 64


def test_internal_proof_denies_invalid_token_and_challenge(monkeypatch) -> None:
    monkeypatch.setenv("EAY_MODEL_PROOF_API_TOKEN", TOKEN)
    with pytest.raises(HTTPException) as invalid_token:
        routes.issue_current_production_model_proof(
            "vision-model-record",
            challenge="8" * 64,
            authorization="Bearer wrong",
        )
    assert invalid_token.value.status_code == 403

    with pytest.raises(HTTPException) as invalid_challenge:
        routes.issue_current_production_model_proof(
            "vision-model-record",
            challenge="not-a-challenge",
            authorization=f"Bearer {TOKEN}",
        )
    assert invalid_challenge.value.status_code == 400


def test_revoked_model_authority_failure_is_not_converted_to_proof(monkeypatch) -> None:
    monkeypatch.setenv("EAY_MODEL_PROOF_API_TOKEN", TOKEN)

    def revoked(_: str):
        raise HTTPException(status_code=409, detail="model retired")

    monkeypatch.setattr(routes, "get_current_production_promotion", revoked)
    with pytest.raises(HTTPException) as denied:
        routes.issue_current_production_model_proof(
            "vision-model-record",
            challenge="8" * 64,
            authorization=f"Bearer {TOKEN}",
        )
    assert denied.value.status_code == 409
