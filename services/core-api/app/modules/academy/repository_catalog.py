from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import roles_json


async def list_entitled_content(
    session: AsyncSession, principal: Principal
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text("""
        WITH actor_roles AS (
            SELECT jsonb_array_elements_text(CAST(:roles AS jsonb)) AS role_key
        ), entitled AS (
            SELECT ae.resource_id AS content_id
            FROM academy_entitlements AS ae
            LEFT JOIN actor_roles AS ar
              ON ae.principal_type='role' AND lower(ae.principal_key)=ar.role_key
            WHERE ae.tenant_id=:tenant_id AND ae.resource_type='content'
              AND ae.permission IN ('view','learn','manage')
              AND (ae.starts_at IS NULL OR ae.starts_at<=CURRENT_TIMESTAMP)
              AND (ae.ends_at IS NULL OR ae.ends_at>CURRENT_TIMESTAMP)
              AND ((ae.principal_type='subject' AND ae.principal_key=:subject)
                   OR ar.role_key IS NOT NULL)
        ), enrolled AS (
            SELECT cv.content_id
            FROM academy_enrollments AS e
            JOIN academy_learning_path_items AS lpi
              ON lpi.tenant_id=e.tenant_id AND lpi.path_id=e.path_id
            JOIN academy_content_versions AS cv
              ON cv.tenant_id=lpi.tenant_id AND cv.id=lpi.content_version_id
            WHERE e.tenant_id=:tenant_id AND e.subject=:subject
              AND e.status IN ('assigned','in_progress','completed')
        )
        SELECT DISTINCT ci.id, ci.content_type, ci.slug, ci.title_i18n,
                        ci.description_i18n, ci.status
        FROM academy_content_items AS ci
        WHERE ci.tenant_id=:tenant_id AND ci.status='published'
          AND (ci.id IN (SELECT content_id FROM entitled)
               OR ci.id IN (SELECT content_id FROM enrolled))
        ORDER BY ci.slug
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


async def get_media_asset(
    session: AsyncSession, principal: Principal, media_id: UUID
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text("""
        WITH actor_roles AS (
            SELECT jsonb_array_elements_text(CAST(:roles AS jsonb)) AS role_key
        ), allowed_versions AS (
            SELECT lpi.content_version_id
            FROM academy_enrollments AS e
            JOIN academy_learning_path_items AS lpi
              ON lpi.tenant_id=e.tenant_id AND lpi.path_id=e.path_id
            WHERE e.tenant_id=:tenant_id AND e.subject=:subject
              AND e.status IN ('assigned','in_progress','completed')
            UNION
            SELECT cv.id
            FROM academy_content_versions AS cv
            JOIN academy_entitlements AS ae
              ON ae.tenant_id=cv.tenant_id AND ae.resource_type='content'
             AND ae.resource_id=cv.content_id
             AND ae.permission IN ('view','learn','manage')
            LEFT JOIN actor_roles AS ar
              ON ae.principal_type='role' AND lower(ae.principal_key)=ar.role_key
            WHERE cv.tenant_id=:tenant_id
              AND (ae.starts_at IS NULL OR ae.starts_at<=CURRENT_TIMESTAMP)
              AND (ae.ends_at IS NULL OR ae.ends_at>CURRENT_TIMESTAMP)
              AND ((ae.principal_type='subject' AND ae.principal_key=:subject)
                   OR ar.role_key IS NOT NULL)
        )
        SELECT ma.id, ma.content_version_id, ma.delivery_key, ma.manifest_path,
               ma.delivery_mode, ma.encryption_mode, ma.segment_duration_seconds,
               ma.transcode_status, cv.duration_ms
        FROM academy_media_assets AS ma
        JOIN academy_content_versions AS cv
          ON cv.tenant_id=ma.tenant_id AND cv.id=ma.content_version_id
        WHERE ma.tenant_id=:tenant_id AND ma.id=:media_id
          AND ma.transcode_status='ready' AND cv.status='published'
          AND ma.content_version_id IN (SELECT content_version_id FROM allowed_versions)
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "subject": principal.subject,
                    "roles": roles_json(principal),
                    "media_id": media_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def list_checkpoints(
    session: AsyncSession,
    principal: Principal,
    enrollment_id: UUID,
    content_version_id: UUID,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text("""
        SELECT q.id AS quiz_id, q.checkpoint_at_ms, q.pass_score, q.max_attempts,
               q.required, q.version_number, COALESCE(bool_or(qa.passed), FALSE) AS passed
        FROM academy_enrollments AS e
        JOIN academy_learning_path_items AS lpi
          ON lpi.tenant_id=e.tenant_id AND lpi.path_id=e.path_id
         AND lpi.content_version_id=:content_version_id
        JOIN academy_quizzes AS q
          ON q.tenant_id=lpi.tenant_id AND q.content_version_id=lpi.content_version_id
         AND q.kind='checkpoint' AND q.status='published'
        LEFT JOIN academy_quiz_attempts AS qa
          ON qa.tenant_id=q.tenant_id AND qa.quiz_id=q.id
         AND qa.enrollment_id=e.id AND qa.subject=e.subject
        WHERE e.tenant_id=:tenant_id AND e.id=:enrollment_id
          AND e.subject=:subject AND e.status IN ('assigned','in_progress','completed')
        GROUP BY q.id
        ORDER BY q.checkpoint_at_ms, q.version_number
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "enrollment_id": enrollment_id,
                    "content_version_id": content_version_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def get_quiz_public_definition(
    session: AsyncSession,
    principal: Principal,
    quiz_id: UUID,
    enrollment_id: UUID,
) -> dict[str, Any] | None:
    quiz = (
        (
            await session.execute(
                text("""
        SELECT q.id, q.content_version_id, q.kind, q.checkpoint_at_ms,
               q.pass_score, q.max_attempts, q.required, q.version_number
        FROM academy_quizzes AS q
        JOIN academy_learning_path_items AS lpi
          ON lpi.tenant_id=q.tenant_id AND lpi.content_version_id=q.content_version_id
        JOIN academy_enrollments AS e
          ON e.tenant_id=lpi.tenant_id AND e.path_id=lpi.path_id
        WHERE q.tenant_id=:tenant_id AND q.id=:quiz_id AND q.status='published'
          AND e.id=:enrollment_id AND e.subject=:subject
          AND e.status IN ('assigned','in_progress','completed')
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "quiz_id": quiz_id,
                    "enrollment_id": enrollment_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if quiz is None:
        return None

    rows = (
        (
            await session.execute(
                text("""
        SELECT q.id AS question_id, q.ordinal AS question_ordinal, q.question_type,
               q.prompt_i18n, q.points, q.required, o.id AS option_id,
               o.ordinal AS option_ordinal, o.label_i18n
        FROM academy_questions AS q
        JOIN academy_question_options AS o
          ON o.tenant_id=q.tenant_id AND o.question_id=q.id
        WHERE q.tenant_id=:tenant_id AND q.quiz_id=:quiz_id
        ORDER BY q.ordinal, o.ordinal
    """),
                {"tenant_id": principal.tenant_id, "quiz_id": quiz_id},
            )
        )
        .mappings()
        .all()
    )
    questions: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        item = questions.setdefault(
            row["question_id"],
            {
                "id": row["question_id"],
                "ordinal": row["question_ordinal"],
                "question_type": row["question_type"],
                "prompt_i18n": row["prompt_i18n"],
                "points": float(row["points"]),
                "required": row["required"],
                "options": [],
            },
        )
        item["options"].append(
            {
                "id": row["option_id"],
                "ordinal": row["option_ordinal"],
                "label_i18n": row["label_i18n"],
            }
        )
    return {**dict(quiz), "questions": list(questions.values())}
