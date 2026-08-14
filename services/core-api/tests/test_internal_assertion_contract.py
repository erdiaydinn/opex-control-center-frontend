"""Adversarial tests for OPEX internal identity assertions."""

import json
import time
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.core.config import Settings
from app.core.internal_identity import (
    INTERNAL_ASSERTION_TYP,
    INTERNAL_SERVICE_ASSERTION_TYP,
    InternalAssertionInvalid,
    verify_internal_identity_assertion,
    verify_internal_service_assertion,
)

ISSUER = "opex-identity-gateway"
AUDIENCE = "opex-core-api"
SERVICE_AUDIENCE = "opex-core-preauth"

TENANT_ID = UUID(
    "00000000-0000-0000-0000-00000000cc01"
)

MEMBERSHIP_ID = UUID(
    "00000000-0000-0000-0000-00000000cc11"
)

KID = "identity-key-2026-01"


def build_key_material():
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

    return (
        private_key,
        public_jwk,
    )


def make_settings(
    tmp_path,
    public_jwk,
):
    jwks_path = (
        tmp_path
        / "internal-jwks.json"
    )

    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    public_jwk,
                ],
            }
        ),
        encoding="utf-8",
    )

    return Settings(
        environment="test",
        auth_mode="internal_assertion",
        internal_assertion_issuer=ISSUER,
        internal_assertion_audience=AUDIENCE,
        internal_service_assertion_audience=SERVICE_AUDIENCE,
        internal_assertion_jwks_file=str(
            jwks_path
        ),
        internal_assertion_algorithms="ES256",
        internal_assertion_max_lifetime_seconds=60,
    )


def claims(
    *,
    lifetime=30,
):
    now = int(
        time.time()
    )

    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(
            MEMBERSHIP_ID
        ),
        "tenant_id": str(
            TENANT_ID
        ),
        "jti": (
            "11111111-1111-4111-"
            "8111-111111111111"
        ),
        "iat": now,
        "nbf": now,
        "exp": now + lifetime,
    }



def service_claims(
    *,
    lifetime=30,
):
    now = int(
        time.time()
    )

    return {
        "iss":
            ISSUER,
        "aud":
            SERVICE_AUDIENCE,
        "sub":
            "identity-gateway",
        "purpose":
            "preauth",
        "jti":
            "service-assertion-0001",
        "iat":
            now,
        "nbf":
            now,
        "exp":
            now + lifetime,
    }


def sign(
    private_key,
    payload,
    *,
    kid=KID,
    typ=INTERNAL_ASSERTION_TYP,
):
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={
            "kid": kid,
            "typ": typ,
        },
    )


def test_valid_internal_assertion_contains_identity_only(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    verified = (
        verify_internal_identity_assertion(
            sign(
                private_key,
                claims(),
            ),
            settings,
        )
    )

    assert verified.tenant_id == TENANT_ID
    assert (
        verified.membership_id
        == MEMBERSHIP_ID
    )


def test_unknown_kid_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    token = sign(
        private_key,
        claims(),
        kid="attacker-key",
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            token,
            settings,
        )


def test_wrong_token_type_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    token = sign(
        private_key,
        claims(),
        typ="JWT",
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            token,
            settings,
        )


def test_algorithm_downgrade_is_rejected(
    tmp_path,
) -> None:
    _, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = claims()

    token = jwt.encode(
        payload,
        'eay-phase1-internal-assertion-test-key-material-2026',
        algorithm="HS256",
        headers={
            "kid": KID,
            "typ": INTERNAL_ASSERTION_TYP,
        },
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            token,
            settings,
        )


def test_authorization_claim_smuggling_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = claims()

    payload["roles"] = [
        "super_admin",
    ]

    token = sign(
        private_key,
        payload,
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            token,
            settings,
        )


def test_provider_claim_smuggling_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = claims()

    payload["provider_id"] = (
        "00000000-0000-0000-"
        "0000-00000000ffff"
    )

    token = sign(
        private_key,
        payload,
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            token,
            settings,
        )


def test_wrong_issuer_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = claims()

    payload["iss"] = (
        "attacker-identity-gateway"
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            sign(
                private_key,
                payload,
            ),
            settings,
        )


def test_wrong_audience_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = claims()

    payload["aud"] = (
        "some-other-service"
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            sign(
                private_key,
                payload,
            ),
            settings,
        )


def test_overlong_lifetime_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            sign(
                private_key,
                claims(
                    lifetime=61,
                ),
            ),
            settings,
        )


def test_untrusted_header_extension_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    token = jwt.encode(
        claims(),
        private_key,
        algorithm="ES256",
        headers={
            "kid": KID,
            "typ": INTERNAL_ASSERTION_TYP,
            "jku": (
                "https://attacker.example/"
                "jwks.json"
            ),
        },
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            token,
            settings,
        )


def test_internal_mode_requires_trusted_jwks_file() -> None:
    with pytest.raises(
        ValueError,
        match="configuration is incomplete",
    ):
        Settings(
            environment="test",
            auth_mode="internal_assertion",
            internal_assertion_issuer=ISSUER,
            internal_assertion_audience=AUDIENCE,
            internal_assertion_jwks_file="",
        )


def test_valid_internal_service_assertion_is_service_only(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    token = sign(
        private_key,
        service_claims(),
        typ=(
            INTERNAL_SERVICE_ASSERTION_TYP
        ),
    )

    verified = (
        verify_internal_service_assertion(
            token,
            settings,
        )
    )

    assert (
        verified.service_subject
        == "identity-gateway"
    )

    assert (
        verified.assertion_id
        == "service-assertion-0001"
    )


def test_identity_assertion_cannot_authenticate_as_service(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    token = sign(
        private_key,
        claims(),
        typ=INTERNAL_ASSERTION_TYP,
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_service_assertion(
            token,
            settings,
        )


def test_service_assertion_cannot_authenticate_as_identity(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    token = sign(
        private_key,
        service_claims(),
        typ=(
            INTERNAL_SERVICE_ASSERTION_TYP
        ),
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_identity_assertion(
            token,
            settings,
        )


@pytest.mark.parametrize(
    "forbidden_claim,value",
    [
        (
            "tenant_id",
            str(TENANT_ID),
        ),
        (
            "membership_id",
            str(MEMBERSHIP_ID),
        ),
        (
            "roles",
            [
                "super_admin",
            ],
        ),
        (
            "permissions",
            [
                "*",
            ],
        ),
        (
            "provider_id",
            "attacker-provider",
        ),
        (
            "email",
            "attacker@example.invalid",
        ),
    ],
)
def test_service_assertion_rejects_authority_claim_smuggling(
    tmp_path,
    forbidden_claim,
    value,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = (
        service_claims()
    )

    payload[
        forbidden_claim
    ] = value

    token = sign(
        private_key,
        payload,
        typ=(
            INTERNAL_SERVICE_ASSERTION_TYP
        ),
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_service_assertion(
            token,
            settings,
        )


def test_service_assertion_wrong_subject_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = (
        service_claims()
    )

    payload[
        "sub"
    ] = "attacker-service"

    token = sign(
        private_key,
        payload,
        typ=(
            INTERNAL_SERVICE_ASSERTION_TYP
        ),
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_service_assertion(
            token,
            settings,
        )



def test_service_assertion_user_audience_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = build_key_material()

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = service_claims()
    payload["aud"] = AUDIENCE

    token = sign(
        private_key,
        payload,
        typ=INTERNAL_SERVICE_ASSERTION_TYP,
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_service_assertion(
            token,
            settings,
        )


def test_service_assertion_wrong_purpose_is_rejected(
    tmp_path,
) -> None:
    private_key, public_jwk = build_key_material()

    settings = make_settings(
        tmp_path,
        public_jwk,
    )

    payload = service_claims()
    payload["purpose"] = "administration"

    token = sign(
        private_key,
        payload,
        typ=INTERNAL_SERVICE_ASSERTION_TYP,
    )

    with pytest.raises(
        InternalAssertionInvalid
    ):
        verify_internal_service_assertion(
            token,
            settings,
        )


def test_service_and_user_audiences_cannot_be_equal() -> None:
    with pytest.raises(
        ValueError,
        match="must differ",
    ):
        Settings(
            internal_assertion_audience="same-audience",
            internal_service_assertion_audience="same-audience",
        )
