from __future__ import annotations

import json
import os
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
    JARVIS_SERVICE_JWKS_MAX_BYTES,
    JARVIS_SERVICE_PURPOSE,
    JARVIS_SERVICE_SUBJECT,
    JarvisServiceSettings,
    verify_jarvis_service_assertion,
)

ISSUER = "eay-ai-core"
AUDIENCE = "opex-core-jarvis"


def public_jwk(
    private_key: ec.EllipticCurvePrivateKey,
    kid: str,
) -> dict[str, object]:
    value = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    value.update({"kid": kid, "use": "sig", "alg": "ES256"})
    return value


def write_jwks_atomic(
    path: Path,
    keys: list[dict[str, object]],
) -> None:
    temporary = path.with_suffix(path.suffix + ".next")
    temporary.write_text(
        json.dumps({"keys": keys}),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def token_for(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    kid: str,
    jti: str,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": JARVIS_SERVICE_SUBJECT,
            "purpose": JARVIS_SERVICE_PURPOSE,
            "jti": jti,
            "iat": now,
            "nbf": now,
            "exp": now + 30,
        },
        private_key,
        algorithm="ES256",
        headers={
            "kid": kid,
            "typ": JARVIS_SERVICE_ASSERTION_TYP,
        },
    )


def settings_for(path: Path) -> JarvisServiceSettings:
    return JarvisServiceSettings(
        enabled=True,
        assertion_issuer=ISSUER,
        assertion_audience=AUDIENCE,
        assertion_jwks_file=str(path),
    )


def test_atomic_jwks_rotation_is_seen_without_process_restart(
    tmp_path: Path,
) -> None:
    old_private = ec.generate_private_key(ec.SECP256R1())
    new_private = ec.generate_private_key(ec.SECP256R1())
    old_key = public_jwk(old_private, "jarvis-old-v1")
    new_key = public_jwk(new_private, "jarvis-new-v2")
    jwks_path = tmp_path / "jarvis.jwks.json"
    write_jwks_atomic(jwks_path, [old_key])
    settings = settings_for(jwks_path)

    old_token = token_for(
        old_private,
        kid="jarvis-old-v1",
        jti="jarvis-rotation-old-0001",
    )
    new_token = token_for(
        new_private,
        kid="jarvis-new-v2",
        jti="jarvis-rotation-new-0001",
    )

    verify_jarvis_service_assertion(old_token, settings)

    write_jwks_atomic(jwks_path, [new_key, old_key])
    verify_jarvis_service_assertion(new_token, settings)
    verify_jarvis_service_assertion(old_token, settings)

    write_jwks_atomic(jwks_path, [new_key])
    verify_jarvis_service_assertion(new_token, settings)

    with pytest.raises(InternalAssertionInvalid):
        verify_jarvis_service_assertion(old_token, settings)


def test_malformed_rotated_jwks_fails_closed_instead_of_using_stale_cache(
    tmp_path: Path,
) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwks_path = tmp_path / "jarvis.jwks.json"
    write_jwks_atomic(
        jwks_path,
        [public_jwk(private_key, "jarvis-v1")],
    )
    settings = settings_for(jwks_path)
    token = token_for(
        private_key,
        kid="jarvis-v1",
        jti="jarvis-malformed-rotation-0001",
    )

    verify_jarvis_service_assertion(token, settings)

    replacement = jwks_path.with_suffix(".broken")
    replacement.write_text("{not-json", encoding="utf-8")
    os.replace(replacement, jwks_path)

    with pytest.raises(InternalAssertionUnavailable):
        verify_jarvis_service_assertion(token, settings)


def test_oversized_rotated_jwks_is_rejected_before_json_parse(
    tmp_path: Path,
) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwks_path = tmp_path / "jarvis.jwks.json"
    jwks_path.write_bytes(b"x" * (JARVIS_SERVICE_JWKS_MAX_BYTES + 1))
    settings = settings_for(jwks_path)
    token = token_for(
        private_key,
        kid="jarvis-v1",
        jti="jarvis-oversized-jwks-0001",
    )

    with pytest.raises(InternalAssertionUnavailable):
        verify_jarvis_service_assertion(token, settings)
