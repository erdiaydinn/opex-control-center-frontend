"""Tenant-safe Jarvis tool grant and execution authorization routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.ai_data_scope_admin_routes import router as ai_data_scope_admin_router
from app.ai_tenant_query_context_routes import router as ai_tenant_query_context_router
from app.core.ai_data_scope import AiDataScope
from app.core.ai_query_contract_policy import (
    AiQueryContractPolicyError,
    require_ai_query_contract_ready,
)
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
    AiToolGrantTenantContextUnavailable,
    AiToolGrantUnavailable,
    RedisAiToolGrantStore,
    canonical_arguments_sha256,
    canonical_reason_sha256,
)
from app.core.audit import build_audit_event
from app.core.config import get_settings
from app.core.jarvis_execution_admission import (
    JarvisAdmissionConcurrencyLimited,
    JarvisAdmissionInvalid,
    JarvisAdmissionLease,
    JarvisAdmissionRateLimited,
    JarvisAdmissionUnavailable,
    JarvisExecutionAdmissionSettings,
    RedisJarvisExecutionAdmissionStore,
)
from app.core.jarvis_grant_idempotency import (
    JarvisGrantIdempotencyConflict,
    JarvisGrantIdempotencyInvalid,
    JarvisGrantIdempotencyReplay,
    JarvisGrantIdempotencyReservation,
    JarvisGrantIdempotencyUnavailable,
    RedisJarvisGrantIdempotencyStore,
    grant_issue_request_fingerprint,
)
from app.core.jarvis_service_identity import VerifiedJarvisService
from app.core.jarvis_service_security import require_fresh_jarvis_service
from app.core.resources import redis_client, write_audit_event
from app.core.security import Principal, get_current_principal

router = APIRouter()
router.include_router(ai_data_scope_admin_router)
router.include_router(ai_tenant_query_context_router)

_ai_tool_grant_store = RedisAiToolGrantStore(redis_client)
_grant_idempotency_store = RedisJarvisGrantIdempotencyStore(redis_client)
_admission_settings = JarvisExecutionAdmissionSettings()
_admission_store = RedisJarvisExecutionAdmissionStore(
    redis_client,
    _admission_settings,
)


class AiToolGrantIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: AiToolName
    arguments: dict[str, Any]
    reason: str = Field(
        min_length=1,
        max_length=1000,
    )


class AiToolGrantIssueResponse(BaseModel):
    request_id: str
    grant_token: str
    expires_in_seconds: int
    tool: AiToolName
    data_scope_fingerprint: str
    tenant_query_context_fingerprint: str
    query_contract_id: str
    query_contract_revision: int
    query_contract_fingerprint: str
    execution_scope_fingerprint: str


class InternalAiToolAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_token: str = Field(
        min_length=32,
        max_length=256,
    )
    tool: AiToolName
    arguments: dict[str, Any]
    reason: str = Field(
        min_length=1,
        max_length=1000,
    )


class InternalAiToolAuthorizationResponse(BaseModel):
    request_id: str
    tenant_id: str
    actor_subject: str
    tool: AiToolName
    granted_scopes: tuple[str, ...]
    data_scope: AiDataScope
    data_scope_fingerprint: str
    tenant_entity_ids: tuple[str, ...]
    tenant_query_context_fingerprint: str
    query_contract_id: str
    query_contract_revision: int
    query_contract_fingerprint: str
    execution_scope_fingerprint: str
    authorization_fingerprint: str
    arguments_sha256: str
    reason_sha256: str
    admission_lease_token: str
    admission_lease_ttl_seconds: int


class InternalAiToolAdmissionReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admission_lease_token: str = Field(
        min_length=32,
        max_length=256,
    )


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


def _query_contract_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI tool execution contract is not ready",
    )


def _tenant_query_context_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI tenant query context is unavailable",
    )


def _admission_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI tool execution admission authority is unavailable",
    )


async def _release_grant_reservation_safely(
    reservation: JarvisGrantIdempotencyReservation | None,
) -> None:
    if reservation is None:
        return
    try:
        await _grant_idempotency_store.release(reservation)
    except (
        JarvisGrantIdempotencyInvalid,
        JarvisGrantIdempotencyUnavailable,
    ):
        # A stale reservation blocks duplicate grant issuance until TTL. That
        # fail-closed outcome is safer than deleting an ambiguous reservation.
        return


async def _release_admission_safely(
    lease: JarvisAdmissionLease | None,
) -> None:
    if lease is None:
        return
    try:
        await _admission_store.release(lease)
    except (JarvisAdmissionInvalid, JarvisAdmissionUnavailable):
        # Concurrency membership is bounded by Redis-server-time TTL.
        return


@router.post(
    "/v1/ai/tool-grants",
    response_model=AiToolGrantIssueResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ai"],
)
async def issue_ai_tool_grant(
    payload: AiToolGrantIssueRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(get_current_principal),
    ],
) -> AiToolGrantIssueResponse:
    """Issue one short-lived invocation grant from DB-backed permissions."""

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

    settings = get_settings()
    try:
        require_ai_query_contract_ready(
            tool=payload.tool,
            environment=settings.environment,
        )
    except AiQueryContractPolicyError as exc:
        raise _query_contract_unavailable() from exc

    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if (
        settings.environment in {"staging", "production"}
        and not idempotency_key
    ):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Idempotency-Key is required for AI tool grant issuance",
        )

    reservation: JarvisGrantIdempotencyReservation | None = None
    if idempotency_key:
        try:
            request_fingerprint = grant_issue_request_fingerprint(
                tenant_id=capability.tenant_id,
                actor_subject=capability.actor_subject,
                tool=capability.tool,
                arguments_sha256=canonical_arguments_sha256(
                    payload.arguments
                ),
                reason_sha256=canonical_reason_sha256(payload.reason),
                authorization_fingerprint=(
                    capability.authorization_fingerprint
                ),
                data_scope_fingerprint=(
                    capability.data_scope_fingerprint
                ),
            )
            reservation = await _grant_idempotency_store.reserve(
                tenant_id=capability.tenant_id,
                actor_subject=capability.actor_subject,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        except JarvisGrantIdempotencyInvalid as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AI tool grant idempotency request is invalid",
            ) from exc
        except JarvisGrantIdempotencyReplay as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="AI tool grant issuance replay is blocked",
            ) from exc
        except JarvisGrantIdempotencyConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency-Key is bound to another AI request",
            ) from exc
        except JarvisGrantIdempotencyUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI tool grant idempotency authority is unavailable",
            ) from exc

    try:
        issued = await _ai_tool_grant_store.issue(
            capability,
            arguments=payload.arguments,
            reason=payload.reason,
        )
    except AiToolGrantInvalid as exc:
        await _release_grant_reservation_safely(reservation)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI tool request is invalid",
        ) from exc
    except AiToolGrantTenantContextUnavailable as exc:
        await _release_grant_reservation_safely(reservation)
        raise _tenant_query_context_unavailable() from exc
    except AiToolGrantUnavailable as exc:
        await _release_grant_reservation_safely(reservation)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tool grant authority is unavailable",
        ) from exc

    binding = issued.binding
    return AiToolGrantIssueResponse(
        request_id=request.state.request_id,
        grant_token=issued.token.get_secret_value(),
        expires_in_seconds=issued.expires_in_seconds,
        tool=capability.tool,
        data_scope_fingerprint=(
            capability.data_scope_fingerprint
        ),
        tenant_query_context_fingerprint=(
            binding.tenant_query_context_fingerprint
        ),
        query_contract_id=binding.query_contract_id,
        query_contract_revision=(
            binding.query_contract_revision
        ),
        query_contract_fingerprint=(
            binding.query_contract_fingerprint
        ),
        execution_scope_fingerprint=(
            binding.execution_scope_fingerprint
        ),
    )


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
    """Consume a Grant V4 token and reserve distributed execution capacity."""

    try:
        authorization = await (
            _ai_tool_grant_store.consume_authorized_invocation(
                token=payload.grant_token,
                tool=payload.tool,
                arguments=payload.arguments,
                reason=payload.reason,
            )
        )
    except (
        AiToolGrantInvalid,
        AiToolGrantReplayOrExpired,
        AiToolGrantBindingMismatch,
    ) as exc:
        raise _ai_tool_grant_failed() from exc
    except AiToolGrantTenantContextUnavailable as exc:
        raise _tenant_query_context_unavailable() from exc
    except AiToolGrantUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tool grant authority is unavailable",
        ) from exc

    binding = authorization.binding

    # Deliberately after atomic grant consumption: if downstream readiness is
    # withdrawn, rate-limited or unavailable, this grant is burned and cannot
    # be retried ambiguously.
    try:
        require_ai_query_contract_ready(
            tool=payload.tool,
            environment=get_settings().environment,
        )
    except AiQueryContractPolicyError as exc:
        raise _query_contract_unavailable() from exc

    admission_lease: JarvisAdmissionLease | None = None
    try:
        admission_lease = await _admission_store.acquire(
            tenant_id=binding.tenant_id,
            actor_subject=binding.actor_subject,
        )
    except (
        JarvisAdmissionRateLimited,
        JarvisAdmissionConcurrencyLimited,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI tool execution admission limit exceeded",
        ) from exc
    except (JarvisAdmissionInvalid, JarvisAdmissionUnavailable) as exc:
        raise _admission_unavailable() from exc

    audit_event = build_audit_event(
        request_id=request.state.request_id,
        actor=binding.actor_subject,
        tenant_id=str(binding.tenant_id),
        method="POST",
        path="/internal/ai/tool-executions/authorize",
        status_code=status.HTTP_200_OK,
        action="ai_tool_execution_authorized",
        metadata={
            "service_subject": (
                jarvis_service.service_subject
            ),
            "tool": binding.tool,
            "arguments_sha256": (
                binding.arguments_sha256
            ),
            "reason_sha256": binding.reason_sha256,
            "authorization_fingerprint": (
                binding.authorization_fingerprint
            ),
            "data_scope_fingerprint": (
                binding.data_scope_fingerprint
            ),
            "data_scope_store_count": len(
                binding.data_scope.store_names
            ),
            "tenant_query_context_fingerprint": (
                binding.tenant_query_context_fingerprint
            ),
            "tenant_entity_count": len(
                authorization.tenant_entity_ids
            ),
            "query_contract_id": (
                binding.query_contract_id
            ),
            "query_contract_revision": (
                binding.query_contract_revision
            ),
            "query_contract_fingerprint": (
                binding.query_contract_fingerprint
            ),
            "execution_scope_fingerprint": (
                binding.execution_scope_fingerprint
            ),
            "admission_lease_ttl_seconds": (
                admission_lease.lease_ttl_seconds
            ),
        },
    )

    try:
        await write_audit_event(audit_event)
    except Exception as exc:
        await _release_admission_safely(admission_lease)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tool execution audit is unavailable",
        ) from exc

    scopes = TOOL_REQUIRED_SCOPES[binding.tool]

    return InternalAiToolAuthorizationResponse(
        request_id=request.state.request_id,
        tenant_id=str(binding.tenant_id),
        actor_subject=binding.actor_subject,
        tool=binding.tool,
        granted_scopes=tuple(sorted(scopes)),
        data_scope=binding.data_scope,
        data_scope_fingerprint=(
            binding.data_scope_fingerprint
        ),
        tenant_entity_ids=(
            authorization.tenant_entity_ids
        ),
        tenant_query_context_fingerprint=(
            binding.tenant_query_context_fingerprint
        ),
        query_contract_id=binding.query_contract_id,
        query_contract_revision=(
            binding.query_contract_revision
        ),
        query_contract_fingerprint=(
            binding.query_contract_fingerprint
        ),
        execution_scope_fingerprint=(
            binding.execution_scope_fingerprint
        ),
        authorization_fingerprint=(
            binding.authorization_fingerprint
        ),
        arguments_sha256=binding.arguments_sha256,
        reason_sha256=binding.reason_sha256,
        admission_lease_token=(
            admission_lease.token.get_secret_value()
        ),
        admission_lease_ttl_seconds=(
            admission_lease.lease_ttl_seconds
        ),
    )


@router.post(
    "/internal/ai/tool-executions/release",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["internal-ai"],
)
async def release_internal_ai_tool_execution(
    payload: InternalAiToolAdmissionReleaseRequest,
    _jarvis_service: Annotated[
        VerifiedJarvisService,
        Depends(require_fresh_jarvis_service),
    ],
) -> None:
    """Release one opaque admission lease after the trusted AI execution."""

    lease = JarvisAdmissionLease(
        token=SecretStr(payload.admission_lease_token),
        lease_ttl_seconds=0,
    )
    try:
        await _admission_store.release(lease)
    except JarvisAdmissionInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI tool admission lease is invalid",
        ) from exc
    except JarvisAdmissionUnavailable as exc:
        raise _admission_unavailable() from exc
