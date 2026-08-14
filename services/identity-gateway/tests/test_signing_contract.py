import json
from pathlib import Path
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.security import (
    GatewaySettings,
    IdentitySigner,
    INTERNAL_ASSERTION_TYP,
    INTERNAL_SERVICE_ASSERTION_TYP,
)


TENANT_ID = UUID(
    "00000000-0000-0000-0000-00000000dd01"
)

MEMBERSHIP_ID = UUID(
    "00000000-0000-0000-0000-00000000dd11"
)


def _settings(
    tmp_path,
):
    key = ec.generate_private_key(
        ec.SECP256R1()
    )

    path = (
        tmp_path
        / "private.pem"
    )

    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    return GatewaySettings(
        environment="test",
        issuer="opex-identity-gateway",
        audience="opex-core-api",
        signing_key_file=str(path),
        signing_kid="test-es256-v1",
        assertion_lifetime_seconds=30,
    )


def test_public_jwks_never_contains_private_key_material(
    tmp_path,
):
    signer = IdentitySigner(
        _settings(tmp_path)
    )

    jwks = signer.public_jwks()

    assert len(
        jwks["keys"]
    ) == 1

    key = jwks["keys"][0]

    assert key["kty"] == "EC"
    assert key["crv"] == "P-256"
    assert key["alg"] == "ES256"

    for private_field in (
        "d",
        "p",
        "q",
        "dp",
        "dq",
        "qi",
        "oth",
        "k",
    ):
        assert (
            private_field
            not in key
        )


def test_internal_assertion_contract_is_identity_only(
    tmp_path,
):
    settings = _settings(
        tmp_path
    )

    signer = IdentitySigner(
        settings
    )

    token = (
        signer.issue_internal_assertion(
            tenant_id=TENANT_ID,
            membership_id=MEMBERSHIP_ID,
        )
    )

    header = jwt.get_unverified_header(
        token
    )

    assert header == {
        "alg": "ES256",
        "kid": "test-es256-v1",
        "typ": INTERNAL_ASSERTION_TYP,
    }

    public_key = jwt.PyJWK.from_dict(
        signer.public_jwks()[
            "keys"
        ][0]
    ).key

    claims = jwt.decode(
        token,
        public_key,
        algorithms=[
            "ES256",
        ],
        audience="opex-core-api",
        issuer="opex-identity-gateway",
    )

    assert set(claims) == {
        "iss",
        "aud",
        "sub",
        "tenant_id",
        "jti",
        "iat",
        "nbf",
        "exp",
    }

    assert claims[
        "tenant_id"
    ] == str(TENANT_ID)

    assert claims[
        "sub"
    ] == str(MEMBERSHIP_ID)

    assert (
        claims["exp"]
        - claims["iat"]
        == 30
    )

    assert claims[
        "nbf"
    ] == claims["iat"]


def test_main_module_has_no_token_issuance_route():
    source = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath(
            "app",
            "main.py",
        )
        .read_text(
            encoding="utf-8"
        )
    )

    forbidden_routes = (
        '@app.post("/internal',
        '@app.get("/internal/assert',
        '@app.post("/token',
        '@app.get("/token',
    )

    for marker in forbidden_routes:
        assert marker not in source


def test_service_assertion_is_strictly_service_only(
    tmp_path,
):
    settings = _settings(
        tmp_path
    )

    signer = IdentitySigner(
        settings
    )

    token = (
        signer.
        issue_internal_service_assertion()
    )

    header = jwt.get_unverified_header(
        token
    )

    assert header == {
        "alg": "ES256",
        "kid": "test-es256-v1",
        "typ":
            INTERNAL_SERVICE_ASSERTION_TYP,
    }

    public_key = jwt.PyJWK.from_dict(
        signer.public_jwks()[
            "keys"
        ][0]
    ).key

    claims = jwt.decode(
        token,
        public_key,
        algorithms=[
            "ES256",
        ],
        audience="opex-core-preauth",
        issuer="opex-identity-gateway",
    )

    assert set(
        claims
    ) == {
        "iss",
        "aud",
        "sub",
        "purpose",
        "jti",
        "iat",
        "nbf",
        "exp",
    }

    assert claims[
        "sub"
    ] == "identity-gateway"

    assert claims[
        "aud"
    ] == "opex-core-preauth"

    assert claims[
        "purpose"
    ] == "preauth"

    assert (
        "tenant_id"
        not in claims
    )

    assert (
        "membership_id"
        not in claims
    )

    assert (
        "roles"
        not in claims
    )

    assert (
        "permissions"
        not in claims
    )

    assert (
        claims["nbf"]
        == claims["iat"]
    )


def test_identity_and_service_token_types_are_distinct(
    tmp_path,
):
    signer = IdentitySigner(
        _settings(
            tmp_path
        )
    )

    identity_token = (
        signer.issue_internal_assertion(
            tenant_id=TENANT_ID,
            membership_id=MEMBERSHIP_ID,
        )
    )

    service_token = (
        signer.
        issue_internal_service_assertion()
    )

    assert (
        jwt.get_unverified_header(
            identity_token
        )["typ"]
        == INTERNAL_ASSERTION_TYP
    )

    assert (
        jwt.get_unverified_header(
            service_token
        )["typ"]
        == INTERNAL_SERVICE_ASSERTION_TYP
    )

    assert (
        INTERNAL_ASSERTION_TYP
        != INTERNAL_SERVICE_ASSERTION_TYP
    )
