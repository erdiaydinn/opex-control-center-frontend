from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.academy.credentials_schemas import (
    BadgeAwardIssueRequest,
    BadgeDefinitionCreateRequest,
    BadgeRetirementRequest,
    BadgeRevocationRequest,
)
from app.modules.academy.credentials_service import (
    create_definition,
    issue_award,
    my_credential,
    my_credentials,
    retire_definition,
    revoke_award,
)
from app.modules.academy.skill_gap_service import get_my_skill_gap_snapshot

router = APIRouter(prefix="/credentials", tags=["academy-credentials"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Viewer = Annotated[Principal, Depends(require_permission("module:academy:view"))]
ManageCredentials = Annotated[
    Principal,
    Depends(require_permission("action:academy:manageContent")),
]
RevokeCredential = Annotated[
    Principal,
    Depends(require_permission("action:academy:revokeCompletion")),
]


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "academy-credential-untracked"))


def _domain_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/me")
async def get_my_credentials(
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    items = await my_credentials(session, principal)
    return {"items": items, "count": len(items)}


@router.get("/me/skill-gaps")
async def get_my_skill_gaps(
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    return await get_my_skill_gap_snapshot(session, principal)


@router.get("/me/{badge_award_id}")
async def get_my_credential(
    badge_award_id: UUID,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    result = await my_credential(
        session,
        principal,
        badge_award_id=badge_award_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Academy credential not found")
    return result


@router.post("/definitions", status_code=status.HTTP_201_CREATED)
async def post_badge_definition(
    payload: BadgeDefinitionCreateRequest,
    request: Request,
    session: TenantSession,
    principal: ManageCredentials,
) -> dict[str, object]:
    try:
        return await create_definition(
            session,
            principal,
            request_id=_request_id(request),
            payload=payload,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.post("/definitions/{badge_definition_id}/retire")
async def post_badge_definition_retirement(
    badge_definition_id: UUID,
    payload: BadgeRetirementRequest,
    request: Request,
    session: TenantSession,
    principal: ManageCredentials,
) -> dict[str, object]:
    try:
        return await retire_definition(
            session,
            principal,
            request_id=_request_id(request),
            badge_definition_id=badge_definition_id,
            payload=payload,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.post("/awards", status_code=status.HTTP_201_CREATED)
async def post_badge_award(
    payload: BadgeAwardIssueRequest,
    request: Request,
    session: TenantSession,
    principal: ManageCredentials,
) -> dict[str, object]:
    try:
        return await issue_award(
            session,
            principal,
            request_id=_request_id(request),
            payload=payload,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.post("/awards/{badge_award_id}/revoke")
async def post_badge_award_revocation(
    badge_award_id: UUID,
    payload: BadgeRevocationRequest,
    request: Request,
    session: TenantSession,
    principal: RevokeCredential,
) -> dict[str, object]:
    try:
        return await revoke_award(
            session,
            principal,
            request_id=_request_id(request),
            badge_award_id=badge_award_id,
            payload=payload,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc
