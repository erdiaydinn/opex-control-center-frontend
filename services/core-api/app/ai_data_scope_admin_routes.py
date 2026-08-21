"""Super-admin API for existing Jarvis role-permission data scopes."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_data_scope import (
    AiDataScope,
    AiDataScopeError,
    parse_ai_data_scope,
)
from app.core.ai_data_scope_admin import (
    AiDataScopeAssignmentConflict,
    AiDataScopeAssignmentNotFound,
    list_ai_data_scope_assignments,
    update_ai_data_scope_assignment,
)
from app.core.ai_tool_authorization import SCOPE_PERMISSION_KEYS
from app.core.security import Principal, require_super_admin

router = APIRouter(
    prefix="/v1/admin/ai-data-scopes",
    tags=["administration", "ai"],
)

ROLE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,99}$")
AI_PERMISSION_KEYS = frozenset(SCOPE_PERMISSION_KEYS.values())
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class AiDataScopeAssignmentView(BaseModel):
    model_config = ConfigDict(frozen=True)

    role_key: str
    role_name: str
    is_system: bool
    permission_key: str
    status: Literal["configured", "unconfigured"]
    record_fingerprint: str
    data_scope: AiDataScope | None


class AiDataScopeAssignmentListResponse(BaseModel):
    tenant_id: str
    count: int
    items: tuple[AiDataScopeAssignmentView, ...]


class UpdateAiDataScopeAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_record_fingerprint: str = Field(
        pattern=SHA256_PATTERN
    )
    data_scope: AiDataScope


class UpdateAiDataScopeAssignmentResponse(BaseModel):
    tenant_id: str
    role_key: str
    permission_key: str
    record_fingerprint: str
    data_scope: AiDataScope
    changed: bool


def _validate_role_key(role_key: str) -> str:
    if not ROLE_KEY_PATTERN.fullmatch(role_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role key",
        )
    return role_key


def _validate_ai_permission_key(permission_key: str) -> str:
    if permission_key not in AI_PERMISSION_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid AI permission key",
        )
    return permission_key


@router.get(
    "",
    response_model=AiDataScopeAssignmentListResponse,
)
async def get_ai_data_scope_assignments(
    principal: Annotated[
        Principal,
        Depends(require_super_admin),
    ],
) -> AiDataScopeAssignmentListResponse:
    records = await list_ai_data_scope_assignments(
        tenant_id=str(principal.tenant_id),
        permission_keys=tuple(sorted(AI_PERMISSION_KEYS)),
    )

    items: list[AiDataScopeAssignmentView] = []
    for record in records:
        parsed: AiDataScope | None = None
        scope_status: Literal[
            "configured",
            "unconfigured",
        ] = "unconfigured"

        try:
            parsed = parse_ai_data_scope(record.raw_scope)
            scope_status = "configured"
        except AiDataScopeError:
            # Legacy/empty/unsupported records are visible as unconfigured but
            # are never echoed back as trusted scope content.
            parsed = None

        items.append(
            AiDataScopeAssignmentView(
                role_key=record.role_key,
                role_name=record.role_name,
                is_system=record.is_system,
                permission_key=record.permission_key,
                status=scope_status,
                record_fingerprint=record.record_fingerprint,
                data_scope=parsed,
            )
        )

    return AiDataScopeAssignmentListResponse(
        tenant_id=str(principal.tenant_id),
        count=len(items),
        items=tuple(items),
    )


@router.put(
    "/{role_key}/{permission_key}",
    response_model=UpdateAiDataScopeAssignmentResponse,
)
async def put_ai_data_scope_assignment(
    role_key: str,
    permission_key: str,
    payload: UpdateAiDataScopeAssignmentRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_super_admin),
    ],
) -> UpdateAiDataScopeAssignmentResponse:
    role_key = _validate_role_key(role_key)
    permission_key = _validate_ai_permission_key(permission_key)

    try:
        updated = await update_ai_data_scope_assignment(
            tenant_id=str(principal.tenant_id),
            role_key=role_key,
            permission_key=permission_key,
            expected_record_fingerprint=(
                payload.expected_record_fingerprint
            ),
            data_scope=payload.data_scope,
            actor_subject=principal.subject,
            request_id=request.state.request_id,
        )
    except AiDataScopeAssignmentNotFound as exc:
        # Scope administration must never create a permission assignment.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI permission assignment not found",
        ) from exc
    except AiDataScopeAssignmentConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI data scope changed; refresh before retrying",
        ) from exc

    return UpdateAiDataScopeAssignmentResponse(
        tenant_id=str(principal.tenant_id),
        role_key=updated.role_key,
        permission_key=updated.permission_key,
        record_fingerprint=updated.record_fingerprint,
        data_scope=updated.data_scope,
        changed=updated.changed,
    )
