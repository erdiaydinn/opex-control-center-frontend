"""Super-admin API for tenant-level Jarvis query discriminator authority."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_tenant_query_context import (
    ABSENT_QUERY_CONTEXT_FINGERPRINT,
    AiTenantQueryContext,
    AiTenantQueryContextConflict,
    AiTenantQueryContextInvalid,
    get_ai_tenant_query_context,
    put_ai_tenant_query_context,
)
from app.core.security import Principal, require_super_admin

router = APIRouter(
    prefix="/v1/admin/ai-query-context",
    tags=["administration", "ai"],
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class AiTenantQueryContextResponse(BaseModel):
    tenant_id: str
    configured: bool
    record_fingerprint: str
    context: AiTenantQueryContext | None


class PutAiTenantQueryContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_record_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )
    context: AiTenantQueryContext


class PutAiTenantQueryContextResponse(BaseModel):
    tenant_id: str
    record_fingerprint: str
    context: AiTenantQueryContext
    changed: bool


@router.get(
    "",
    response_model=AiTenantQueryContextResponse,
)
async def get_tenant_query_context(
    principal: Annotated[
        Principal,
        Depends(require_super_admin),
    ],
) -> AiTenantQueryContextResponse:
    try:
        record = await get_ai_tenant_query_context(
            tenant_id=str(principal.tenant_id)
        )
    except AiTenantQueryContextInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant query context is invalid",
        ) from exc

    if record is None:
        return AiTenantQueryContextResponse(
            tenant_id=str(principal.tenant_id),
            configured=False,
            record_fingerprint=(
                ABSENT_QUERY_CONTEXT_FINGERPRINT
            ),
            context=None,
        )

    return AiTenantQueryContextResponse(
        tenant_id=str(principal.tenant_id),
        configured=True,
        record_fingerprint=record.record_fingerprint,
        context=record.context,
    )


@router.put(
    "",
    response_model=PutAiTenantQueryContextResponse,
)
async def put_tenant_query_context(
    payload: PutAiTenantQueryContextRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_super_admin),
    ],
) -> PutAiTenantQueryContextResponse:
    try:
        updated = await put_ai_tenant_query_context(
            tenant_id=str(principal.tenant_id),
            expected_record_fingerprint=(
                payload.expected_record_fingerprint
            ),
            context=payload.context,
            actor_subject=principal.subject,
            request_id=request.state.request_id,
        )
    except AiTenantQueryContextConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant query context changed; refresh before retrying",
        ) from exc
    except AiTenantQueryContextInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant query context is invalid",
        ) from exc

    return PutAiTenantQueryContextResponse(
        tenant_id=str(principal.tenant_id),
        record_fingerprint=updated.record_fingerprint,
        context=updated.context,
        changed=updated.changed,
    )
