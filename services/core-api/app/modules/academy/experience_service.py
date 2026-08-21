from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository import record_learning_event, record_platform_audit
from app.modules.academy.repository_experience import (
    apply_scenario_decision,
    create_interaction_set,
    create_scenario,
    get_interaction_timeline,
    start_scenario_run,
)
from app.modules.academy.service import require_module


async def author_interaction_set(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    payload: Any,
) -> dict[str, Any]:
    await require_module(session, principal)
    result = await create_interaction_set(session, principal, payload)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Compatible Academy content version not found for interaction set",
        )
    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.interaction-set.created",
        resource_type="academy_interaction_set",
        resource_id=str(result["id"]),
        data={
            "content_version_id": str(result["content_version_id"]),
            "version_number": result["version_number"],
            "node_count": result["node_count"],
            "status": result["status"],
            "source_fingerprint": result["source_fingerprint"],
        },
    )
    return result


async def interaction_timeline(
    session: AsyncSession,
    principal: Principal,
    *,
    enrollment_id: UUID,
    content_version_id: UUID,
) -> dict[str, Any]:
    await require_module(session, principal)
    result = await get_interaction_timeline(
        session,
        principal,
        enrollment_id=enrollment_id,
        content_version_id=content_version_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Published interaction timeline not found")
    return result


async def author_scenario(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    payload: Any,
) -> dict[str, Any]:
    await require_module(session, principal)
    result = await create_scenario(session, principal, payload)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Interactive Academy content version not found for scenario",
        )
    await record_platform_audit(
        session,
        principal,
        request_id=request_id,
        action="academy.scenario.created",
        resource_type="academy_scenario",
        resource_id=str(result["id"]),
        data={
            "content_version_id": str(result["content_version_id"]),
            "scenario_key": result["scenario_key"],
            "version_number": result["version_number"],
            "node_count": result["node_count"],
            "edge_count": result["edge_count"],
            "status": result["status"],
            "source_fingerprint": result["source_fingerprint"],
        },
    )
    return result


async def begin_scenario(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    scenario_id: UUID,
    enrollment_id: UUID,
) -> dict[str, Any]:
    await require_module(session, principal)
    result = await start_scenario_run(
        session,
        principal,
        scenario_id=scenario_id,
        enrollment_id=enrollment_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Published enrolled scenario not found",
        )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="scenario_started",
        enrollment_id=enrollment_id,
        content_version_id=result["content_version_id"],
        data={
            "scenario_id": str(result["scenario_id"]),
            "run_id": str(result["run_id"]),
            "revision": result["revision"],
        },
    )
    return result


async def decide_scenario(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    run_id: UUID,
    payload: Any,
) -> dict[str, Any]:
    await require_module(session, principal)
    result = await apply_scenario_decision(
        session,
        principal,
        run_id=run_id,
        choice_key=payload.choice_key,
        expected_revision=payload.expected_revision,
    )
    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Scenario decision is invalid, stale or no longer available",
        )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="scenario_progressed",
        enrollment_id=result["enrollment_id"],
        content_version_id=result["content_version_id"],
        data={
            "scenario_id": str(result["scenario_id"]),
            "run_id": str(result["run_id"]),
            "current_node_key": result["current_node_key"],
            "status": result["status"],
            "score": result["score"],
            "revision": result["revision"],
        },
    )
    return result
