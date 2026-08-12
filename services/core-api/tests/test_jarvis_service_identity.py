from __future__ import annotations

import json
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.core.config import Settings
from app.core.internal_identity import InternalAssertionInvalid
from app.core.jarvis_service_identity import (
    JARVIS_SERVICE_ASSERTION_TYP,
    JARVIS_SERVICE_AUDIENCE,
    JARVIS_SERVICE_PURPOSE,
    JARVIS_SERVICE_SUBJECT,
    verify_jarvis_service_assertion,
)

ISSUER = "opex-identity-gateway"
KID = "jarvis-test-es256-v1"


def verification_material(
    tmp_path: Path,
) -> tuple[
    ec.EllipticCurvePrivateKey,
    Settings,
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

    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [public_jwk],
            }
        ),
        encoding="utf-8",
    )

    settings = Settings(
        internal_assertion_issuer=ISSUER,
        internal_assertion_jwks_file=str(jwks_path),
    )

    return private_key, settings


def token_for(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    token_type: str = JARVIS_SERVICE_ASSERTION_TYP,
    audience: str = JARVIS_SERVICE_AUDIENCE,
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
    private_key, settings = verification_material(
        tmp_path
    )

    verified = verify_jarvis_service_assertion(
        token_for(private_key),
        settings,
    )

    assert verified.service_subject == JARVIS_SERVICE_SUBJECT
    assert verified.assertion_id == "jarvis-test-assertion-0001"


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
    private_key, settings = verification_material(
        tmp_path
    )

    token = token_for(
        private_key,
        token_type=token_type,
        audience=audience,
        subject=subject,
        purpose=purpose,
    )

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(
            token,
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
            JARVIS_SERVICE_AUDIENCE,
            "identity-gateway",
            JARVIS_SERVICE_PURPOSE,
        ),
        (
            JARVIS_SERVICE_AUDIENCE,
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
    private_key, settings = verification_material(
        tmp_path
    )

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
    private_key, settings = verification_material(
        tmp_path
    )

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


def test_lifetime_cannot_exceed_internal_security_window(
    tmp_path: Path,
) -> None:
    private_key, settings = verification_material(
        tmp_path
    )

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(
            token_for(
                private_key,
                lifetime=(
                    settings.internal_assertion_max_lifetime_seconds
                    + 1
                ),
            ),
            settings,
        )
