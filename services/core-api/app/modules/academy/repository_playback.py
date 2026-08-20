from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def create_playback_session(
    session: AsyncSession,
    principal: Principal,
    *,
    enrollment_id: UUID,
    media_id: UUID,
    session_nonce: str,
    max_playback_rate: float,
    seek_tolerance_ms: int,
    expires_at: datetime,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_playback_sessions (
                        tenant_id,
                        enrollment_id,
                        content_version_id,
                        media_id,
                        subject,
                        session_nonce,
                        max_playback_rate,
                        seek_tolerance_ms,
                        expires_at
                    )
                    SELECT
                        e.tenant_id,
                        e.id,
                        ma.content_version_id,
                        ma.id,
                        e.subject,
                        :session_nonce,
                        :max_playback_rate,
                        :seek_tolerance_ms,
                        :expires_at
                    FROM academy_enrollments AS e
                    JOIN academy_learning_path_items AS lpi
                      ON lpi.tenant_id = e.tenant_id
                     AND lpi.path_id = e.path_id
                    JOIN academy_media_assets AS ma
                      ON ma.tenant_id = lpi.tenant_id
                     AND ma.content_version_id = lpi.content_version_id
                    JOIN academy_content_versions AS cv
                      ON cv.tenant_id = ma.tenant_id
                     AND cv.id = ma.content_version_id
                    JOIN academy_content_items AS ci
                      ON ci.tenant_id = cv.tenant_id
                     AND ci.id = cv.content_id
                    WHERE e.tenant_id = :tenant_id
                      AND e.id = :enrollment_id
                      AND e.subject = :subject
                      AND e.status IN ('assigned', 'in_progress')
                      AND ma.id = :media_id
                      AND ma.transcode_status = 'ready'
                      AND cv.status = 'published'
                      AND ci.content_type IN ('video', 'live')
                    RETURNING id, enrollment_id, content_version_id, media_id, subject,
                              status, max_playback_rate, seek_tolerance_ms, last_sequence,
                              last_position_ms, verified_until_ms, verified_watch_ms,
                              revision, started_at, last_heartbeat_at, expires_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "enrollment_id": enrollment_id,
                    "media_id": media_id,
                    "subject": principal.subject,
                    "session_nonce": session_nonce,
                    "max_playback_rate": max_playback_rate,
                    "seek_tolerance_ms": seek_tolerance_ms,
                    "expires_at": expires_at,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def get_playback_session_for_update(
    session: AsyncSession,
    principal: Principal,
    playback_session_id: UUID,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT ps.id, ps.enrollment_id, ps.content_version_id, ps.media_id,
                           ps.subject, ps.status, ps.max_playback_rate,
                           ps.seek_tolerance_ms, ps.last_sequence,
                           ps.last_position_ms, ps.verified_until_ms,
                           ps.verified_watch_ms, ps.revision, ps.started_at,
                           ps.last_heartbeat_at, ps.expires_at,
                           COALESCE(cv.duration_ms, ma.duration_ms, 0) AS duration_ms
                    FROM academy_playback_sessions AS ps
                    JOIN academy_content_versions AS cv
                      ON cv.tenant_id = ps.tenant_id
                     AND cv.id = ps.content_version_id
                    JOIN academy_media_assets AS ma
                      ON ma.tenant_id = ps.tenant_id
                     AND ma.id = ps.media_id
                    WHERE ps.tenant_id = :tenant_id
                      AND ps.id = :playback_session_id
                      AND ps.subject = :subject
                    FOR UPDATE OF ps
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "playback_session_id": playback_session_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def commit_playback_heartbeat(
    session: AsyncSession,
    principal: Principal,
    *,
    playback_session_id: UUID,
    sequence_no: int,
    from_position_ms: int,
    to_position_ms: int,
    client_elapsed_ms: int,
    accepted_advance_ms: int,
    playback_rate: float,
    visibility: str,
    receipt_hash: str,
    new_last_position_ms: int,
    new_verified_until_ms: int,
    new_verified_watch_ms: int,
    expected_revision: int,
) -> dict[str, Any] | None:
    updated = (
        (
            await session.execute(
                text(
                    """
                    UPDATE academy_playback_sessions
                    SET last_sequence = :sequence_no,
                        last_position_ms = :last_position_ms,
                        verified_until_ms = :verified_until_ms,
                        verified_watch_ms = :verified_watch_ms,
                        revision = revision + 1,
                        last_heartbeat_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = :tenant_id
                      AND id = :playback_session_id
                      AND subject = :subject
                      AND status = 'active'
                      AND revision = :expected_revision
                      AND expires_at > CURRENT_TIMESTAMP
                    RETURNING id, enrollment_id, content_version_id, media_id,
                              status, max_playback_rate, seek_tolerance_ms,
                              last_sequence, last_position_ms, verified_until_ms,
                              verified_watch_ms, revision, started_at,
                              last_heartbeat_at, expires_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "playback_session_id": playback_session_id,
                    "subject": principal.subject,
                    "sequence_no": sequence_no,
                    "last_position_ms": new_last_position_ms,
                    "verified_until_ms": new_verified_until_ms,
                    "verified_watch_ms": new_verified_watch_ms,
                    "expected_revision": expected_revision,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if updated is None:
        return None

    await session.execute(
        text(
            """
            INSERT INTO academy_playback_receipts (
                tenant_id,
                playback_session_id,
                sequence_no,
                from_position_ms,
                to_position_ms,
                client_elapsed_ms,
                accepted_advance_ms,
                playback_rate,
                visibility,
                receipt_hash
            ) VALUES (
                :tenant_id,
                :playback_session_id,
                :sequence_no,
                :from_position_ms,
                :to_position_ms,
                :client_elapsed_ms,
                :accepted_advance_ms,
                :playback_rate,
                :visibility,
                :receipt_hash
            )
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "playback_session_id": playback_session_id,
            "sequence_no": sequence_no,
            "from_position_ms": from_position_ms,
            "to_position_ms": to_position_ms,
            "client_elapsed_ms": client_elapsed_ms,
            "accepted_advance_ms": accepted_advance_ms,
            "playback_rate": playback_rate,
            "visibility": visibility,
            "receipt_hash": receipt_hash,
        },
    )
    return dict(updated)


async def get_verified_playback_snapshot(
    session: AsyncSession,
    principal: Principal,
    *,
    playback_session_id: UUID,
    enrollment_id: UUID,
    content_version_id: UUID,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, enrollment_id, content_version_id, media_id,
                           status, seek_tolerance_ms, last_position_ms,
                           verified_until_ms, verified_watch_ms, revision,
                           last_heartbeat_at, expires_at
                    FROM academy_playback_sessions
                    WHERE tenant_id = :tenant_id
                      AND id = :playback_session_id
                      AND enrollment_id = :enrollment_id
                      AND content_version_id = :content_version_id
                      AND subject = :subject
                      AND status = 'active'
                      AND expires_at > CURRENT_TIMESTAMP
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "playback_session_id": playback_session_id,
                    "enrollment_id": enrollment_id,
                    "content_version_id": content_version_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def close_playback_session(
    session: AsyncSession,
    principal: Principal,
    playback_session_id: UUID,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    UPDATE academy_playback_sessions
                    SET status = 'closed',
                        closed_at = COALESCE(closed_at, CURRENT_TIMESTAMP),
                        revision = revision + 1
                    WHERE tenant_id = :tenant_id
                      AND id = :playback_session_id
                      AND subject = :subject
                      AND status = 'active'
                    RETURNING id, enrollment_id, content_version_id, media_id,
                              status, last_position_ms, verified_until_ms,
                              verified_watch_ms, revision, closed_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "playback_session_id": playback_session_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None
