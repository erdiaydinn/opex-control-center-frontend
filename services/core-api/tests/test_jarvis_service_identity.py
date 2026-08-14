from __future__ import annotations

import json
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.core.internal_identity import (
    InternalAssertionInvalid,
    InternalAssertionUnavailable,
)
from app.core.jarvis_service_identity import (
    JARVIS_SERVICE_ASSERTION_TYP,
    JARVIS_SERVICE_PURPOSE,
    JARVIS_SERVICE_SUBJECT,
    JarvisServiceSettings,
    verify_jarvis_service_assertion,
)

ISSUER = "eay-ai-core"
AUDIENCE = "opex-core-jarvis"
KID = "jarvis-test-es256-v1"


def verification_material(
    tmp_path: Path,
) -> tuple[
    ec.EllipticCurvePrivateKey,
    JarvisServiceSettings,
]:
    private_key = ec.generate_private_key(
        ec.SECP256R1()
    )

    public_jwk = json.loads(
        ECAlgorithm.to_jwk(
            private_key.public_key()
        )
    )
    public_jwk.update(
        {
            "kid": KID,
            "use": "sig",
            "alg": "ES256",
        }
    )

    jwks_path = tmp_path / "jarvis-jwks.json"
    jwks_path.write_text(
        json.dumps({"keys": [public_jwk]}),
        encoding="utf-8",
    )

    settings = JarvisServiceSettings(
        enabled=True,
        assertion_issuer=ISSUER,
        assertion_audience=AUDIENCE,
        assertion_jwks_file=str(jwks_path),
    )

    return private_key, settings


def token_for(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    token_type: str = JARVIS_SERVICE_ASSERTION_TYP,
    audience: str = AUDIENCE,
    subject: str = JARVIS_SERVICE_SUBJECT,
    purpose: str = JARVIS_SERVICE_PURPOSE,
    lifetime: int = 30,
    extra_claims: dict[str, object] | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "iss": ISSUER,
        "aud": audience,
        "sub": subject,
        "purpose": purpose,
        "jti": "jarvis-test-assertion-0001",
        "iat": now,
        "nbf": now,
        "exp": now + lifetime,
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={
            "kid": KID,
            "typ": token_type,
        },
    )


def test_valid_jarvis_service_assertion_is_accepted(
    tmp_path: Path,
) -> None:
    private_key, settings = verification_material(tmp_path)
    verified = verify_jarvis_service_assertion(
        token_for(private_key),
        settings,
    )

    assert verified.service_subject == JARVIS_SERVICE_SUBJECT
    assert verified.assertion_id == "jarvis-test-assertion-0001"


def test_disabled_jarvis_identity_fails_closed() -> None:
    settings = JarvisServiceSettings()

    with pytest.raises(InternalAssertionUnavailable):
        verify_jarvis_service_assertion(
            "opaque-token",
            settings,
        )


def test_identity_gateway_issuer_and_reserved_audiences_are_rejected() -> None:
    with pytest.raises(ValueError):
        JarvisServiceSettings(
            enabled=True,
            assertion_issuer="opex-identity-gateway",
            assertion_jwks_file="jwks.json",
        )

    for audience in (
        "opex-core-api",
        "opex-core-preauth",
    ):
        with pytest.raises(ValueError):
            JarvisServiceSettings(
                enabled=True,
                assertion_audience=audience,
                assertion_jwks_file="jwks.json",
            )


def test_foreign_signing_key_is_not_trusted(
    tmp_path: Path,
) -> None:
    _, settings = verification_material(tmp_path)
    foreign_key = ec.generate_private_key(
        ec.SECP256R1()
    )

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(
            token_for(foreign_key),
            settings,
        )


@pytest.mark.parametrize(
    ("token_type", "audience", "subject", "purpose"),
    [
        (
            "opex-internal-service+jwt",
            "opex-core-preauth",
            "identity-gateway",
            "preauth",
        ),
        (
            "opex-internal+jwt",
            "opex-core-api",
            "00000000-0000-4000-8000-000000000001",
            JARVIS_SERVICE_PURPOSE,
        ),
    ],
)
def test_phase1_token_types_cannot_cross_into_jarvis_boundary(
    tmp_path: Path,
    token_type: str,
    audience: str,
    subject: str,
    purpose: str,
) -> None:
    private_key, settings = verification_material(tmp_path)

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(
            token_for(
                private_key,
                token_type=token_type,
                audience=audience,
                subject=subject,
                purpose=purpose,
            ),
            settings,
        )


@pytest.mark.parametrize(
    ("audience", "subject", "purpose"),
    [
        (
            "opex-core-api",
            JARVIS_SERVICE_SUBJECT,
            JARVIS_SERVICE_PURPOSE,
        ),
        (
            AUDIENCE,
            "identity-gateway",
            JARVIS_SERVICE_PURPOSE,
        ),
        (
            AUDIENCE,
            JARVIS_SERVICE_SUBJECT,
            "preauth",
        ),
    ],
)
def test_audience_subject_and_purpose_are_exact(
    tmp_path: Path,
    audience: str,
    subject: str,
    purpose: str,
) -> None:
    private_key, settings = verification_material(tmp_path)

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(
            token_for(
                private_key,
                audience=audience,
                subject=subject,
                purpose=purpose,
            ),
            settings,
        )


def test_unexpected_claim_smuggling_is_rejected(
    tmp_path: Path,
) -> None:
    private_key, settings = verification_material(tmp_path)

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(
            token_for(
                private_key,
                extra_claims={
                    "tenant_id": "attacker-tenant",
                    "permissions": ["*"],
                },
            ),
            settings,
        )


def test_lifetime_is_independently_bounded(
    tmp_path: Path,
) -> None:
    private_key, settings = verification_material(tmp_path)

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(
            token_for(
                private_key,
                lifetime=(
                    settings.assertion_max_lifetime_seconds + 1
                ),
            ),
            settings,
        )
