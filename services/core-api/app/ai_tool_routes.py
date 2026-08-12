"""Tenant-safe Jarvis broker and internal execution authorization routes."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_tool_authorization import (
    TOOL_REQUIRED_SCOPES,
    AiToolAccessDenied,
    AiToolAuthorizationError,
    AiToolName,
    AiToolPermissionScopeUnsupported,
    derive_ai_tool_capability,
)
from app.core.ai_tool_grants import (
    AiToolGrantBindingMismatch,
    AiToolGrantInvalid,
    AiToolGrantReplayOrExpired,
    AiToolGrantUnavailable,
    RedisAiToolGrantStore,
    canonical_arguments_sha256,
    canonical_reason_sha256,
)
from app.core.audit import build_audit_event
from app.core.jarvis_execution_broker import (
    BrokerToolExecutionResult,
    JarvisExecutionBroker,
    JarvisExecutionBrokerContractError,
    JarvisExecutionBrokerDenied,
    JarvisExecutionBrokerIndeterminate,
    JarvisExecutionBrokerSettings,
    JarvisExecutionBrokerUnavailable,
)
from app.core.jarvis_execution_idempotency import (
    JarvisIdempotencyConflict,
    JarvisIdempotencyInvalid,
    JarvisIdempotencyReplay,
    JarvisIdempotencyUnavailable,
    PostgresJarvisExecutionIdempotencyStore,
    build_execution_request_fingerprint,
    validate_idempotency_key,
)
from app.core.jarvis_service_identity import VerifiedJarvisService
from app.core.jarvis_service_security import require_fresh_jarvis_service
from app.core.resources import engine, redis_client, write_audit_event
from app.core.security import Principal, get_current_principal

logger = logging.getLogger(__name__)
router = APIRouter()
_ai_tool_grant_store = RedisAiToolGrantStore(redis_client)
_jarvis_execution_broker_settings = JarvisExecutionBrokerSettings()
_jarvis_execution_broker = JarvisExecutionBroker(
    _jarvis_execution_broker_settings
)
_jarvis_idempotency_store = PostgresJarvisExecutionIdempotencyStore(
    engine
)


class AiToolExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: AiToolName
    arguments: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)


class InternalAiToolAuthorizationRequest(BaseModel):
    grant_token: str = Field(min_length=32, max_length=256)
    tool: AiToolName
    arguments: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)


class InternalAiToolAuthorizationResponse(BaseModel):
    request_id: str
    tenant_id: str
    actor_subject: str
    tool: AiToolName
    granted_scopes: tuple[str, ...]
    authorization_fingerprint: str
    arguments_sha256: str
    reason_sha256: str


def _ai_tool_access_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="AI tool access denied",
    )


def _ai_tool_grant_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="AI tool grant authentication failed",
    )


def _ai_tool_runtime_unavailable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


def _require_idempotency_key(request: Request) -> str:
    values = request.headers.getlist("idempotency-key")
    if len(values) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one Idempotency-Key header is required",
        )
    try:
        return validate_idempotency_key(values[0])
    except JarvisIdempotencyInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is invalid",
        ) from exc


def _broker_execution_policy() -> dict[str, object]:
    return {
        "contract": "jarvis-broker-v1",
        "execute": True,
        "maximum_bytes_billed": (
            _jarvis_execution_broker_settings.maximum_bytes_billed
        ),
        "tool_timeout_ms": _jarvis_execution_broker_settings.tool_timeout_ms,
        "max_rows": _jarvis_execution_broker_settings.max_rows,
    }


async def _release_reserved_idempotency(
    *,
    capability,
    idempotency_key: str,
    request_fingerprint: str,
) -> None:
    try:
        await _jarvis_idempotency_store.release_reserved(
            tenant_id=capability.tenant_id,
            actor_subject=capability.actor_subject,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
    except JarvisIdempotencyUnavailable:
        # Keeping a stale reserved record is safer than accidentally allowing
        # another execution under the same key.
        logger.warning(
            "Jarvis reserved idempotency state could not be released",
            exc_info=True,
        )


async def _finalize_dispatched_idempotency(
    *,
    capability,
    idempotency_key: str,
    request_fingerprint: str,
    new_state: str,
) -> None:
    try:
        await _jarvis_idempotency_store.transition(
            tenant_id=capability.tenant_id,
            actor_subject=capability.actor_subject,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            expected_state="dispatched",
            new_state=new_state,
        )
    except JarvisIdempotencyUnavailable:
        # `dispatched` was durably committed before network I/O. Leaving that
        # state in place still blocks duplicate execution until expiry.
        logger.warning(
            "Jarvis dispatched idempotency state could not be finalized",
            exc_info=True,
        )


@router.post(
    "/v1/ai/tool-executions",
    response_model=BrokerToolExecutionResult,
    tags=["ai"],
)
async def execute_ai_tool(
    payload: AiToolExecutionRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(get_current_principal),
    ],
) -> BrokerToolExecutionResult:
    """Broker one governed invocation with durable request idempotency."""

    idempotency_key = _require_idempotency_key(request)

    try:
        _jarvis_execution_broker.require_enabled()
    except JarvisExecutionBrokerUnavailable as exc:
        raise _ai_tool_runtime_unavailable(
            "AI tool execution broker is unavailable"
        ) from exc

    try:
        capability = derive_ai_tool_capability(
            principal,
            tool=payload.tool,
        )
    except (
        AiToolAccessDenied,
        AiToolPermissionScopeUnsupported,
    ) as exc:
        raise _ai_tool_access_denied() from exc
    except AiToolAuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI tool request is invalid",
        ) from exc

    try:
        arguments_sha256 = canonical_arguments_sha256(payload.arguments)
        reason_sha256 = canonical_reason_sha256(payload.reason)
        request_fingerprint = build_execution_request_fingerprint(
            capability,
            arguments_sha256=arguments_sha256,
            reason_sha256=reason_sha256,
            execution_policy=_broker_execution_policy(),
        )
    except (AiToolGrantInvalid, JarvisIdempotencyInvalid) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI tool request is invalid",
        ) from exc

    try:
        await _jarvis_idempotency_store.reserve(
            tenant_id=capability.tenant_id,
            actor_subject=capability.actor_subject,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
    except JarvisIdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key conflicts with another AI tool request",
        ) from exc
    except JarvisIdempotencyReplay as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "AI tool request already claimed this Idempotency-Key; "
                "do not retry automatically"
            ),
        ) from exc
    except JarvisIdempotencyUnavailable as exc:
        raise _ai_tool_runtime_unavailable(
            "AI tool idempotency authority is unavailable"
        ) from exc

    request_event = build_audit_event(
        request_id=request.state.request_id,
        actor=capability.actor_subject,
        tenant_id=str(capability.tenant_id),
        method="POST",
        path="/v1/ai/tool-executions",
        status_code=status.HTTP_200_OK,
        action="ai_tool_execution_requested",
        metadata={
            "tool": capability.tool,
            "arguments_sha256": arguments_sha256,
            "reason_sha256": reason_sha256,
            "authorization_fingerprint": (
                capability.authorization_fingerprint
            ),
            "idempotency_request_fingerprint": request_fingerprint,
        },
    )

    try:
        await write_audit_event(request_event)
    except Exception as exc:
        await _release_reserved_idempotency(
            capability=capability,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        raise _ai_tool_runtime_unavailable(
            "AI tool request audit is unavailable"
        ) from exc

    try:
        issued = await _ai_tool_grant_store.issue(
            capability,
            arguments=payload.arguments,
            reason=payload.reason,
        )
    except AiToolGrantInvalid as exc:
        await _release_reserved_idempotency(
            capability=capability,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI tool request is invalid",
        ) from exc
    except AiToolGrantUnavailable as exc:
        await _release_reserved_idempotency(
            capability=capability,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        raise _ai_tool_runtime_unavailable(
            "AI tool grant authority is unavailable"
        ) from exc

    try:
        await _jarvis_idempotency_store.transition(
            tenant_id=capability.tenant_id,
            actor_subject=capability.actor_subject,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            expected_state="reserved",
            new_state="dispatched",
        )
    except JarvisIdempotencyUnavailable as exc:
        # The grant token never leaves this process on this path. It may remain
        # in Redis until expiry, but AI Core never receives it.
        raise _ai_tool_runtime_unavailable(
            "AI tool idempotency dispatch state is unavailable"
        ) from exc

    try:
        result = await _jarvis_execution_broker.execute(
            grant_token=issued.token.get_secret_value(),
            tool=payload.tool,
            arguments=payload.arguments,
            reason=payload.reason,
        )
    except JarvisExecutionBrokerDenied as exc:
        await _finalize_dispatched_idempotency(
            capability=capability,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            new_state="denied",
        )
        raise _ai_tool_access_denied() from exc
    except JarvisExecutionBrokerIndeterminate as exc:
        await _finalize_dispatched_idempotency(
            capability=capability,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            new_state="indeterminate",
        )
        raise _ai_tool_runtime_unavailable(
            "AI tool execution outcome is unknown; do not retry automatically"
        ) from exc
    except JarvisExecutionBrokerUnavailable as exc:
        await _finalize_dispatched_idempotency(
            capability=capability,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            new_state="indeterminate",
        )
        raise _ai_tool_runtime_unavailable(
            "AI tool execution broker is unavailable; do not retry automatically"
        ) from exc
    except JarvisExecutionBrokerContractError as exc:
        await _finalize_dispatched_idempotency(
            capability=capability,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            new_state="indeterminate",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "AI tool execution contract failed closed; "
                "do not retry automatically"
            ),
        ) from exc

    await _finalize_dispatched_idempotency(
        capability=capability,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        new_state="completed",
    )
    return result


@router.post(
    "/internal/ai/tool-executions/authorize",
    response_model=InternalAiToolAuthorizationResponse,
    tags=["internal-ai"],
)
async def authorize_internal_ai_tool_execution(
    payload: InternalAiToolAuthorizationRequest,
    request: Request,
    jarvis_service: Annotated[
        VerifiedJarvisService,
        Depends(require_fresh_jarvis_service),
    ],
) -> InternalAiToolAuthorizationResponse:
    """Consume a broker-owned grant and return trusted execution context."""

    try:
        binding = await _ai_tool_grant_store.consume_authorized_invocation(
            token=payload.grant_token,
            tool=payload.tool,
            arguments=payload.arguments,
            reason=payload.reason,
        )
    except (
        AiToolGrantInvalid,
        AiToolGrantReplayOrExpired,
        AiToolGrantBindingMismatch,
    ) as exc:
        raise _ai_tool_grant_failed() from exc
    except AiToolGrantUnavailable as exc:
        raise _ai_tool_runtime_unavailable(
            "AI tool grant authority is unavailable"
        ) from exc

    audit_event = build_audit_event(
        request_id=request.state.request_id,
        actor=binding.actor_subject,
        tenant_id=str(binding.tenant_id),
        method="POST",
        path="/internal/ai/tool-executions/authorize",
        status_code=status.HTTP_200_OK,
        action="ai_tool_execution_authorized",
        metadata={
            "service_subject": jarvis_service.service_subject,
            "tool": binding.tool,
            "arguments_sha256": binding.arguments_sha256,
            "reason_sha256": binding.reason_sha256,
            "authorization_fingerprint": (
                binding.authorization_fingerprint
            ),
        },
    )

    try:
        await write_audit_event(audit_event)
    except Exception as exc:
        # Grant is already consumed. Never execute without durable audit.
        raise _ai_tool_runtime_unavailable(
            "AI tool execution audit is unavailable"
        ) from exc

    scopes = TOOL_REQUIRED_SCOPES[binding.tool]

    return InternalAiToolAuthorizationResponse(
        request_id=request.state.request_id,
        tenant_id=str(binding.tenant_id),
        actor_subject=binding.actor_subject,
        tool=binding.tool,
        granted_scopes=tuple(sorted(scopes)),
        authorization_fingerprint=(
            binding.authorization_fingerprint
        ),
        arguments_sha256=binding.arguments_sha256,
        reason_sha256=binding.reason_sha256,
    )
