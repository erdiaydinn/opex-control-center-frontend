"""Adversarial tests for the internal service-auth transport boundary."""

import asyncio
import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from jwt.algorithms import ECAlgorithm
from starlette.requests import Request

import app.core.security as security_module
from app.core.config import Settings
from app.core.internal_identity import (
    INTERNAL_SERVICE_ASSERTION_TYP,
)
from app.core.internal_service_replay import (
    InternalServiceReplayDetected,
    InternalServiceReplayUnavailable,
)
from app.core.security import (
    INTERNAL_SERVICE_ASSERTION_HEADER,
    require_fresh_internal_service,
    require_internal_service,
)

ISSUER = "opex-identity-gateway"
USER_AUDIENCE = "opex-core-api"
SERVICE_AUDIENCE = "opex-core-preauth"
KID = "service-auth-test-key"


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

    return private_key, public_jwk


def make_settings(
    tmp_path,
    public_jwk,
    *,
    missing_jwks=False,
):
    jwks_path = (
        tmp_path
        / "service-auth-jwks.json"
    )

    if not missing_jwks:
        jwks_path.write_text(
            json.dumps(
                {
                    "keys": [
                        public_jwk,
                    ]
                }
            ),
            encoding="utf-8",
        )

    # Intentionally OIDC:
    # service authentication must remain independently usable
    # before the global BFF/internal-assertion cutover.
    return Settings(
        environment="test",
        auth_mode="oidc",
        oidc_issuer=(
            "https://idp.example.test"
        ),
        oidc_audience=USER_AUDIENCE,
        oidc_jwks_url=(
            "https://idp.example.test/jwks"
        ),
        internal_assertion_issuer=ISSUER,
        internal_assertion_audience=(
            USER_AUDIENCE
        ),
        internal_service_assertion_audience=(
            SERVICE_AUDIENCE
        ),
        internal_assertion_jwks_file=str(
            jwks_path
        ),
        internal_assertion_algorithms="ES256",
        internal_assertion_max_lifetime_seconds=60,
    )


def service_claims(
    *,
    audience=SERVICE_AUDIENCE,
):
    now = int(
        time.time()
    )

    return {
        "iss": ISSUER,
        "aud": audience,
        "sub": "identity-gateway",
        "purpose": "preauth",
        "jti": "service-assertion-0001",
        "iat": now,
        "nbf": now,
        "exp": now + 30,
    }


def sign(
    private_key,
    payload,
):
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={
            "kid": KID,
            "typ":
                INTERNAL_SERVICE_ASSERTION_TYP,
        },
    )


def request_with_headers(
    headers,
):
    path = (
        "/internal/v1/preauth/providers"
    )

    scope = {
        "type": "http",
        "asgi": {
            "version": "3.0",
        },
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(
            "ascii"
        ),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (
                name.lower().encode(
                    "ascii"
                ),
                value.encode(
                    "ascii"
                ),
            )
            for name, value
            in headers
        ],
        "client": (
            "172.31.255.10",
            41000,
        ),
        "server": (
            "core-api",
            8000,
        ),
    }

    return Request(
        scope
    )


def invoke(
    request,
    settings,
):
    return asyncio.run(
        require_internal_service(
            request,
            settings,
        )
    )



def invoke_fresh(
    request,
    settings,
):
    return asyncio.run(
        require_fresh_internal_service(
            request,
            settings,
        )
    )


def expect_fresh_http_error(
    request,
    settings,
    *,
    status_code,
    detail,
):
    try:
        invoke_fresh(
            request,
            settings,
        )

    except HTTPException as exc:
        assert (
            exc.status_code
            == status_code
        )

        assert (
            exc.detail
            == detail
        )

        return

    raise AssertionError(
        "Fresh service request unexpectedly authenticated"
    )


def expect_http_error(
    request,
    settings,
    *,
    status_code,
    detail,
):
    try:
        invoke(
            request,
            settings,
        )

    except HTTPException as exc:
        assert (
            exc.status_code
            == status_code
        )

        assert (
            exc.detail
            == detail
        )

        return

    raise AssertionError(
        "Request unexpectedly authenticated"
    )


def valid_material(
    tmp_path,
):
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
    )

    return (
        private_key,
        public_jwk,
        settings,
        token,
    )


def test_valid_dedicated_service_header_is_accepted(
    tmp_path,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    request = request_with_headers(
        [
            (
                INTERNAL_SERVICE_ASSERTION_HEADER,
                token,
            ),
        ]
    )

    verified = invoke(
        request,
        settings,
    )

    assert (
        verified.service_subject
        == "identity-gateway"
    )

    assert (
        request.state.internal_service
        == verified
    )


def test_missing_service_header_fails_closed(
    tmp_path,
) -> None:
    (
        _,
        _,
        settings,
        _,
    ) = valid_material(
        tmp_path
    )

    expect_http_error(
        request_with_headers([]),
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )


def test_authorization_bearer_cannot_substitute_for_service_header(
    tmp_path,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    expect_http_error(
        request_with_headers(
            [
                (
                    "Authorization",
                    "Bearer " + token,
                ),
            ]
        ),
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )


def test_duplicate_service_headers_are_rejected(
    tmp_path,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    expect_http_error(
        request_with_headers(
            [
                (
                    INTERNAL_SERVICE_ASSERTION_HEADER,
                    token,
                ),
                (
                    INTERNAL_SERVICE_ASSERTION_HEADER,
                    token,
                ),
            ]
        ),
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )


def test_proxy_coalesced_duplicate_header_is_rejected(
    tmp_path,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    expect_http_error(
        request_with_headers(
            [
                (
                    INTERNAL_SERVICE_ASSERTION_HEADER,
                    token + "," + token,
                ),
            ]
        ),
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )


def test_service_header_whitespace_smuggling_is_rejected(
    tmp_path,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    expect_http_error(
        request_with_headers(
            [
                (
                    INTERNAL_SERVICE_ASSERTION_HEADER,
                    " " + token,
                ),
            ]
        ),
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )


def test_malformed_service_assertion_maps_to_generic_401(
    tmp_path,
) -> None:
    (
        _,
        _,
        settings,
        _,
    ) = valid_material(
        tmp_path
    )

    expect_http_error(
        request_with_headers(
            [
                (
                    INTERNAL_SERVICE_ASSERTION_HEADER,
                    "attacker-not-a-jwt",
                ),
            ]
        ),
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )


def test_user_audience_service_token_is_rejected_by_dependency(
    tmp_path,
) -> None:
    (
        private_key,
        _,
        settings,
        _,
    ) = valid_material(
        tmp_path
    )

    token = sign(
        private_key,
        service_claims(
            audience=USER_AUDIENCE,
        ),
    )

    expect_http_error(
        request_with_headers(
            [
                (
                    INTERNAL_SERVICE_ASSERTION_HEADER,
                    token,
                ),
            ]
        ),
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )


def test_unavailable_trusted_jwks_fails_closed_as_503(
    tmp_path,
) -> None:
    private_key, public_jwk = (
        build_key_material()
    )

    settings = make_settings(
        tmp_path,
        public_jwk,
        missing_jwks=True,
    )

    token = sign(
        private_key,
        service_claims(),
    )

    expect_http_error(
        request_with_headers(
            [
                (
                    INTERNAL_SERVICE_ASSERTION_HEADER,
                    token,
                ),
            ]
        ),
        settings,
        status_code=503,
        detail=(
            "Internal service authentication unavailable"
        ),
    )


class AcceptOnceReplayGuard:
    def __init__(self):
        self.seen = set()
        self.calls = []

    async def consume(
        self,
        *,
        assertion_id,
        ttl_seconds,
    ):
        self.calls.append(
            (
                assertion_id,
                ttl_seconds,
            )
        )

        if assertion_id in self.seen:
            raise (
                InternalServiceReplayDetected(
                    "replay"
                )
            )

        self.seen.add(
            assertion_id
        )


class UnavailableReplayGuard:
    async def consume(
        self,
        *,
        assertion_id,
        ttl_seconds,
    ):
        raise (
            InternalServiceReplayUnavailable(
                "unavailable"
            )
        )


def test_fresh_service_assertion_is_consumed_once(
    tmp_path,
    monkeypatch,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    guard = AcceptOnceReplayGuard()

    monkeypatch.setattr(
        security_module,
        "_internal_service_replay_guard",
        guard,
    )

    request = request_with_headers(
        [
            (
                INTERNAL_SERVICE_ASSERTION_HEADER,
                token,
            ),
        ]
    )

    verified = invoke_fresh(
        request,
        settings,
    )

    assert (
        verified.assertion_id
        == "service-assertion-0001"
    )

    assert guard.calls == [
        (
            "service-assertion-0001",
            70,
        )
    ]


def test_same_service_assertion_replay_is_generic_401(
    tmp_path,
    monkeypatch,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    guard = AcceptOnceReplayGuard()

    monkeypatch.setattr(
        security_module,
        "_internal_service_replay_guard",
        guard,
    )

    first = request_with_headers(
        [
            (
                INTERNAL_SERVICE_ASSERTION_HEADER,
                token,
            ),
        ]
    )

    invoke_fresh(
        first,
        settings,
    )

    second = request_with_headers(
        [
            (
                INTERNAL_SERVICE_ASSERTION_HEADER,
                token,
            ),
        ]
    )

    expect_fresh_http_error(
        second,
        settings,
        status_code=401,
        detail=(
            "Internal service authentication failed"
        ),
    )

    assert (
        second.state.internal_service
        is None
    )


def test_replay_authority_outage_is_fail_closed_503(
    tmp_path,
    monkeypatch,
) -> None:
    (
        _,
        _,
        settings,
        token,
    ) = valid_material(
        tmp_path
    )

    monkeypatch.setattr(
        security_module,
        "_internal_service_replay_guard",
        UnavailableReplayGuard(),
    )

    request = request_with_headers(
        [
            (
                INTERNAL_SERVICE_ASSERTION_HEADER,
                token,
            ),
        ]
    )

    expect_fresh_http_error(
        request,
        settings,
        status_code=503,
        detail=(
            "Internal service authentication unavailable"
        ),
    )

    assert (
        request.state.internal_service
        is None
    )
