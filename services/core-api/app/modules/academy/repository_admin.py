from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def list_admin_content(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text("""
        SELECT
            ci.id,
            ci.content_type,
            ci.slug,
            ci.title_i18n,
            ci.description_i18n,
            ci.status,
            ci.created_by,
            ci.created_at,
            ci.updated_at,
            latest.id AS latest_version_id,
            latest.version_label,
            latest.version_number,
            latest.locale,
            latest.mime_type,
            latest.duration_ms,
            latest.accessibility_metadata,
            latest.status AS version_status,
            COALESCE(version_counts.total_versions, 0) AS version_count
        FROM academy_content_items AS ci
        LEFT JOIN LATERAL (
            SELECT cv.*
            FROM academy_content_versions AS cv
            WHERE cv.tenant_id=ci.tenant_id AND cv.content_id=ci.id
            ORDER BY cv.version_number DESC, cv.created_at DESC
            LIMIT 1
        ) AS latest ON TRUE
        LEFT JOIN LATERAL (
            SELECT count(*)::integer AS total_versions
            FROM academy_content_versions AS cv
            WHERE cv.tenant_id=ci.tenant_id AND cv.content_id=ci.id
        ) AS version_counts ON TRUE
        WHERE ci.tenant_id=:tenant_id
        ORDER BY ci.updated_at DESC, ci.slug
    """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def list_admin_paths(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text("""
        SELECT
            lp.id,
            lp.key,
            lp.title_i18n,
            lp.description_i18n,
            lp.certificate_enabled,
            lp.completion_policy,
            lp.status,
            lp.created_by,
            lp.created_at,
            COALESCE(items.item_count, 0) AS item_count,
            COALESCE(assignments.assignment_count, 0) AS role_assignment_count,
            COALESCE(enrollments.enrollment_count, 0) AS enrollment_count,
            COALESCE(enrollments.completed_count, 0) AS completed_count
        FROM academy_learning_paths AS lp
        LEFT JOIN LATERAL (
            SELECT count(*)::integer AS item_count
            FROM academy_learning_path_items AS lpi
            WHERE lpi.tenant_id=lp.tenant_id AND lpi.path_id=lp.id
        ) AS items ON TRUE
        LEFT JOIN LATERAL (
            SELECT count(*)::integer AS assignment_count
            FROM academy_path_role_assignments AS pra
            WHERE pra.tenant_id=lp.tenant_id AND pra.path_id=lp.id
        ) AS assignments ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                count(*)::integer AS enrollment_count,
                count(*) FILTER (WHERE status='completed')::integer AS completed_count
            FROM academy_enrollments AS e
            WHERE e.tenant_id=lp.tenant_id AND e.path_id=lp.id
        ) AS enrollments ON TRUE
        WHERE lp.tenant_id=:tenant_id
        ORDER BY lp.created_at DESC, lp.key
    """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def academy_admin_summary(
    session: AsyncSession,
    principal: Principal,
) -> dict[str, Any]:
    role_rows = (
        (
            await session.execute(
                text("""
        SELECT key, name, is_system
        FROM roles
        WHERE tenant_id=:tenant_id
        ORDER BY is_system DESC, name, key
    """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    version_rows = (
        (
            await session.execute(
                text("""
        SELECT
            cv.id AS content_version_id,
            cv.content_id,
            ci.slug,
            ci.content_type,
            ci.title_i18n,
            cv.version_label,
            cv.version_number,
            cv.locale,
            cv.duration_ms,
            cv.accessibility_metadata
        FROM academy_content_versions AS cv
        JOIN academy_content_items AS ci
          ON ci.tenant_id=cv.tenant_id AND ci.id=cv.content_id
        WHERE cv.tenant_id=:tenant_id
          AND cv.status='published'
          AND ci.status='published'
        ORDER BY ci.updated_at DESC, ci.slug, cv.version_number DESC
    """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    content_version_rows = (
        (
            await session.execute(
                text("""
        SELECT
            cv.id AS content_version_id,
            cv.content_id,
            ci.slug,
            ci.content_type,
            ci.title_i18n,
            ci.status AS content_status,
            cv.version_label,
            cv.version_number,
            cv.locale,
            cv.mime_type,
            cv.duration_ms,
            cv.status AS version_status,
            cv.published_at,
            cv.effective_at,
            cv.retired_at,
            cv.created_at
        FROM academy_content_versions AS cv
        JOIN academy_content_items AS ci
          ON ci.tenant_id=cv.tenant_id AND ci.id=cv.content_id
        WHERE cv.tenant_id=:tenant_id
        ORDER BY ci.slug, cv.locale, cv.version_number DESC, cv.created_at DESC
    """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    quiz_rows = (
        (
            await session.execute(
                text("""
        SELECT
            q.id,
            q.content_version_id,
            q.kind,
            q.checkpoint_at_ms,
            q.pass_score,
            q.max_attempts,
            q.required,
            q.status,
            q.version_number,
            q.supersedes_quiz_id,
            q.created_at,
            ci.slug,
            ci.title_i18n,
            cv.version_label,
            cv.locale,
            COALESCE(question_counts.question_count, 0) AS question_count
        FROM academy_quizzes AS q
        JOIN academy_content_versions AS cv
          ON cv.tenant_id=q.tenant_id AND cv.id=q.content_version_id
        JOIN academy_content_items AS ci
          ON ci.tenant_id=cv.tenant_id AND ci.id=cv.content_id
        LEFT JOIN LATERAL (
            SELECT count(*)::integer AS question_count
            FROM academy_questions AS aq
            WHERE aq.tenant_id=q.tenant_id AND aq.quiz_id=q.id
        ) AS question_counts ON TRUE
        WHERE q.tenant_id=:tenant_id
        ORDER BY q.created_at DESC, q.version_number DESC
    """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    row = (
        (
            await session.execute(
                text("""
        SELECT
            (SELECT count(*) FROM academy_content_items WHERE tenant_id=:tenant_id)::integer AS content_count,
            (SELECT count(*) FROM academy_content_items WHERE tenant_id=:tenant_id AND status='published')::integer AS published_content_count,
            (SELECT count(*) FROM academy_learning_paths WHERE tenant_id=:tenant_id)::integer AS path_count,
            (SELECT count(*) FROM academy_enrollments WHERE tenant_id=:tenant_id)::integer AS enrollment_count,
            (SELECT count(*) FROM academy_enrollments WHERE tenant_id=:tenant_id AND status='completed')::integer AS completed_count,
            (SELECT count(*) FROM academy_quizzes WHERE tenant_id=:tenant_id AND status='published')::integer AS published_quiz_count
    """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .one()
    )

    roles = [{**dict(item), "source": "tenant_registry"} for item in role_rows]
    known_role_keys = {str(item["key"]).strip().lower() for item in role_rows}
    for raw_role in sorted(principal.roles):
        role_key = raw_role.strip().lower()
        if not role_key or role_key in known_role_keys:
            continue
        roles.append(
            {
                "key": role_key,
                "name": role_key,
                "is_system": False,
                "source": "identity_claim",
            }
        )
        known_role_keys.add(role_key)

    return {
        "summary": dict(row),
        "authoring": {
            "roles": roles,
            "published_versions": [dict(item) for item in version_rows],
            "content_versions": [dict(item) for item in content_version_rows],
            "quizzes": [dict(item) for item in quiz_rows],
        },
    }
