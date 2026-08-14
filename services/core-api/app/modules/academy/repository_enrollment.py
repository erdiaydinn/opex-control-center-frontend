from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import roles_json


async def create_manual_enrollment(
    session: AsyncSession,
    principal: Principal,
    *,
    path_id: UUID,
    subject: str,
    due_at: Any,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text("""
        INSERT INTO academy_enrollments (
            tenant_id, path_id, subject, source, status, assigned_by, due_at
        ) SELECT :tenant_id, lp.id, :subject, 'manual', 'assigned', :assigned_by, :due_at
          FROM academy_learning_paths AS lp
          WHERE lp.tenant_id=:tenant_id AND lp.id=:path_id AND lp.status='published'
        ON CONFLICT (tenant_id, subject, path_id)
        DO UPDATE SET due_at=COALESCE(EXCLUDED.due_at, academy_enrollments.due_at)
        RETURNING id, path_id, subject, source, status, assigned_at, due_at
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "path_id": path_id,
                    "subject": subject.strip(),
                    "assigned_by": principal.subject,
                    "due_at": due_at,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def reconcile_role_enrollments(
    session: AsyncSession, principal: Principal
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text("""
        WITH actor_roles AS (
            SELECT jsonb_array_elements_text(CAST(:roles AS jsonb)) AS role_key
        ), eligible AS (
            SELECT DISTINCT lp.id AS path_id, pra.due_days
            FROM academy_learning_paths AS lp
            JOIN academy_path_role_assignments AS pra
              ON pra.tenant_id=lp.tenant_id AND pra.path_id=lp.id
            JOIN actor_roles AS ar ON ar.role_key=lower(pra.role_key)
            WHERE lp.tenant_id=:tenant_id AND lp.status='published'
        )
        INSERT INTO academy_enrollments (
            tenant_id, path_id, subject, source, status, assigned_by, due_at
        ) SELECT :tenant_id, path_id, :subject, 'role', 'assigned', 'academy-role-engine',
                 CASE WHEN due_days IS NULL THEN NULL
                      ELSE CURRENT_TIMESTAMP + make_interval(days => due_days) END
          FROM eligible
        ON CONFLICT (tenant_id, subject, path_id) DO NOTHING
        RETURNING id, path_id, subject, source, status, assigned_at, due_at
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "subject": principal.subject,
                    "roles": roles_json(principal),
                },
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def list_enrollments(session: AsyncSession, principal: Principal) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text("""
        SELECT e.id, e.path_id, lp.key, lp.title_i18n, e.source, e.status,
               e.assigned_at, e.due_at, e.started_at, e.completed_at,
               e.completion_revoked_at
        FROM academy_enrollments AS e
        JOIN academy_learning_paths AS lp
          ON lp.tenant_id=e.tenant_id AND lp.id=e.path_id
        WHERE e.tenant_id=:tenant_id AND e.subject=:subject
        ORDER BY COALESCE(e.due_at, 'infinity'::timestamptz), e.assigned_at DESC
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def get_enrollment_workspace(
    session: AsyncSession,
    principal: Principal,
    enrollment_id: UUID,
) -> dict[str, Any] | None:
    enrollment = (
        (
            await session.execute(
                text("""
        SELECT
            e.id,
            e.path_id,
            e.subject,
            e.source,
            e.status,
            e.assigned_at,
            e.due_at,
            e.started_at,
            e.completed_at,
            lp.key AS path_key,
            lp.title_i18n,
            lp.description_i18n,
            lp.certificate_enabled,
            lp.completion_policy
        FROM academy_enrollments AS e
        JOIN academy_learning_paths AS lp
          ON lp.tenant_id=e.tenant_id AND lp.id=e.path_id
        WHERE e.tenant_id=:tenant_id
          AND e.id=:enrollment_id
          AND e.subject=:subject
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "enrollment_id": enrollment_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if enrollment is None:
        return None

    rows = (
        (
            await session.execute(
                text("""
        SELECT
            lpi.ordinal,
            lpi.required,
            lpi.completion_policy,
            cv.id AS content_version_id,
            cv.content_id,
            cv.version_label,
            cv.version_number,
            cv.locale,
            cv.mime_type,
            cv.duration_ms,
            cv.accessibility_metadata,
            ci.slug,
            ci.content_type,
            ci.title_i18n,
            ci.description_i18n,
            COALESCE(p.status, 'not_started') AS progress_status,
            COALESCE(p.progress_percent, 0) AS progress_percent,
            COALESCE(p.last_position_ms, 0) AS last_position_ms,
            COALESCE(p.watched_ms, 0) AS watched_ms,
            COALESCE(p.revision, 0) AS progress_revision,
            media.id AS media_id,
            media.asset_kind,
            media.delivery_mode,
            media.duration_ms AS media_duration_ms,
            media.transcode_status,
            COALESCE(quizzes.items, '[]'::jsonb) AS quizzes
        FROM academy_learning_path_items AS lpi
        JOIN academy_content_versions AS cv
          ON cv.tenant_id=lpi.tenant_id AND cv.id=lpi.content_version_id
        JOIN academy_content_items AS ci
          ON ci.tenant_id=cv.tenant_id AND ci.id=cv.content_id
        LEFT JOIN academy_progress AS p
          ON p.tenant_id=lpi.tenant_id
         AND p.enrollment_id=:enrollment_id
         AND p.content_version_id=cv.id
         AND p.subject=:subject
        LEFT JOIN LATERAL (
            SELECT ma.*
            FROM academy_media_assets AS ma
            WHERE ma.tenant_id=cv.tenant_id
              AND ma.content_version_id=cv.id
              AND ma.transcode_status='ready'
            ORDER BY ma.created_at DESC
            LIMIT 1
        ) AS media ON TRUE
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'id', q.id,
                    'kind', q.kind,
                    'checkpoint_at_ms', q.checkpoint_at_ms,
                    'pass_score', q.pass_score,
                    'max_attempts', q.max_attempts,
                    'required', q.required,
                    'version_number', q.version_number,
                    'passed', EXISTS (
                        SELECT 1
                        FROM academy_quiz_attempts AS qa
                        WHERE qa.tenant_id=q.tenant_id
                          AND qa.quiz_id=q.id
                          AND qa.enrollment_id=:enrollment_id
                          AND qa.subject=:subject
                          AND qa.passed=TRUE
                    ),
                    'attempt_count', (
                        SELECT COUNT(*)
                        FROM academy_quiz_attempts AS qa
                        WHERE qa.tenant_id=q.tenant_id
                          AND qa.quiz_id=q.id
                          AND qa.enrollment_id=:enrollment_id
                          AND qa.subject=:subject
                    )
                ) ORDER BY COALESCE(q.checkpoint_at_ms, 9223372036854775807), q.id
            ) AS items
            FROM academy_quizzes AS q
            WHERE q.tenant_id=cv.tenant_id
              AND q.content_version_id=cv.id
              AND q.status='published'
        ) AS quizzes ON TRUE
        WHERE lpi.tenant_id=:tenant_id
          AND lpi.path_id=:path_id
          AND cv.status='published'
          AND ci.status='published'
        ORDER BY lpi.ordinal
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "path_id": enrollment["path_id"],
                    "enrollment_id": enrollment_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .all()
    )

    return {
        "enrollment": dict(enrollment),
        "items": [dict(row) for row in rows],
    }
