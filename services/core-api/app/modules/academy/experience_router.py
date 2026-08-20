from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.academy.credentials_router import router as credentials_router
from app.modules.academy.experience_service import (
    author_interaction_set,
    author_scenario,
    begin_scenario,
    decide_scenario,
    interaction_timeline,
)
from app.modules.academy.playback_service import (
    finish_verified_playback,
    record_verified_heartbeat,
    start_verified_playback,
)
from app.modules.academy.schemas import (
    InteractionSetCreateRequest,
    PlaybackHeartbeatRequest,
    ScenarioCreateRequest,
    ScenarioDecisionRequest,
    ScenarioStartRequest,
)
from app.modules.academy.service import require_module

router = APIRouter(tags=["academy-experience"])
router.include_router(credentials_router)

TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Player = Annotated[
    Principal,
    Depends(require_permission("feature:academy:player")),
]
StudioUser = Annotated[
    Principal,
    Depends(require_permission("feature:academy:contentStudio")),
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


@router.get("/enrollments/{enrollment_id}/content/{content_version_id}/interactions")
async def get_interactions(
    enrollment_id: UUID,
    content_version_id: UUID,
    session: TenantSession,
    principal: Player,
) -> dict[str, object]:
    return await interaction_timeline(
        session,
        principal,
        enrollment_id=enrollment_id,
        content_version_id=content_version_id,
    )


@router.post(
    "/admin/interaction-sets",
    status_code=status.HTTP_201_CREATED,
)
async def post_interaction_set(
    payload: InteractionSetCreateRequest,
    request: Request,
    session: TenantSession,
    principal: StudioUser,
) -> dict[str, object]:
    return await author_interaction_set(
        session,
        principal,
        request_id=_request_id(request),
        payload=payload,
    )


@router.post(
    "/admin/scenarios",
    status_code=status.HTTP_201_CREATED,
)
async def post_scenario(
    payload: ScenarioCreateRequest,
    request: Request,
    session: TenantSession,
    principal: StudioUser,
) -> dict[str, object]:
    return await author_scenario(
        session,
        principal,
        request_id=_request_id(request),
        payload=payload,
    )


@router.post(
    "/scenarios/{scenario_id}/runs",
    status_code=status.HTTP_201_CREATED,
)
async def post_scenario_run(
    scenario_id: UUID,
    payload: ScenarioStartRequest,
    request: Request,
    session: TenantSession,
    principal: Player,
) -> dict[str, object]:
    return await begin_scenario(
        session,
        principal,
        request_id=_request_id(request),
        scenario_id=scenario_id,
        enrollment_id=payload.enrollment_id,
    )


@router.post("/scenario-runs/{run_id}/decisions")
async def post_scenario_decision(
    run_id: UUID,
    payload: ScenarioDecisionRequest,
    request: Request,
    session: TenantSession,
    principal: Player,
) -> dict[str, object]:
    return await decide_scenario(
        session,
        principal,
        request_id=_request_id(request),
        run_id=run_id,
        payload=payload,
    )
