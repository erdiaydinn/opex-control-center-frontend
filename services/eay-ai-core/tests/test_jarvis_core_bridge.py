from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr

from app.jarvis_core_bridge import (
    DEFAULT_JARVIS_SERVICE_AUDIENCE,
    DEFAULT_JARVIS_SERVICE_ISSUER,
    JARVIS_SERVICE_ASSERTION_HEADER,
    JARVIS_SERVICE_ASSERTION_TYP,
    JARVIS_SERVICE_PURPOSE,
    JARVIS_SERVICE_SUBJECT,
    JarvisCoreAuthorizationClient,
    JarvisCoreAuthorizationProtocolError,
    JarvisCoreAuthorizationUnavailable,
    JarvisCoreBridgeConfigurationError,
    JarvisCoreBridgeSettings,
    JarvisServiceAssertionSigner,
    canonical_arguments_sha256,
    canonical_reason_sha256,
)

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")


def write_private_key(path: Path) -> ec.EllipticCurvePrivateKey:
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    if os.name != "nt":
        path.chmod(0o600)
    return key


def bridge_settings(tmp_path: Path) -> tuple[JarvisCoreBridgeSettings, ec.EllipticCurvePrivateKey]:
    key_path = tmp_path / "jarvis-service-key.pem"
    key = write_private_key(key_path)
    settings = JarvisCoreBridgeSettings(
        environment="test",
        enabled=True,
        core_base_url="http://core-api:8000",
        signing_key_file=str(key_path),
        signing_kid="jarvis-test-1",
        assertion_issuer=DEFAULT_JARVIS_SERVICE_ISSUER,
        assertion_audience=DEFAULT_JARVIS_SERVICE_AUDIENCE,
        assertion_lifetime_seconds=30,
        timeout_seconds=2.0,
    )
    settings.validate()
    return settings, key


def catalog_arguments() -> dict[str, object]:
    return {
        "query": "milk",
        "field": "product",
        "limit": 10,
    }


def authorized_payload(arguments: dict[str, object], reason: str) -> dict[str, object]:
    return {
        "request_id": "request-1",
        "tenant_id": str(TENANT_ID),
        "actor_subject": "user-1",
        "tool": "catalog_query",
        "granted_scopes": ["catalog:read"],
        "authorization_fingerprint": "a" * 64,
        "arguments_sha256": canonical_arguments_sha256(arguments),
        "reason_sha256": canonical_reason_sha256(reason),
    }


class FakeSigner:
    def issue_assertion(self) -> str:
        return "signed-jarvis-service-assertion"


class FakeClient:
    def __init__(self, *, payload: dict[str, object] | None = None, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.error is not None:
            raise self.error
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=self.payload, request=request)


def test_signer_issues_narrow_es256_contract(tmp_path: Path) -> None:
    settings, key = bridge_settings(tmp_path)
    signer = JarvisServiceAssertionSigner(settings)

    token = signer.issue_assertion()
    header = jwt.get_unverified_header(token)
    claims = jwt.decode(
        token,
        key.public_key(),
        algorithms=["ES256"],
        audience=DEFAULT_JARVIS_SERVICE_AUDIENCE,
        issuer=DEFAULT_JARVIS_SERVICE_ISSUER,
    )

    assert header == {
        "alg": "ES256",
        "kid": "jarvis-test-1",
        "typ": JARVIS_SERVICE_ASSERTION_TYP,
    }
    assert set(claims) == {"iss", "aud", "sub", "purpose", "jti", "iat", "nbf", "exp"}
    assert claims["sub"] == JARVIS_SERVICE_SUBJECT
    assert claims["purpose"] == JARVIS_SERVICE_PURPOSE
    assert claims["nbf"] == claims["iat"]
    assert claims["exp"] - claims["iat"] == 30
    UUID(claims["jti"])

    public_jwks = signer.public_jwks()
    public_key = public_jwks["keys"][0]
    assert isinstance(public_key, dict)
    assert public_key["kid"] == "jarvis-test-1"
    assert public_key["alg"] == "ES256"
    assert "d" not in public_key


def test_private_key_environment_material_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EAY_JARVIS_SERVICE_SIGNING_KEY", "do-not-accept")
    with pytest.raises(JarvisCoreBridgeConfigurationError):
        JarvisCoreBridgeSettings.from_environment()


def test_identity_gateway_issuer_and_reserved_audience_are_rejected(tmp_path: Path) -> None:
    settings, _ = bridge_settings(tmp_path)

    with pytest.raises(JarvisCoreBridgeConfigurationError):
        JarvisCoreBridgeSettings(
            **{**settings.__dict__, "assertion_issuer": "opex-identity-gateway"}
        ).validate()

    with pytest.raises(JarvisCoreBridgeConfigurationError):
        JarvisCoreBridgeSettings(
            **{**settings.__dict__, "assertion_audience": "opex-core-preauth"}
        ).validate()


def test_authorization_client_binds_response_to_exact_invocation(tmp_path: Path) -> None:
    settings, _ = bridge_settings(tmp_path)
    arguments = catalog_arguments()
    reason = "catalog lookup for replenishment"
    fake = FakeClient(payload=authorized_payload(arguments, reason))
    client = JarvisCoreAuthorizationClient(
        settings,
        signer=FakeSigner(),  # type: ignore[arg-type]
        client=fake,  # type: ignore[arg-type]
    )

    context = client.authorize(
        grant_token=SecretStr("g" * 43),
        tool="catalog_query",
        arguments=arguments,
        reason=reason,
    )

    assert context.tenant_id == TENANT_ID
    assert context.actor_subject == "user-1"
    assert context.granted_scopes == ("catalog:read",)
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "http://core-api:8000/internal/ai/tool-executions/authorize"
    assert call["headers"] == {
        JARVIS_SERVICE_ASSERTION_HEADER: "signed-jarvis-service-assertion"
    }
    assert call["json"]["grant_token"] == "g" * 43  # type: ignore[index]


def test_authorization_client_rejects_scope_widening(tmp_path: Path) -> None:
    settings, _ = bridge_settings(tmp_path)
    arguments = catalog_arguments()
    reason = "catalog lookup"
    payload = authorized_payload(arguments, reason)
    payload["granted_scopes"] = ["catalog:read", "legal:read"]
    fake = FakeClient(payload=payload)
    client = JarvisCoreAuthorizationClient(
        settings,
        signer=FakeSigner(),  # type: ignore[arg-type]
        client=fake,  # type: ignore[arg-type]
    )

    with pytest.raises(JarvisCoreAuthorizationProtocolError):
        client.authorize(
            grant_token=SecretStr("g" * 43),
            tool="catalog_query",
            arguments=arguments,
            reason=reason,
        )


def test_authorization_client_rejects_argument_or_reason_mismatch(tmp_path: Path) -> None:
    settings, _ = bridge_settings(tmp_path)
    arguments = catalog_arguments()
    reason = "catalog lookup"

    for field in ("arguments_sha256", "reason_sha256"):
        payload = authorized_payload(arguments, reason)
        payload[field] = "b" * 64
        fake = FakeClient(payload=payload)
        client = JarvisCoreAuthorizationClient(
            settings,
            signer=FakeSigner(),  # type: ignore[arg-type]
            client=fake,  # type: ignore[arg-type]
        )
        with pytest.raises(JarvisCoreAuthorizationProtocolError):
            client.authorize(
                grant_token=SecretStr("g" * 43),
                tool="catalog_query",
                arguments=arguments,
                reason=reason,
            )


def test_network_failure_is_fail_closed_and_never_retried(tmp_path: Path) -> None:
    settings, _ = bridge_settings(tmp_path)
    request = httpx.Request("POST", "http://core-api:8000/internal/ai/tool-executions/authorize")
    fake = FakeClient(error=httpx.ConnectError("down", request=request))
    client = JarvisCoreAuthorizationClient(
        settings,
        signer=FakeSigner(),  # type: ignore[arg-type]
        client=fake,  # type: ignore[arg-type]
    )

    with pytest.raises(JarvisCoreAuthorizationUnavailable):
        client.authorize(
            grant_token=SecretStr("g" * 43),
            tool="catalog_query",
            arguments=catalog_arguments(),
            reason="catalog lookup",
        )

    assert len(fake.calls) == 1
