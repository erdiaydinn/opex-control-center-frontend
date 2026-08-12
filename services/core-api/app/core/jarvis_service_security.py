"""FastAPI authentication dependency for EAY Jarvis service calls."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.internal_identity import (
    InternalAssertionInvalid,
    InternalAssertionUnavailable,
)
from app.core.internal_service_replay import (
    INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS,
    InternalServiceReplayDetected,
    InternalServiceReplayUnavailable,
    RedisInternalServiceReplayGuard,
)
from app.core.jarvis_service_identity import (
    JarvisServiceSettings,
    VerifiedJarvisService,
    get_jarvis_service_settings,
    verify_jarvis_service_assertion,
)
from app.core.resources import redis_client

JARVIS_SERVICE_ASSERTION_HEADER = (
    "X-OPEX-Jarvis-Service-Assertion"
)

_jarvis_service_replay_guard = (
    RedisInternalServiceReplayGuard(
        redis_client,
        key_prefix=(
            "opex:{identity}:jarvis-service-replay"
        ),
    )
)


def _jarvis_service_authentication_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Jarvis service authentication failed",
    )


def _extract_single_assertion_header(
    request: Request,
) -> str:
    header_values = request.headers.getlist(
        JARVIS_SERVICE_ASSERTION_HEADER
    )

    if len(header_values) != 1:
        raise _jarvis_service_authentication_failed()

    token = header_values[0]

    if (
        not token
        or len(token) > 8192
        or token != token.strip()
        or "," in token
        or any(
            character.isspace()
            for character in token
        )
    ):
        raise _jarvis_service_authentication_failed()

    return token


async def require_jarvis_service(
    request: Request,
    settings: Annotated[
        JarvisServiceSettings,
        Depends(get_jarvis_service_settings),
    ],
) -> VerifiedJarvisService:
    """Authenticate independently signed EAY AI Core calls."""

    if not settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )

    token = _extract_single_assertion_header(request)

    try:
        verified = verify_jarvis_service_assertion(
            token,
            settings,
        )
    except InternalAssertionInvalid as exc:
        raise _jarvis_service_authentication_failed() from exc
    except InternalAssertionUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jarvis service authentication unavailable",
        ) from exc

    request.state.jarvis_service = verified
    return verified


async def require_fresh_jarvis_service(
    request: Request,
    settings: Annotated[
        JarvisServiceSettings,
        Depends(get_jarvis_service_settings),
    ],
) -> VerifiedJarvisService:
    """Require a valid and single-use Jarvis machine assertion."""

    verified = await require_jarvis_service(
        request,
        settings,
    )

    ttl_seconds = (
        settings.assertion_max_lifetime_seconds
        + INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS
    )

    try:
        await _jarvis_service_replay_guard.consume(
            assertion_id=verified.assertion_id,
            ttl_seconds=ttl_seconds,
        )
    except InternalServiceReplayDetected as exc:
        request.state.jarvis_service = None
        raise _jarvis_service_authentication_failed() from exc
    except InternalServiceReplayUnavailable as exc:
        request.state.jarvis_service = None
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jarvis service authentication unavailable",
        ) from exc

    return verified
