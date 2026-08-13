"""Tenant-safe Jarvis tool grant and execution authorization routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.ai_data_scope_admin_routes import router as ai_data_scope_admin_router
from app.ai_tenant_query_context_routes import router as ai_tenant_query_context_router
from app.core.ai_data_scope import AiDataScope
from app.core.ai_query_contract_policy import (
    AiQueryContractPolicyError,
    require_ai_query_contract_ready,
)
from app.core.ai_tenant_query_context import (
    AiTenantQueryContextInvalid,
    AiTenantQueryContextRecord,
    get_ai_tenant_query_context,
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
    AiToolGrantUnavailable,
    RedisAiToolGrantStore,
)
from app.core.audit import build_audit_event
from app.core.config import get_settings
from app.core.jarvis_service_identity import VerifiedJarvisService
from app.core.jarvis_service_security import require_fresh_jarvis_service
from app.core.resources import redis_client, write_audit_event
from app.core.security import Principal, get_current_principal

router = APIRouter()
router.include_router(ai_data_scope_admin_router)
router.include_router(ai_tenant_query_context_router)

_ai_tool_grant_store = RedisAiToolGrantStore(redis_client)


class AiToolGrantIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: AiToolName
    arguments: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)


class AiToolGrantIssueResponse(BaseModel):
    request_id: str
    grant_token: str
    expires_in_seconds: int
    tool: AiToolName
    data_scope_fingerprint: str
    query_contract_id: str
    query_contract_revision: int
    query_contract_fingerprint: str
    execution_scope_fingerprint: str
    query_context_record_fingerprint: str
    execution_context_fingerprint: str


class InternalAiToolAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    data_scope: AiDataScope
    data_scope_fingerprint: str
    query_contract_id: str
    query_contract_revision: int
    query_contract_fingerprint: str
    execution_scope_fingerprint: str
    query_context_record_fingerprint: str
    execution_context_fingerprint: str
    entity_ids: tuple[str, ...]
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


def _query_contract_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI tool execution contract is not ready",
    )


def _query_context_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI tenant query context is not ready",
    )


async def _load_tenant_query_context(
    tenant_id: str,
) -> AiTenantQueryContextRecord | None:
    """Adapt the keyword-only DB authority to the grant loader contract."""
    return await get_ai_tenant_query_context(tenant_id=tenant_id)


@router.post(
    "/v1/ai/tool-grants",
    response_model=AiToolGrantIssueResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ai"],
)
async def issue_ai_tool_grant(
    payload: AiToolGrantIssueRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> AiToolGrantIssueResponse:
    """Issue one short-lived invocation grant from DB-backed permissions."""

    try:
        capability = derive_ai_tool_capability(principal, tool=payload.tool)
    except (AiToolAccessDenied, AiToolPermissionScopeUnsupported) as exc:
        raise _ai_tool_access_denied() from exc
    except AiToolAuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI tool request is invalid",
        ) from exc

    try:
        require_ai_query_contract_ready(
            tool=payload.tool,
            environment=get_settings().environment,
        )
    except AiQueryContractPolicyError as exc:
        raise _query_contract_unavailable() from exc

    try:
        query_context = await _load_tenant_query_context(
            str(principal.tenant_id)
        )
    except AiTenantQueryContextInvalid as exc:
        raise _query_context_unavailable() from exc
    except Exception as exc:
        raise _query_context_unavailable() from exc
    if query_context is None:
        raise _query_context_unavailable()

    try:
        issued = await _ai_tool_grant_store.issue(
            capability,
            arguments=payload.arguments,
            reason=payload.reason,
            query_context=query_context,
        )
    except AiToolGrantInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI tool request is invalid",
        ) from exc
    except AiToolGrantUnavailable as exc:
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
        data_scope_fingerprint=capability.data_scope_fingerprint,
        query_contract_id=binding.query_contract_id,
        query_contract_revision=binding.query_contract_revision,
        query_contract_fingerprint=binding.query_contract_fingerprint,
        execution_scope_fingerprint=binding.execution_scope_fingerprint,
        query_context_record_fingerprint=(
            binding.query_context_record_fingerprint
        ),
        execution_context_fingerprint=(
            binding.execution_context_fingerprint
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
    """Consume a user grant and return one trusted execution context."""

    try:
        binding = await _ai_tool_grant_store.consume_authorized_invocation(
            token=payload.grant_token,
            tool=payload.tool,
            arguments=payload.arguments,
            reason=payload.reason,
            query_context_loader=_load_tenant_query_context,
        )
    except (
        AiToolGrantInvalid,
        AiToolGrantReplayOrExpired,
        AiToolGrantBindingMismatch,
    ) as exc:
        raise _ai_tool_grant_failed() from exc
    except AiToolGrantUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tool grant authority is unavailable",
        ) from exc

    try:
        require_ai_query_contract_ready(
            tool=payload.tool,
            environment=get_settings().environment,
        )
    except AiQueryContractPolicyError as exc:
        raise _query_contract_unavailable() from exc

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
            "data_scope_fingerprint": binding.data_scope_fingerprint,
            "data_scope_store_count": len(binding.data_scope.store_names),
            "query_contract_id": binding.query_contract_id,
            "query_contract_revision": binding.query_contract_revision,
            "query_contract_fingerprint": (
                binding.query_contract_fingerprint
            ),
            "execution_scope_fingerprint": (
                binding.execution_scope_fingerprint
            ),
            "query_context_record_fingerprint": (
                binding.query_context_record_fingerprint
            ),
            "execution_context_fingerprint": (
                binding.execution_context_fingerprint
            ),
            "entity_id_count": len(binding.entity_ids),
        },
    )

    try:
        await write_audit_event(audit_event)
    except Exception as exc:
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
        data_scope_fingerprint=binding.data_scope_fingerprint,
        query_contract_id=binding.query_contract_id,
        query_contract_revision=binding.query_contract_revision,
        query_contract_fingerprint=binding.query_contract_fingerprint,
        execution_scope_fingerprint=binding.execution_scope_fingerprint,
        query_context_record_fingerprint=(
            binding.query_context_record_fingerprint
        ),
        execution_context_fingerprint=(
            binding.execution_context_fingerprint
        ),
        entity_ids=binding.entity_ids,
        authorization_fingerprint=binding.authorization_fingerprint,
        arguments_sha256=binding.arguments_sha256,
        reason_sha256=binding.reason_sha256,
    )
