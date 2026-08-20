import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.modules.audit.field_activation_proof import (
    AuditFieldActivationProof,
    AuditFieldActivationProofUnavailable,
    EAYAuditFieldActivationProofVerifier,
    _sealed_payload,
    require_field_activation_for_production,
)

TOKEN = "k" * 64
TENANT = "00000000-0000-0000-0000-000000000123"
RELEASE_SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[1]


def _proof_body(request: httpx.Request, **overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    body: dict[str, object] = {
        "tenant_id": TENANT,
        "release_sha": RELEASE_SHA,
        "capability": "photo_vision",
        "deployment_fingerprint": "1" * 64,
        "field_uat_fingerprint": "2" * 64,
        "device_attestation_fingerprint": "3" * 64,
        "private_storage_fingerprint": "4" * 64,
        "privacy_scanner_fingerprint": "5" * 64,
        "video_decoder_fingerprint": None,
        "challenge": request.headers["X-EAY-Audit-Field-Challenge"],
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=20)).isoformat(),
        "seal": "",
    }
    body.update(overrides)
    body["seal"] = hmac.new(TOKEN.encode(), _sealed_payload(body), hashlib.sha256).hexdigest()
    return body


@pytest.mark.asyncio
async def test_current_field_activation_proof_is_challenge_and_identity_bound() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["X-EAY-Audit-Field-Challenge"]
        assert request.url.path.endswith(f"/{TENANT}/photo_vision/{RELEASE_SHA}")
        return httpx.Response(200, json=_proof_body(request))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = EAYAuditFieldActivationProofVerifier(
        base_url="https://eay-audit-field-authority",
        token=TOKEN,
        client=client,
    )
    proof = await verifier.require_current_activation(
        tenant_id=TENANT,
        release_sha=RELEASE_SHA,
        capability="photo_vision",
    )
    await client.aclose()

    assert proof.tenant_id == TENANT
    assert proof.release_sha == RELEASE_SHA
    assert proof.capability == "photo_vision"


@pytest.mark.asyncio
async def test_wrong_tenant_or_expired_field_proof_fails_closed() -> None:
    async def wrong_tenant(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_proof_body(request, tenant_id="other"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrong_tenant))
    verifier = EAYAuditFieldActivationProofVerifier(
        base_url="https://eay-audit-field-authority",
        token=TOKEN,
        client=client,
    )
    with pytest.raises(AuditFieldActivationProofUnavailable):
        await verifier.require_current_activation(
            tenant_id=TENANT,
            release_sha=RELEASE_SHA,
            capability="photo_vision",
        )
    await client.aclose()

    async def expired(request: httpx.Request) -> httpx.Response:
        now = datetime.now(UTC)
        return httpx.Response(
            200,
            json=_proof_body(
                request,
                issued_at=(now - timedelta(seconds=40)).isoformat(),
                expires_at=(now - timedelta(seconds=10)).isoformat(),
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(expired))
    verifier = EAYAuditFieldActivationProofVerifier(
        base_url="https://eay-audit-field-authority",
        token=TOKEN,
        client=client,
    )
    with pytest.raises(AuditFieldActivationProofUnavailable):
        await verifier.require_current_activation(
            tenant_id=TENANT,
            release_sha=RELEASE_SHA,
            capability="photo_vision",
        )
    await client.aclose()


def test_video_activation_requires_decoder_acceptance() -> None:
    with pytest.raises(ValueError):
        AuditFieldActivationProof(
            tenant_id=TENANT,
            release_sha=RELEASE_SHA,
            capability="video_vision",
            deployment_fingerprint="1" * 64,
            field_uat_fingerprint="2" * 64,
            device_attestation_fingerprint="3" * 64,
            private_storage_fingerprint="4" * 64,
            privacy_scanner_fingerprint="5" * 64,
            video_decoder_fingerprint=None,
        )


@pytest.mark.asyncio
async def test_nonproduction_does_not_invent_or_require_field_authority(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_ENVIRONMENT", "staging")
    monkeypatch.delenv("EAY_RELEASE_SHA", raising=False)
    result = await require_field_activation_for_production(
        tenant_id=TENANT,
        capability="photo_vision",
    )
    assert result is None


@pytest.mark.asyncio
async def test_production_without_exact_release_sha_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_ENVIRONMENT", "production")
    monkeypatch.delenv("EAY_RELEASE_SHA", raising=False)
    with pytest.raises(AuditFieldActivationProofUnavailable):
        await require_field_activation_for_production(
            tenant_id=TENANT,
            capability="photo_vision",
        )


def test_vision_authorization_source_binds_production_field_authority() -> None:
    source = (ROOT / "app/modules/audit/vision_inference_authorization.py").read_text(
        encoding="utf-8"
    )
    assert "require_field_activation_for_production" in source
    assert "current_production_field_activation_proof_unavailable" in source
    assert "field_activation_fingerprint" in source
