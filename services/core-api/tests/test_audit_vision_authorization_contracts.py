import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.modules.audit.control_contracts import (
    AuditQuestionControl,
    AuditVisionContract,
    parse_question_controls,
    question_control_fingerprint,
)
from app.modules.audit.privacy_verification_runtime import (
    AuditPrivacyScanResult,
    AuditServerPrivacyVerification,
)
from app.modules.audit.privacy_verification_service import (
    SERVER_PRIVACY_AUTHORITY_VERSION,
)
from app.modules.audit.privacy_verification_service import (
    _fingerprint as privacy_verification_fingerprint,
)
from app.modules.audit.schemas import AuditProgramCreate
from app.modules.audit.vision_inference_authorization import (
    _authorization_fingerprint,
    _privacy_event_is_current_and_intact,
)
from app.modules.audit.vision_model_proof import (
    AICoreProductionModelProofVerifier,
    ProductionModelProof,
    ProductionModelProofUnavailable,
    UnavailableProductionModelProofVerifier,
)

CORE_API_ROOT = Path(__file__).resolve().parents[1]
PROOF_TOKEN = "audit-model-proof-test-token-32-bytes-minimum"


def _proof_response(request: httpx.Request, **changes: object) -> httpx.Response:
    challenge = request.headers["X-EAY-Model-Proof-Challenge"]
    now = datetime.now(UTC)
    body: dict[str, object] = {
        "model_record_id": "vision-model-record",
        "artifact_sha256": "a" * 64,
        "artifact_provenance_fingerprint": "b" * 64,
        "production_promotion_fingerprint": "c" * 64,
        "production_release_proof_fingerprint": "d" * 64,
        "challenge": challenge,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=30)).isoformat(),
    }
    body.update(changes)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    body["seal"] = hmac.new(
        PROOF_TOKEN.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()
    return httpx.Response(200, json=body)


async def _verify_with(handler) -> ProductionModelProof:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = AICoreProductionModelProofVerifier(
            base_url="http://eay-ai-core:8000",
            token=PROOF_TOKEN,
            client=client,
        )
        return await verifier.require_current_production("vision-model-record")


def visual_control(model_record_id: str = "vision-model-record") -> AuditQuestionControl:
    return AuditQuestionControl(
        item_key="front_area_cleanliness",
        evidence_modalities=("VISUAL",),
        vision_contract=AuditVisionContract(
            model_record_id=model_record_id,
            required_capabilities=("object_detection", "visual_reasoning"),
        ),
        risk_class="food_safety",
        default_priority="high",
        action_template_key="remove_waste_and_clean",
        owner_rule_key="location_manager",
        sla_rule_key="food_safety_high",
    )


def test_question_control_rejects_vision_without_visual_or_video_evidence() -> None:
    with pytest.raises(ValidationError, match="requires VISUAL or VIDEO"):
        AuditQuestionControl(
            item_key="temperature_check",
            evidence_modalities=("SENSOR",),
            vision_contract=AuditVisionContract(
                model_record_id="model-1",
                required_capabilities=("visual_reasoning",),
            ),
        )


def test_open_ended_visual_discovery_cannot_be_authoritative() -> None:
    with pytest.raises(ValidationError, match="cannot be authoritative"):
        AuditVisionContract(
            model_record_id="model-1",
            required_capabilities=("visual_reasoning",),
            open_ended_discovery_authoritative=True,
        )


def test_program_creation_rejects_duplicate_question_controls() -> None:
    control = visual_control().model_dump(mode="json")
    with pytest.raises(ValidationError, match="item_key values must be unique"):
        AuditProgramCreate(
            program_key="market.audit.v1",
            version=1,
            name_i18n={"tr": "Market Denetimi"},
            field_template_id="market-template",
            field_template_version=1,
            settings={"question_controls": [control, control]},
        )


def test_control_fingerprint_is_deterministic_and_model_bound() -> None:
    first = question_control_fingerprint(visual_control("model-a"))
    second = question_control_fingerprint(visual_control("model-a"))
    changed = question_control_fingerprint(visual_control("model-b"))
    assert first == second
    assert first != changed
    assert len(first) == 64


@pytest.mark.asyncio
async def test_default_model_proof_verifier_fails_closed() -> None:
    verifier = UnavailableProductionModelProofVerifier()
    with pytest.raises(ProductionModelProofUnavailable):
        await verifier.require_current_production("vision-model-record")


@pytest.mark.asyncio
async def test_ai_core_model_proof_bridge_accepts_fresh_exact_proof() -> None:
    proof = await _verify_with(lambda request: _proof_response(request))
    assert proof.model_record_id == "vision-model-record"
    assert proof.production_release_proof_fingerprint == "d" * 64


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"model_record_id": "fake-model-record"},
        {"expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
        {"challenge": "e" * 64},
    ],
    ids=["wrong-model", "expired-proof", "replayed-challenge"],
)
async def test_ai_core_model_proof_bridge_rejects_wrong_expired_or_replayed_proof(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ProductionModelProofUnavailable):
        await _verify_with(lambda request: _proof_response(request, **changes))


@pytest.mark.asyncio
async def test_ai_core_model_proof_bridge_rejects_tampered_version_or_release_proof() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = _proof_response(request)
        body = response.json()
        body["production_release_proof_fingerprint"] = "f" * 64
        return httpx.Response(200, json=body)

    with pytest.raises(ProductionModelProofUnavailable):
        await _verify_with(handler)


def verified_privacy_context() -> dict[str, object]:
    tenant_id = str(uuid4())
    run_id = uuid4()
    redaction_id = uuid4()
    field_id = uuid4()
    privacy_event_id = uuid4()
    content_sha = "a" * 64
    scanner = AuditPrivacyScanResult(
        detected_face_count=0,
        detected_sensitive_region_count=0,
        scanner_model_ref="privacy-scanner:test",
        scanner_model_fingerprint="b" * 64,
    )
    result = AuditServerPrivacyVerification(
        status="verified",
        reason="server hash/size and privacy scan passed",
        observed_sha256=content_sha,
        observed_byte_size=123,
        scan=scanner,
        privacy_gate_passed=True,
    )
    fingerprint = privacy_verification_fingerprint(
        tenant_id=tenant_id,
        audit_run_id=run_id,
        redaction_receipt_id=redaction_id,
        field_evidence_receipt_id=field_id,
        expected_sha256=content_sha,
        expected_byte_size=123,
        result=result,
    )
    return {
        "tenant_id": tenant_id,
        "audit_run_id": run_id,
        "redaction_receipt_id": redaction_id,
        "field_evidence_receipt_id": field_id,
        "privacy_verification_event_id": privacy_event_id,
        "verification_status": "verified",
        "verification_authority_version": SERVER_PRIVACY_AUTHORITY_VERSION,
        "verification_fingerprint": fingerprint,
        "verification_reason": result.reason,
        "media_kind": "image",
        "redacted_object_sha256": content_sha,
        "redacted_object_byte_size": 123,
        "observed_sha256": content_sha,
        "observed_byte_size": 123,
        "scanner_model_ref": scanner.scanner_model_ref,
        "scanner_model_fingerprint": scanner.scanner_model_fingerprint,
        "detected_face_count": 0,
        "detected_sensitive_region_count": 0,
        "program_key": "market.audit.v1",
        "program_version": 1,
    }


def test_only_exact_server_privacy_v2_event_is_accepted() -> None:
    context = verified_privacy_context()
    assert _privacy_event_is_current_and_intact(context) is True

    legacy = dict(context)
    legacy["verification_authority_version"] = None
    assert _privacy_event_is_current_and_intact(legacy) is False

    tampered = dict(context)
    tampered["verification_fingerprint"] = "c" * 64
    assert _privacy_event_is_current_and_intact(tampered) is False


def test_authorization_fingerprint_binds_model_contract_privacy_and_evidence() -> None:
    context = verified_privacy_context()
    proof = ProductionModelProof(
        model_record_id="vision-model-record",
        artifact_sha256="c" * 64,
        artifact_provenance_fingerprint="d" * 64,
        production_promotion_fingerprint="e" * 64,
        production_release_proof_fingerprint="f" * 64,
    )
    control = visual_control()
    fingerprint = _authorization_fingerprint(
        tenant_id=str(context["tenant_id"]),
        context=context,
        item_key=control.item_key,
        control_fingerprint=question_control_fingerprint(control),
        proof=proof,
        capabilities=tuple(sorted(control.vision_contract.required_capabilities)),
    )
    changed = _authorization_fingerprint(
        tenant_id=str(context["tenant_id"]),
        context=context,
        item_key=control.item_key,
        control_fingerprint=question_control_fingerprint(control),
        proof=proof.model_copy(update={"artifact_sha256": "9" * 64}),
        capabilities=tuple(sorted(control.vision_contract.required_capabilities)),
    )
    assert len(fingerprint) == 64
    assert fingerprint != changed

    wrong_tenant = _authorization_fingerprint(
        tenant_id=str(uuid4()),
        context=context,
        item_key=control.item_key,
        control_fingerprint=question_control_fingerprint(control),
        proof=proof,
        capabilities=tuple(sorted(control.vision_contract.required_capabilities)),
    )
    assert fingerprint != wrong_tenant


def test_single_use_consumption_is_tenant_bound_and_atomic() -> None:
    source = (
        CORE_API_ROOT / "app/modules/audit/vision_inference_authorization.py"
    ).read_text(encoding="utf-8")
    consume = source.split("async def consume_vision_inference_authorization", 1)[1]
    assert "authorization.tenant_id=CAST(:tenant_id AS UUID)" in consume
    assert "authorization.consumed_at IS NULL" in consume
    assert "authorization.expires_at > CURRENT_TIMESTAMP" in consume
    assert "SET consumed_at=CURRENT_TIMESTAMP" in consume


def test_program_settings_without_controls_remain_valid_but_have_no_vision_contract() -> None:
    program = AuditProgramCreate(
        program_key="legacy.audit",
        version=1,
        name_i18n={"tr": "Legacy"},
        field_template_id="legacy-template",
        field_template_version=1,
        settings={},
    )
    assert parse_question_controls(program.settings) == ()
