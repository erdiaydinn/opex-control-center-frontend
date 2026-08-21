from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def get_progress_target(
    session: AsyncSession,
    principal: Principal,
    enrollment_id: UUID,
    content_version_id: UUID,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT e.id AS enrollment_id, e.status AS enrollment_status, e.path_id,
                       ci.content_type, cv.id AS content_version_id, cv.duration_ms,
                       lpi.required, lpi.completion_policy,
                       p.status AS progress_status, COALESCE(p.progress_percent, 0) AS progress_percent,
                       COALESCE(p.last_position_ms, 0) AS last_position_ms,
                       COALESCE(p.max_position_ms, 0) AS max_position_ms,
                       COALESCE(p.watched_ms, 0) AS watched_ms,
                       COALESCE(p.revision, 0) AS revision
                FROM academy_enrollments AS e
                JOIN academy_learning_path_items AS lpi
                  ON lpi.tenant_id = e.tenant_id AND lpi.path_id = e.path_id
                 AND lpi.content_version_id = :content_version_id
                JOIN academy_content_versions AS cv
                  ON cv.tenant_id = lpi.tenant_id AND cv.id = lpi.content_version_id
                JOIN academy_content_items AS ci
                  ON ci.tenant_id = cv.tenant_id AND ci.id = cv.content_id
                LEFT JOIN academy_progress AS p
                  ON p.tenant_id = e.tenant_id AND p.enrollment_id = e.id
                 AND p.content_version_id = cv.id
                WHERE e.tenant_id = :tenant_id AND e.id = :enrollment_id
                  AND e.subject = :subject AND e.status IN ('assigned', 'in_progress')
                FOR UPDATE OF e
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
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


async def get_blocking_checkpoint(
    session: AsyncSession,
    principal: Principal,
    *,
    enrollment_id: UUID,
    content_version_id: UUID,
    requested_position_ms: int,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT q.id AS quiz_id, q.checkpoint_at_ms, q.version_number
                FROM academy_quizzes AS q
                WHERE q.tenant_id = :tenant_id AND q.content_version_id = :content_version_id
                  AND q.kind = 'checkpoint' AND q.status = 'published' AND q.required = TRUE
                  AND q.checkpoint_at_ms <= :requested_position_ms
                  AND NOT EXISTS (
                      SELECT 1 FROM academy_quiz_attempts AS qa
                      WHERE qa.tenant_id = q.tenant_id AND qa.quiz_id = q.id
                        AND qa.enrollment_id = :enrollment_id AND qa.subject = :subject
                        AND qa.passed = TRUE
                  )
                ORDER BY q.checkpoint_at_ms, q.version_number
                LIMIT 1
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "content_version_id": content_version_id,
                    "requested_position_ms": requested_position_ms,
                    "enrollment_id": enrollment_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def save_progress(
    session: AsyncSession,
    principal: Principal,
    enrollment_id: UUID,
    content_version_id: UUID,
    *,
    status: str,
    progress_percent: float,
    last_position_ms: int,
    max_position_ms: int,
    watched_ms: int,
    completed: bool,
    expected_revision: int,
) -> dict[str, Any] | None:
    if expected_revision == 0:
        row = (
            (
                await session.execute(
                    text(
                        """
                    INSERT INTO academy_progress (
                        tenant_id, enrollment_id, content_version_id, subject, status,
                        progress_percent, last_position_ms, max_position_ms, watched_ms,
                        revision, last_checkpoint_at, completed_at, updated_at
                    ) VALUES (
                        :tenant_id, :enrollment_id, :content_version_id, :subject, :status,
                        :progress_percent, :last_position_ms, :max_position_ms, :watched_ms,
                        1, CURRENT_TIMESTAMP,
                        CASE WHEN :completed THEN CURRENT_TIMESTAMP ELSE NULL END,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (tenant_id, enrollment_id, content_version_id) DO NOTHING
                    RETURNING id, enrollment_id, content_version_id, status, progress_percent,
                              last_position_ms, max_position_ms, watched_ms, revision,
                              completed_at, updated_at
                    """
                    ),
                    {
                        "tenant_id": principal.tenant_id,
                        "enrollment_id": enrollment_id,
                        "content_version_id": content_version_id,
                        "subject": principal.subject,
                        "status": status,
                        "progress_percent": progress_percent,
                        "last_position_ms": last_position_ms,
                        "max_position_ms": max_position_ms,
                        "watched_ms": watched_ms,
                        "completed": completed,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
    else:
        row = (
            (
                await session.execute(
                    text(
                        """
                    UPDATE academy_progress
                    SET status = :status,
                        progress_percent = GREATEST(progress_percent, :progress_percent),
                        last_position_ms = :last_position_ms,
                        max_position_ms = GREATEST(max_position_ms, :max_position_ms),
                        watched_ms = GREATEST(watched_ms, :watched_ms),
                        revision = revision + 1,
                        last_checkpoint_at = CURRENT_TIMESTAMP,
                        completed_at = CASE
                            WHEN completed_at IS NOT NULL THEN completed_at
                            WHEN :completed THEN CURRENT_TIMESTAMP ELSE NULL END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = :tenant_id AND enrollment_id = :enrollment_id
                      AND content_version_id = :content_version_id AND subject = :subject
                      AND revision = :expected_revision
                    RETURNING id, enrollment_id, content_version_id, status, progress_percent,
                              last_position_ms, max_position_ms, watched_ms, revision,
                              completed_at, updated_at
                    """
                    ),
                    {
                        "tenant_id": principal.tenant_id,
                        "enrollment_id": enrollment_id,
                        "content_version_id": content_version_id,
                        "subject": principal.subject,
                        "status": status,
                        "progress_percent": progress_percent,
                        "last_position_ms": last_position_ms,
                        "max_position_ms": max_position_ms,
                        "watched_ms": watched_ms,
                        "completed": completed,
                        "expected_revision": expected_revision,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )

    if row is None:
        return None
    await session.execute(
        text(
            """
            UPDATE academy_enrollments
            SET status = CASE WHEN status = 'assigned' THEN 'in_progress' ELSE status END,
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
            WHERE tenant_id = :tenant_id AND id = :enrollment_id AND subject = :subject
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "enrollment_id": enrollment_id,
            "subject": principal.subject,
        },
    )
    return dict(row)


async def get_progress_snapshot(
    session: AsyncSession,
    principal: Principal,
    enrollment_id: UUID,
    content_version_id: UUID,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT id, enrollment_id, content_version_id, status, progress_percent,
                       last_position_ms, max_position_ms, watched_ms, revision,
                       completed_at, updated_at
                FROM academy_progress
                WHERE tenant_id = :tenant_id AND enrollment_id = :enrollment_id
                  AND content_version_id = :content_version_id AND subject = :subject
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
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
