from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.jarvis_service_identity import (
    JARVIS_SERVICE_ALGORITHM,
    JARVIS_SERVICE_ASSERTION_TYP,
    JARVIS_SERVICE_PURPOSE,
    JARVIS_SERVICE_SUBJECT,
    JarvisServiceIdentityError,
    JarvisServiceIdentitySettings,
    JarvisServiceIdentitySigner,
)


def write_ec_private_key(tmp_path: Path) -> Path:
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "jarvis-private.pem"
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


def signer_for(tmp_path: Path) -> JarvisServiceIdentitySigner:
    return JarvisServiceIdentitySigner(
        JarvisServiceIdentitySettings(
            private_key_file=str(write_ec_private_key(tmp_path)),
            signing_kid="eay-ai-core-es256-v1",
        )
    )


def test_public_jwks_contains_no_private_material(tmp_path: Path) -> None:
    jwks = signer_for(tmp_path).public_jwks()

    assert len(jwks["keys"]) == 1
    key = jwks["keys"][0]
    assert key["kty"] == "EC"
    assert key["crv"] == "P-256"
    assert key["alg"] == "ES256"
    assert key["use"] == "sig"
    assert key["kid"] == "eay-ai-core-es256-v1"
    assert "d" not in key


def test_assertion_has_exact_machine_only_contract(tmp_path: Path) -> None:
    signer = signer_for(tmp_path)
    token = signer.issue_tool_execution_assertion()
    header = jwt.get_unverified_header(token)

    assert header == {
        "alg": JARVIS_SERVICE_ALGORITHM,
        "kid": "eay-ai-core-es256-v1",
        "typ": JARVIS_SERVICE_ASSERTION_TYP,
    }

    public_key = jwt.PyJWK.from_dict(
        signer.public_jwks()["keys"][0]
    ).key
    claims = jwt.decode(
        token,
        public_key,
        algorithms=["ES256"],
        audience="opex-core-jarvis",
        issuer="eay-ai-core",
    )

    assert set(claims) == {
        "iss",
        "aud",
        "sub",
        "purpose",
        "jti",
        "iat",
        "nbf",
        "exp",
    }
    assert claims["sub"] == JARVIS_SERVICE_SUBJECT
    assert claims["purpose"] == JARVIS_SERVICE_PURPOSE
    assert claims["aud"] == "opex-core-jarvis"
    assert claims["iss"] == "eay-ai-core"
    assert claims["nbf"] == claims["iat"]
    assert claims["exp"] - claims["iat"] == 30

    assert "tenant_id" not in claims
    assert "actor_subject" not in claims
    assert "permissions" not in claims
    assert "granted_scopes" not in claims


def test_reserved_phase1_audiences_are_rejected(tmp_path: Path) -> None:
    key_path = str(write_ec_private_key(tmp_path))

    for audience in (
        "opex-core-api",
        "opex-core-preauth",
    ):
        with pytest.raises(JarvisServiceIdentityError):
            JarvisServiceIdentitySettings(
                private_key_file=key_path,
                signing_kid="eay-ai-core-es256-v1",
                audience=audience,
            )


def test_identity_gateway_issuer_cannot_be_reused(tmp_path: Path) -> None:
    with pytest.raises(JarvisServiceIdentityError):
        JarvisServiceIdentitySettings(
            private_key_file=str(write_ec_private_key(tmp_path)),
            signing_kid="eay-ai-core-es256-v1",
            issuer="opex-identity-gateway",
        )


def test_lifetime_is_hard_bounded_to_thirty_seconds(tmp_path: Path) -> None:
    with pytest.raises(JarvisServiceIdentityError):
        JarvisServiceIdentitySettings(
            private_key_file=str(write_ec_private_key(tmp_path)),
            signing_kid="eay-ai-core-es256-v1",
            lifetime_seconds=31,
        )


def test_non_p256_private_key_is_rejected(tmp_path: Path) -> None:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    path = tmp_path / "wrong-key.pem"
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    with pytest.raises(JarvisServiceIdentityError):
        JarvisServiceIdentitySigner(
            JarvisServiceIdentitySettings(
                private_key_file=str(path),
                signing_kid="eay-ai-core-es256-v1",
            )
        )


def test_no_general_token_issuance_route_is_added() -> None:
    main_source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "main.py"
    ).read_text(encoding="utf-8")

    assert "/token" not in main_source
    assert "/internal/assert" not in main_source
    assert "issue_tool_execution_assertion" not in main_source
