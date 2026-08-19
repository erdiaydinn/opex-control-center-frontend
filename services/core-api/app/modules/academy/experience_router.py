from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.academy.playback_service import (
    finish_verified_playback,
    record_verified_heartbeat,
    start_verified_playback,
)
from app.modules.academy.schemas import PlaybackHeartbeatRequest
from app.modules.academy.service import require_module

router = APIRouter(tags=["academy-experience"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Player = Annotated[
    Principal,
    Depends(require_permission("feature:academy:player")),
]


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "academy-experience-untracked"))


@router.post("/enrollments/{enrollment_id}/media/{media_id}/verified-playback")
async def post_verified_playback(
    enrollment_id: UUID,
    media_id: UUID,
    request: Request,
    session: TenantSession,
    principal: Player,
) -> dict[str, object]:
    await require_module(session, principal)
    return await start_verified_playback(
        session,
        principal,
        request_id=_request_id(request),
        enrollment_id=enrollment_id,
        media_id=media_id,
    )


@router.post("/playback-sessions/{playback_session_id}/heartbeat")
async def post_playback_heartbeat(
    playback_session_id: UUID,
    payload: PlaybackHeartbeatRequest,
    request: Request,
    session: TenantSession,
    principal: Player,
) -> dict[str, object]:
    await require_module(session, principal)
    return await record_verified_heartbeat(
        session,
        principal,
        request_id=_request_id(request),
        playback_session_id=playback_session_id,
        payload=payload,
    )


@router.post("/playback-sessions/{playback_session_id}/close")
async def post_playback_close(
    playback_session_id: UUID,
    request: Request,
    session: TenantSession,
    principal: Player,
) -> dict[str, object]:
    await require_module(session, principal)
    return await finish_verified_playback(
        session,
        principal,
        request_id=_request_id(request),
        playback_session_id=playback_session_id,
    )
