from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.core.jarvis_service_security as security
from app.core.internal_identity import InternalAssertionInvalid
from app.core.internal_service_replay import (
    INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS,
    InternalServiceReplayDetected,
    InternalServiceReplayUnavailable,
)
from app.core.jarvis_service_identity import (
    JarvisServiceSettings,
    VerifiedJarvisService,
)


class RecordingReplayGuard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def consume(
        self,
        *,
        assertion_id: str,
        ttl_seconds: int,
    ) -> None:
        self.calls.append(
            (assertion_id, ttl_seconds)
        )


class ReplayDetectedGuard(RecordingReplayGuard):
    async def consume(
        self,
        *,
        assertion_id: str,
        ttl_seconds: int,
    ) -> None:
        del assertion_id, ttl_seconds
        raise InternalServiceReplayDetected(
            "replay"
        )


class ReplayUnavailableGuard(RecordingReplayGuard):
    async def consume(
        self,
        *,
        assertion_id: str,
        ttl_seconds: int,
    ) -> None:
        del assertion_id, ttl_seconds
        raise InternalServiceReplayUnavailable(
            "redis unavailable"
        )


def enabled_settings() -> JarvisServiceSettings:
    return JarvisServiceSettings(
        enabled=True,
        assertion_jwks_file="test-jarvis-jwks.json",
    )


def request_with_headers(
    headers: list[tuple[bytes, bytes]],
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/internal/ai/tool-executions/authorize",
            "raw_path": b"/internal/ai/tool-executions/authorize",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("core-api", 8000),
        }
    )


def valid_request() -> Request:
    return request_with_headers(
        [
            (
                b"x-opex-jarvis-service-assertion",
                b"opaque-token",
            )
        ]
    )


def verified_service() -> VerifiedJarvisService:
    return VerifiedJarvisService(
        service_subject="eay-ai-core",
        assertion_id="jarvis-assertion-0001",
    )


def install_valid_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def verify(
        token: str,
        settings: JarvisServiceSettings,
    ) -> VerifiedJarvisService:
        del settings
        assert token == "opaque-token"
        return verified_service()

    monkeypatch.setattr(
        security,
        "verify_jarvis_service_assertion",
        verify,
    )


@pytest.mark.asyncio
async def test_disabled_jarvis_service_boundary_is_hidden() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await security.require_jarvis_service(
            valid_request(),
            JarvisServiceSettings(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Not Found"


@pytest.mark.asyncio
async def test_valid_jarvis_header_sets_machine_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_valid_verifier(monkeypatch)
    request = valid_request()

    verified = await security.require_jarvis_service(
        request,
        enabled_settings(),
    )

    assert verified == verified_service()
    assert request.state.jarvis_service == verified


@pytest.mark.asyncio
async def test_duplicate_or_coalesced_jarvis_header_is_rejected() -> None:
    duplicate = request_with_headers(
        [
            (
                b"x-opex-jarvis-service-assertion",
                b"token-one",
            ),
            (
                b"x-opex-jarvis-service-assertion",
                b"token-two",
            ),
        ]
    )

    with pytest.raises(HTTPException) as duplicate_info:
        await security.require_jarvis_service(
            duplicate,
            enabled_settings(),
        )

    assert duplicate_info.value.status_code == 401

    coalesced = request_with_headers(
        [
            (
                b"x-opex-jarvis-service-assertion",
                b"token-one,token-two",
            )
        ]
    )

    with pytest.raises(HTTPException) as coalesced_info:
        await security.require_jarvis_service(
            coalesced,
            enabled_settings(),
        )

    assert coalesced_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verifier_failure_is_generic_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(
        token: str,
        settings: JarvisServiceSettings,
    ) -> VerifiedJarvisService:
        del token, settings
        raise InternalAssertionInvalid(
            "specific cryptographic reason"
        )

    monkeypatch.setattr(
        security,
        "verify_jarvis_service_assertion",
        reject,
    )

    with pytest.raises(HTTPException) as exc_info:
        await security.require_jarvis_service(
            valid_request(),
            enabled_settings(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == (
        "Jarvis service authentication failed"
    )
    assert "cryptographic" not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_fresh_jarvis_assertion_consumes_replay_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_valid_verifier(monkeypatch)
    guard = RecordingReplayGuard()
    monkeypatch.setattr(
        security,
        "_jarvis_service_replay_guard",
        guard,
    )
    settings = enabled_settings()

    verified = await security.require_fresh_jarvis_service(
        valid_request(),
        settings,
    )

    assert verified == verified_service()
    assert guard.calls == [
        (
            "jarvis-assertion-0001",
            settings.assertion_max_lifetime_seconds
            + INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS,
        )
    ]


@pytest.mark.asyncio
async def test_replayed_jarvis_assertion_is_generic_401_and_clears_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_valid_verifier(monkeypatch)
    monkeypatch.setattr(
        security,
        "_jarvis_service_replay_guard",
        ReplayDetectedGuard(),
    )
    request = valid_request()

    with pytest.raises(HTTPException) as exc_info:
        await security.require_fresh_jarvis_service(
            request,
            enabled_settings(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == (
        "Jarvis service authentication failed"
    )
    assert request.state.jarvis_service is None


@pytest.mark.asyncio
async def test_replay_authority_failure_is_503_and_clears_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_valid_verifier(monkeypatch)
    monkeypatch.setattr(
        security,
        "_jarvis_service_replay_guard",
        ReplayUnavailableGuard(),
    )
    request = valid_request()

    with pytest.raises(HTTPException) as exc_info:
        await security.require_fresh_jarvis_service(
            request,
            enabled_settings(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "Jarvis service authentication unavailable"
    )
    assert request.state.jarvis_service is None
