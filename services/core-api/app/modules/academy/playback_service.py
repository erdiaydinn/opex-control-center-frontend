from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.media import (
    AcademyMediaUnavailable,
    build_playback_url,
    issue_playback_token,
    load_media_config,
    media_unavailable_http,
)
from app.modules.academy.repository import (
    get_blocking_checkpoint,
    get_media_asset,
    record_learning_event,
)
from app.modules.academy.repository_playback import (
    close_playback_session,
    commit_playback_heartbeat,
    create_playback_session,
    get_playback_session_for_update,
)
from app.modules.academy.repository_utils import stable_fingerprint

PLAYBACK_SESSION_TTL = timedelta(hours=8)
DEFAULT_MAX_PLAYBACK_RATE = 1.25
DEFAULT_SEEK_TOLERANCE_MS = 3000
CLIENT_CLOCK_MULTIPLIER = 1.05
SERVER_CLOCK_MULTIPLIER = 1.10


async def start_verified_playback(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    enrollment_id: UUID,
    media_id: UUID,
) -> dict[str, Any]:
    media = await get_media_asset(session, principal, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Accessible ready media asset not found")

    try:
        config = load_media_config()
        token, expires_at = issue_playback_token(
            config,
            principal,
            media_id=media_id,
            content_version_id=media["content_version_id"],
            delivery_key=media["delivery_key"],
        )
    except AcademyMediaUnavailable as exc:
        raise media_unavailable_http(exc) from exc

    now = datetime.now(UTC)
    playback = await create_playback_session(
        session,
        principal,
        enrollment_id=enrollment_id,
        media_id=media_id,
        session_nonce=token_hex(16),
        max_playback_rate=DEFAULT_MAX_PLAYBACK_RATE,
        seek_tolerance_ms=DEFAULT_SEEK_TOLERANCE_MS,
        expires_at=now + PLAYBACK_SESSION_TTL,
    )
    if playback is None:
        raise HTTPException(
            status_code=404,
            detail="Active enrolled video target not found for verified playback",
        )

    playback_url = build_playback_url(
        config,
        delivery_key=media["delivery_key"],
        manifest_path=media["manifest_path"],
        token=token,
        delivery_mode=media["delivery_mode"],
    )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="verified_playback_started",
        enrollment_id=enrollment_id,
        content_version_id=media["content_version_id"],
        data={
            "media_id": str(media_id),
            "playback_session_id": str(playback["id"]),
            "grant_expires_at": expires_at,
            "session_expires_at": playback["expires_at"].isoformat(),
            "max_playback_rate": float(playback["max_playback_rate"]),
        },
    )
    return {
        "playback_session_id": playback["id"],
        "playback_url": playback_url,
        "authorization_token": token,
        "grant_expires_in_seconds": config.token_ttl_seconds,
        "session_expires_at": playback["expires_at"],
        "content_version_id": playback["content_version_id"],
        "max_playback_rate": float(playback["max_playback_rate"]),
        "seek_tolerance_ms": int(playback["seek_tolerance_ms"]),
        "verified_until_ms": int(playback["verified_until_ms"]),
        "verified_watch_ms": int(playback["verified_watch_ms"]),
        "forward_seek_policy": "deny-unverified",
        "background_policy": "no-forward-credit-while-hidden",
        "checkpoint_policy": "hard-stop-before-required-checkpoint",
        "evidence_authority": "server-receipts",
        "download_protection": "friction-not-guarantee",
    }


async def record_verified_heartbeat(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    playback_session_id: UUID,
    payload: Any,
) -> dict[str, Any]:
    state = await get_playback_session_for_update(session, principal, playback_session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Verified playback session not found")

    now = datetime.now(UTC)
    if state["status"] != "active" or state["expires_at"] <= now:
        raise HTTPException(status_code=409, detail="Verified playback session is not active")

    expected_sequence = int(state["last_sequence"]) + 1
    if payload.sequence_no != expected_sequence:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Playback heartbeat sequence conflict",
                "expected_sequence": expected_sequence,
            },
        )

    max_rate = float(state["max_playback_rate"])
    if payload.playback_rate > max_rate:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Playback rate exceeds verified-learning policy",
                "max_playback_rate": max_rate,
            },
        )

    duration_ms = int(state["duration_ms"] or 0)
    if duration_ms and payload.to_position_ms > duration_ms + int(state["seek_tolerance_ms"]):
        raise HTTPException(status_code=400, detail="Playback position exceeds media duration")

    verified_until = int(state["verified_until_ms"])
    seek_tolerance = int(state["seek_tolerance_ms"])
    if payload.from_position_ms > verified_until + seek_tolerance:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Forward seek into unverified video is not allowed",
                "verified_until_ms": verified_until,
                "max_seek_position_ms": verified_until + seek_tolerance,
            },
        )

    checkpoint = await get_blocking_checkpoint(
        session,
        principal,
        enrollment_id=state["enrollment_id"],
        content_version_id=state["content_version_id"],
        requested_position_ms=payload.to_position_ms,
    )
    if checkpoint is not None:
        checkpoint_at_ms = int(checkpoint["checkpoint_at_ms"])
        if verified_until < checkpoint_at_ms <= payload.to_position_ms:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Required checkpoint blocks playback continuation",
                    "quiz_id": str(checkpoint["quiz_id"]),
                    "checkpoint_at_ms": checkpoint_at_ms,
                    "quiz_version": checkpoint["version_number"],
                    "max_seek_position_ms": checkpoint_at_ms,
                },
            )

    position_delta = payload.to_position_ms - payload.from_position_ms
    if payload.visibility == "hidden" and position_delta > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Hidden playback does not earn verified watch coverage",
                "verified_until_ms": verified_until,
            },
        )

    server_elapsed_ms = max(
        0,
        int((now - state["last_heartbeat_at"]).total_seconds() * 1000),
    )
    allowed_by_client = int(
        payload.client_elapsed_ms * payload.playback_rate * CLIENT_CLOCK_MULTIPLIER
    )
    allowed_by_server = int(server_elapsed_ms * max_rate * SERVER_CLOCK_MULTIPLIER)
    allowed_position_advance = min(allowed_by_client, allowed_by_server)

    if position_delta > allowed_position_advance and position_delta > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Playback advanced faster than verified wall-clock budget",
                "allowed_advance_ms": allowed_position_advance,
                "requested_advance_ms": position_delta,
                "verified_until_ms": verified_until,
            },
        )

    # Rewatching already-verified material is allowed but never double-counted.
    new_verified_until = verified_until
    if (
        payload.visibility != "hidden"
        and payload.to_position_ms > verified_until
        and payload.from_position_ms <= verified_until + seek_tolerance
    ):
        new_verified_until = payload.to_position_ms
    if duration_ms:
        new_verified_until = min(duration_ms, new_verified_until)
    accepted_advance = max(0, new_verified_until - verified_until)
    new_verified_watch_ms = int(state["verified_watch_ms"]) + accepted_advance
    if duration_ms:
        new_verified_watch_ms = min(duration_ms, new_verified_watch_ms)

    receipt_hash = stable_fingerprint(
        {
            "contract": "academy-playback-receipt-v1",
            "tenant_id": principal.tenant_id,
            "subject": principal.subject,
            "playback_session_id": playback_session_id,
            "sequence_no": payload.sequence_no,
            "from_position_ms": payload.from_position_ms,
            "to_position_ms": payload.to_position_ms,
            "client_elapsed_ms": payload.client_elapsed_ms,
            "playback_rate": payload.playback_rate,
            "visibility": payload.visibility,
            "accepted_advance_ms": accepted_advance,
        }
    )
    updated = await commit_playback_heartbeat(
        session,
        principal,
        playback_session_id=playback_session_id,
        sequence_no=payload.sequence_no,
        from_position_ms=payload.from_position_ms,
        to_position_ms=payload.to_position_ms,
        client_elapsed_ms=payload.client_elapsed_ms,
        accepted_advance_ms=accepted_advance,
        playback_rate=payload.playback_rate,
        visibility=payload.visibility,
        receipt_hash=receipt_hash,
        new_last_position_ms=payload.to_position_ms,
        new_verified_until_ms=new_verified_until,
        new_verified_watch_ms=new_verified_watch_ms,
        expected_revision=int(state["revision"]),
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="Playback session revision conflict")

    verified_percent = (
        min(100.0, new_verified_watch_ms * 100.0 / duration_ms) if duration_ms else 0.0
    )
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="verified_playback_heartbeat",
        enrollment_id=state["enrollment_id"],
        content_version_id=state["content_version_id"],
        data={
            "playback_session_id": str(playback_session_id),
            "sequence_no": payload.sequence_no,
            "accepted_advance_ms": accepted_advance,
            "verified_until_ms": new_verified_until,
            "verified_watch_ms": new_verified_watch_ms,
            "verified_percent": round(verified_percent, 2),
            "receipt_hash": receipt_hash,
        },
    )
    return {
        **updated,
        "accepted_advance_ms": accepted_advance,
        "verified_percent": round(verified_percent, 2),
        "receipt_hash": receipt_hash,
        "max_seek_position_ms": new_verified_until + seek_tolerance,
    }


async def finish_verified_playback(
    session: AsyncSession,
    principal: Principal,
    *,
    request_id: str,
    playback_session_id: UUID,
) -> dict[str, Any]:
    result = await close_playback_session(session, principal, playback_session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Active verified playback session not found")
    await record_learning_event(
        session,
        principal,
        request_id=request_id,
        event_type="verified_playback_closed",
        enrollment_id=result["enrollment_id"],
        content_version_id=result["content_version_id"],
        data={
            "playback_session_id": str(playback_session_id),
            "verified_until_ms": int(result["verified_until_ms"]),
            "verified_watch_ms": int(result["verified_watch_ms"]),
        },
    )
    return result
