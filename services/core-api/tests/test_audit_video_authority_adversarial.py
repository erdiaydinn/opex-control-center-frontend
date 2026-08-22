from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.audit import video_vision_authorization as video_auth
from app.modules.audit.control_contracts import AuditQuestionControl, AuditVisionContract
from app.modules.audit.field_activation_proof import (
    AuditFieldActivationProof,
    AuditFieldActivationProofUnavailable,
    require_field_activation_for_production,
)

CORE_API_ROOT = Path(__file__).resolve().parents[1]
TENANT_ID = str(uuid4())
RELEASE_SHA = "a" * 40


class _FieldVerifier:
    def __init__(self, proof: AuditFieldActivationProof) -> None:
        self.proof = proof

    async def require_current_activation(
        self,
        *,
        tenant_id: str,
        release_sha: str,
        capability: str,
    ) -> AuditFieldActivationProof:
        assert tenant_id == self.proof.tenant_id
        assert release_sha == self.proof.release_sha
        assert capability == self.proof.capability
        return self.proof


def _control(*, modality: str = "VIDEO") -> AuditQuestionControl:
    return AuditQuestionControl(
        item_key="cold_room_video_condition",
        evidence_modalities=(modality,),
        vision_contract=AuditVisionContract(
            model_record_id="video-vision-model",
            required_capabilities=("object_detection", "visual_reasoning"),
        ),
    )


def _proof(*, decoder_fingerprint: str) -> AuditFieldActivationProof:
    return AuditFieldActivationProof(
        tenant_id=TENANT_ID,
        release_sha=RELEASE_SHA,
        capability="video_vision",
        deployment_fingerprint="1" * 64,
        field_uat_fingerprint="2" * 64,
        device_attestation_fingerprint="3" * 64,
        private_storage_fingerprint="4" * 64,
        privacy_scanner_fingerprint="5" * 64,
        video_decoder_fingerprint=decoder_fingerprint,
    )


@pytest.mark.asyncio
async def test_production_video_activation_fails_closed_without_external_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEX_ENVIRONMENT", "production")
    monkeypatch.setenv("EAY_RELEASE_SHA", RELEASE_SHA)
    monkeypatch.delenv("EAY_AUDIT_FIELD_AUTHORITY_URL", raising=False)
    monkeypatch.delenv("EAY_AUDIT_FIELD_AUTHORITY_TOKEN_FILE", raising=False)

    with pytest.raises(
        AuditFieldActivationProofUnavailable,
        match="current production Audit field activation proof is unavailable",
    ):
        await require_field_activation_for_production(
            tenant_id=TENANT_ID,
            capability="video_vision",
        )


@pytest.mark.asyncio
async def test_video_authorization_blocks_decoder_drift_before_model_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEX_ENVIRONMENT", "production")
    monkeypatch.setenv("EAY_RELEASE_SHA", RELEASE_SHA)
    monkeypatch.setattr(video_auth, "REQUIRED_CONSUMERS", {"audit"})

    control = _control()

    async def fake_context(**_: object) -> dict[str, object]:
        return {
            "run_status": "running",
            "settings": {"question_controls": [control.model_dump(mode="json")]},
            "decoder_fingerprint": "8" * 64,
        }

    monkeypatch.setattr(video_auth, "_load_context", fake_context)
    monkeypatch.setattr(video_auth, "_video_event_is_current_and_intact", lambda _: True)

    decision = await video_auth.authorize_video_vision_inference(
        tenant_id=TENANT_ID,
        audit_run_id=uuid4(),
        item_key=control.item_key,
        redaction_receipt_id=uuid4(),
        video_verification_event_id=uuid4(),
        field_activation_proof_verifier=_FieldVerifier(
            _proof(decoder_fingerprint="9" * 64)
        ),
    )

    assert decision.status == "blocked"
    assert decision.reason == "production_video_decoder_fingerprint_mismatch"
    assert decision.vision_inference_authorized is False
    assert decision.finding_authorized is False
    assert decision.action_authorized is False


@pytest.mark.asyncio
async def test_video_authorization_rejects_non_video_question_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(video_auth, "REQUIRED_CONSUMERS", {"audit"})
    control = _control(modality="VISUAL")

    async def fake_context(**_: object) -> dict[str, object]:
        return {
            "run_status": "running",
            "settings": {"question_controls": [control.model_dump(mode="json")]},
        }

    monkeypatch.setattr(video_auth, "_load_context", fake_context)
    monkeypatch.setattr(video_auth, "_video_event_is_current_and_intact", lambda _: True)

    decision = await video_auth.authorize_video_vision_inference(
        tenant_id=TENANT_ID,
        audit_run_id=uuid4(),
        item_key=control.item_key,
        redaction_receipt_id=uuid4(),
        video_verification_event_id=uuid4(),
    )

    assert decision.status == "blocked"
    assert decision.reason == "video_evidence_not_permitted_for_item"
    assert decision.vision_inference_authorized is False


@pytest.mark.asyncio
async def test_video_authorization_rejects_unverified_or_tampered_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(video_auth, "REQUIRED_CONSUMERS", {"audit"})

    async def fake_context(**_: object) -> dict[str, object]:
        return {"run_status": "running"}

    monkeypatch.setattr(video_auth, "_load_context", fake_context)
    monkeypatch.setattr(video_auth, "_video_event_is_current_and_intact", lambda _: False)

    decision = await video_auth.authorize_video_vision_inference(
        tenant_id=TENANT_ID,
        audit_run_id=uuid4(),
        item_key="cold_room_video_condition",
        redaction_receipt_id=uuid4(),
        video_verification_event_id=uuid4(),
    )

    assert decision.status == "blocked"
    assert decision.reason == "server_video_privacy_v1_verification_required"
    assert decision.vision_inference_authorized is False


def test_video_consume_is_fenced_to_tenant_run_expiry_and_single_use() -> None:
    routes = (CORE_API_ROOT / "app/modules/audit/video_routes.py").read_text(
        encoding="utf-8"
    )
    authorization = (
        CORE_API_ROOT / "app/modules/audit/video_vision_authorization.py"
    ).read_text(encoding="utf-8")

    assert "tenant_id = CAST(:tenant_id AS UUID)" in routes
    assert "audit_run_id = CAST(:audit_run_id AS UUID)" in routes
    assert "if not await _authorization_belongs_to_run" in routes
    assert "authorization.tenant_id = CAST(:tenant_id AS UUID)" in authorization
    assert "authorization.consumed_at IS NULL" in authorization
    assert "authorization.expires_at > CURRENT_TIMESTAMP" in authorization
    assert "run.id = authorization.audit_run_id" in authorization
    assert "run.status <> 'cancelled'" in authorization


def test_public_video_route_cannot_accept_client_model_decoder_or_scanner_authority() -> None:
    routes = (CORE_API_ROOT / "app/modules/audit/video_routes.py").read_text(
        encoding="utf-8"
    )
    create_payload = routes.split("class AuditVideoVisionAuthorizationCreate", 1)[1].split(
        "class AuditVideoVisionAuthorizationConsume", 1
    )[0]

    assert "redaction_receipt_id" in create_payload
    assert "video_verification_event_id" in create_payload
    assert "model_record_id" not in create_payload
    assert "decoder" not in create_payload.lower()
    assert "scanner" not in create_payload.lower()
    assert "capabilities" not in create_payload


def test_photo_and_video_inference_leases_are_db_immutable_except_one_way_consumption() -> None:
    migration = (
        CORE_API_ROOT / "alembic/versions/0059_audit_inference_lease_immutability.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0059_audit_inference_lease_immutability"' in migration
    assert 'down_revision: str = "0058_audit_video_replay_fence"' in migration
    assert '"audit_vision_inference_authorizations"' in migration
    assert '"audit_video_inference_authorizations"' in migration
    assert "enforce_audit_inference_lease_consumption_only" in migration
    assert "to_jsonb(NEW) - 'consumed_at'" in migration
    assert "to_jsonb(OLD) - 'consumed_at'" in migration
    assert "OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL" in migration
    assert "NEW.consumed_at := CURRENT_TIMESTAMP" in migration
    assert "REVOKE UPDATE ON TABLE" in migration
    assert "GRANT UPDATE (consumed_at) ON TABLE" in migration
