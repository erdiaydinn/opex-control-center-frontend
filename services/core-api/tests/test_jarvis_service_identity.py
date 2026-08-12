import json
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.core.jarvis_service_identity import (
    JARVIS_SERVICE_ALGORITHM,
    JARVIS_SERVICE_ASSERTION_TYP,
    JARVIS_SERVICE_PURPOSE,
    JARVIS_SERVICE_SUBJECT,
    JarvisServiceAssertionInvalid,
    JarvisServiceAssertionUnavailable,
    JarvisServiceVerifierSettings,
    verify_jarvis_service_assertion,
)

KID = "eay-ai-core-test-key"
AUDIENCE = "opex-core-jarvis"


def _public_jwk(private_key: ec.EllipticCurvePrivateKey) -> dict[str, object]:
    jwk = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    jwk.update(
        {
            "kid": KID,
            "use": "sig",
            "alg": JARVIS_SERVICE_ALGORITHM,
        }
    )
    return jwk


def _settings(tmp_path, private_key: ec.EllipticCurvePrivateKey):
    jwks_file = tmp_path / "jarvis-service.jwks.json"
    jwks_file.write_text(
        json.dumps({"keys": [_public_jwk(private_key)]}),
        encoding="utf-8",
    )
    return JarvisServiceVerifierSettings(jwks_file=str(jwks_file))


def _token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    now: int,
    lifetime: int = 30,
    audience: str = AUDIENCE,
    token_type: str = JARVIS_SERVICE_ASSERTION_TYP,
    purpose: str = JARVIS_SERVICE_PURPOSE,
    subject: str = JARVIS_SERVICE_SUBJECT,
    extra_claims: dict[str, object] | None = None,
    kid: str = KID,
) -> str:
    claims: dict[str, object] = {
        "iss": JARVIS_SERVICE_SUBJECT,
        "aud": audience,
        "sub": subject,
        "purpose": purpose,
        "jti": str(uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + lifetime,
    }
    claims.update(extra_claims or {})
    return jwt.encode(
        claims,
        private_key,
        algorithm=JARVIS_SERVICE_ALGORITHM,
        headers={"kid": kid, "typ": token_type},
    )


def test_accepts_exact_ai_core_service_contract(tmp_path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    settings = _settings(tmp_path, private_key)
    now = int(time.time())

    verified = verify_jarvis_service_assertion(
        _token(private_key, now=now),
        settings,
        now=now,
    )

    assert verified.service_subject == JARVIS_SERVICE_SUBJECT
    assert verified.issued_at == now
    assert verified.expires_at == now + 30
    assert 1 <= verified.replay_ttl_seconds <= 40


@pytest.mark.parametrize(
    ("token_kwargs", "expected_message"),
    [
        (
            {"audience": "opex-core-preauth"},
            "signature or claims",
        ),
        (
            {"token_type": "opex-internal-service+jwt"},
            "type is invalid",
        ),
        (
            {"purpose": "preauth"},
            "purpose is invalid",
        ),
        (
            {"subject": "identity-gateway"},
            "subject is invalid",
        ),
        (
            {"extra_claims": {"tenant_id": "tenant-a"}},
            "claim contract is invalid",
        ),
    ],
)
def test_rejects_identity_gateway_or_authority_smuggling(
    tmp_path,
    token_kwargs,
    expected_message,
):
    private_key = ec.generate_private_key(ec.SECP256R1())
    settings = _settings(tmp_path, private_key)
    now = int(time.time())

    with pytest.raises(
        JarvisServiceAssertionInvalid,
        match=expected_message,
    ):
        verify_jarvis_service_assertion(
            _token(private_key, now=now, **token_kwargs),
            settings,
            now=now,
        )


def test_rejects_assertion_lifetime_above_hard_max(tmp_path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    settings = _settings(tmp_path, private_key)
    now = int(time.time())

    with pytest.raises(
        JarvisServiceAssertionInvalid,
        match="lifetime is invalid",
    ):
        verify_jarvis_service_assertion(
            _token(private_key, now=now, lifetime=31),
            settings,
            now=now,
        )


def test_rejects_untrusted_kid(tmp_path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    settings = _settings(tmp_path, private_key)
    now = int(time.time())

    with pytest.raises(
        JarvisServiceAssertionInvalid,
        match="signing key is not trusted",
    ):
        verify_jarvis_service_assertion(
            _token(private_key, now=now, kid="other-key"),
            settings,
            now=now,
        )


def test_rejects_private_material_in_trusted_jwks(tmp_path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_jwk = json.loads(ECAlgorithm.to_jwk(private_key))
    private_jwk.update(
        {
            "kid": KID,
            "use": "sig",
            "alg": JARVIS_SERVICE_ALGORITHM,
        }
    )
    jwks_file = tmp_path / "unsafe.jwks.json"
    jwks_file.write_text(
        json.dumps({"keys": [private_jwk]}),
        encoding="utf-8",
    )
    settings = JarvisServiceVerifierSettings(jwks_file=str(jwks_file))
    now = int(time.time())

    with pytest.raises(
        JarvisServiceAssertionUnavailable,
        match="Private key material",
    ):
        verify_jarvis_service_assertion(
            _token(private_key, now=now),
            settings,
            now=now,
        )


def test_settings_reject_phase1_audience_reuse(tmp_path):
    jwks_file = tmp_path / "unused.jwks.json"
    jwks_file.write_text('{"keys": []}', encoding="utf-8")

    with pytest.raises(
        JarvisServiceAssertionInvalid,
        match="audience is invalid",
    ):
        JarvisServiceVerifierSettings(
            jwks_file=str(jwks_file),
            audience="opex-core-preauth",
        )
