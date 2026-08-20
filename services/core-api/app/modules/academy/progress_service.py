from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository import (
    claim_idempotency_key,
    get_blocking_checkpoint,
    get_progress_snapshot,
    get_progress_target,
    record_learning_event,
    save_progress,
)
from app.modules.academy.repository_playback import get_verified_playback_snapshot
from app.modules.academy.repository_utils import stable_fingerprint
from app.modules.academy.service import require_module


def _request_fingerprint(operation: str, value: object) -> str:
    return stable_fingerprint({"operation": operation, "payload": value})


def _required_watch_percent(target: dict[str, Any]) -> float:
    if target.get("content_type") not in {"video", "live"}:
        return 0.0
    if int(target.get("duration_ms") or 0) <= 0:
        return 0.0

    policy = target.get("completion_policy")
    raw_value = policy.get("required_watch_percent", 90) if isinstance(policy, dict) else 90
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = 90.0
    return min(100.0, max(0.0, value))


async def update_progress(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    enrollment_id: UUID,
    payload: Any,
    idempotency_key: str | None,
) -> dict[str, Any]:
    await require_module(session, principal)
    fingerprint = _request_fingerprint(
        "academy.progress.v2",
        {"enrollment_id": enrollment_id, **payload.model_dump(mode="json")},
    )
    claim = await claim_idempotency_key(
        session,
        principal,
        operation="academy.progress.v2",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        resource_id=f"{enrollment_id}:{payload.content_version_id}",
    )
    if not claim["claimed"]:
        if claim["request_fingerprint"] != fingerprint:
            raise HTTPException(
                status_code=409, detail="Idempotency key was already used with a different request"
            )
        snapshot = await get_progress_snapshot(
            session, principal, enrollment_id, payload.content_version_id
        )
        if snapshot is None:
            raise HTTPException(
                status_code=409, detail="Idempotent progress result is no longer available"
            )
        return {**snapshot, "idempotent_replay": True}

    target = await get_progress_target(
        session, principal, enrollment_id, payload.content_version_id
    )
    if target is None:
        raise HTTPException(
            status_code=404, detail="Active Academy enrollment/content target not found"
        )

    current_revision = int(target["revision"])
    if payload.expected_revision is not None and payload.expected_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={"message": "Progress revision conflict", "current_revision": current_revision},
        )

    requested_position = payload.last_position_ms
    duration_ms = int(target["duration_ms"] or 0)
    if duration_ms and requested_position > duration_ms + 5000:
        raise HTTPException(status_code=400, detail="Progress position exceeds media duration")

    checkpoint = await get_blocking_checkpoint(
        session,
        principal,
        enrollment_id=enrollment_id,
        content_version_id=payload.content_version_id,
        requested_position_ms=requested_position,
    )
    if checkpoint:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Required video checkpoint must be completed before continuing",
                "quiz_id": str(checkpoint["quiz_id"]),
                "checkpoint_at_ms": checkpoint["checkpoint_at_ms"],
                "quiz_version": checkpoint["version_number"],
            },
        )

    is_timed_media = target.get("content_type") in {"video", "live"} and duration_ms > 0
    playback_evidence: dict[str, Any] | None = None
    if is_timed_media:
        if payload.playback_session_id is None:
            raise HTTPException(
                status_code=409,
                detail="Verified playback session is required for timed-media progress",
            )
        playback_evidence = await get_verified_playback_snapshot(
            session,
            principal,
            playback_session_id=payload.playback_session_id,
            enrollment_id=enrollment_id,
            content_version_id=payload.content_version_id,
        )
        if playback_evidence is None:
            raise HTTPException(
                status_code=409,
                detail="Active verified playback evidence is not available",
            )
        verified_until = int(playback_evidence["verified_until_ms"])
        seek_tolerance = int(playback_evidence["seek_tolerance_ms"])
        if requested_position > verified_until + seek_tolerance:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Progress cannot advance beyond verified playback coverage",
                    "verified_until_ms": verified_until,
                    "max_seek_position_ms": verified_until + seek_tolerance,
                },
            )
        watched_ms = max(int(target["watched_ms"]), int(playback_evidence["verified_watch_ms"]))
        max_position_ms = max(int(target["max_position_ms"]), verified_until)
        evidence_mode = "server-verified-playback"
    else:
        watched_ms = int(target["watched_ms"]) + payload.watched_delta_ms
        max_position_ms = max(int(target["max_position_ms"]), requested_position)
        evidence_mode = "direct-progress"

    if duration_ms:
        watched_ms = min(duration_ms, watched_ms)
        max_position_ms = min(duration_ms, max_position_ms)
        progress_percent = min(100.0, max_position_ms * 100.0 / duration_ms)
        watched_percent = min(100.0, watched_ms * 100.0 / duration_ms)
    else:
        progress_percent = (
            100.0 if payload.complete_requested else float(target["progress_percent"])
        )
        watched_percent = 100.0 if payload.complete_requested else 0.0

    required_watch_percent = _required_watch_percent(target)
    watched_requirement_met = watched_percent >= required_watch_percent
    completed = bool(
        payload.complete_requested
        and progress_percent >= 90.0
        and watched_requirement_met
    )
    progress_status = "completed" if completed else "in_progress"
    row = await save_progress(
        session,
        principal,
        enrollment_id,
        payload.content_version_id,
        status=progress_status,
        progress_percent=progress_percent,
        last_position_ms=requested_position,
        max_position_ms=max_position_ms,
        watched_ms=watched_ms,
        completed=completed,
        expected_revision=current_revision,
    )
    if row is None:
        raise HTTPException(
            status_code=409,
            detail={"message": "Progress revision conflict", "current_revision": current_revision},
        )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="progress_updated",
        enrollment_id=enrollment_id,
        content_version_id=payload.content_version_id,
        idempotency_key=idempotency_key,
        data={
            "contract": "academy-progress-v2",
            "evidence_mode": evidence_mode,
            "playback_session_id": (
                str(payload.playback_session_id) if payload.playback_session_id else None
            ),
            "revision": row["revision"],
            "progress_percent": float(row["progress_percent"]),
            "watched_percent": round(watched_percent, 2),
            "required_watch_percent": required_watch_percent,
        },
    )
    return {
        **row,
        "idempotent_replay": False,
        "evidence_mode": evidence_mode,
        "watched_percent": round(watched_percent, 2),
        "required_watch_percent": required_watch_percent,
    }
