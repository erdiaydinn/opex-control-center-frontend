from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def get_completion_snapshot(
    session: AsyncSession,
    principal: Principal,
    enrollment_id: UUID,
) -> dict[str, Any] | None:
    enrollment = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    e.id,
                    e.path_id,
                    e.status,
                    lp.certificate_enabled,
                    lp.completion_policy
                FROM academy_enrollments AS e
                JOIN academy_learning_paths AS lp
                  ON lp.tenant_id = e.tenant_id
                 AND lp.id = e.path_id
                WHERE e.tenant_id = :tenant_id
                  AND e.id = :enrollment_id
                  AND e.subject = :subject
                  AND e.status IN ('assigned', 'in_progress', 'completed')
                FOR UPDATE OF e
                """
                ),
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

    required_result = await session.execute(
        text("""
        SELECT lpi.content_version_id
        FROM academy_learning_path_items AS lpi
        WHERE lpi.tenant_id=:tenant_id AND lpi.path_id=:path_id AND lpi.required=TRUE
        ORDER BY lpi.ordinal
    """),
        {"tenant_id": principal.tenant_id, "path_id": enrollment["path_id"]},
    )
    required_versions = [row[0] for row in required_result.all()]

    incomplete_result = await session.execute(
        text("""
        SELECT lpi.content_version_id
        FROM academy_learning_path_items AS lpi
        LEFT JOIN academy_progress AS p
          ON p.tenant_id=lpi.tenant_id AND p.enrollment_id=:enrollment_id
         AND p.content_version_id=lpi.content_version_id AND p.subject=:subject
        WHERE lpi.tenant_id=:tenant_id AND lpi.path_id=:path_id AND lpi.required=TRUE
          AND COALESCE(p.status,'not_started') <> 'completed'
        ORDER BY lpi.ordinal
    """),
        {
            "tenant_id": principal.tenant_id,
            "path_id": enrollment["path_id"],
            "enrollment_id": enrollment_id,
            "subject": principal.subject,
        },
    )
    incomplete_versions = [row[0] for row in incomplete_result.all()]

    missing_result = await session.execute(
        text("""
        SELECT q.id
        FROM academy_quizzes AS q
        JOIN academy_learning_path_items AS lpi
          ON lpi.tenant_id=q.tenant_id AND lpi.content_version_id=q.content_version_id AND lpi.path_id=:path_id
        WHERE q.tenant_id=:tenant_id AND q.status='published' AND q.required=TRUE
          AND NOT EXISTS (
              SELECT 1 FROM academy_quiz_attempts AS qa
              WHERE qa.tenant_id=q.tenant_id AND qa.quiz_id=q.id
                AND qa.enrollment_id=:enrollment_id AND qa.subject=:subject AND qa.passed=TRUE
          )
        ORDER BY q.id
    """),
        {
            "tenant_id": principal.tenant_id,
            "path_id": enrollment["path_id"],
            "enrollment_id": enrollment_id,
            "subject": principal.subject,
        },
    )
    missing_quizzes = [row[0] for row in missing_result.all()]

    certificate = (
        (
            await session.execute(
                text("""
        SELECT certificate_code, contract_version, completion_fingerprint, issued_at, revoked_at
        FROM academy_certificates
        WHERE tenant_id=:tenant_id AND enrollment_id=:enrollment_id
    """),
                {"tenant_id": principal.tenant_id, "enrollment_id": enrollment_id},
            )
        )
        .mappings()
        .one_or_none()
    )

    return {
        **dict(enrollment),
        "required_content_version_ids": required_versions,
        "incomplete_content_version_ids": incomplete_versions,
        "missing_required_quiz_ids": missing_quizzes,
        "certificate": dict(certificate) if certificate else None,
    }


async def mark_enrollment_completed(
    session: AsyncSession,
    principal: Principal,
    *,
    enrollment_id: UUID,
    path_id: UUID,
    certificate_enabled: bool,
    certificate_code: str,
    completion_fingerprint: str,
) -> dict[str, Any]:
    await session.execute(
        text("""
        UPDATE academy_enrollments
        SET status='completed', completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP)
        WHERE tenant_id=:tenant_id AND id=:enrollment_id AND subject=:subject
    """),
        {
            "tenant_id": principal.tenant_id,
            "enrollment_id": enrollment_id,
            "subject": principal.subject,
        },
    )
    if not certificate_enabled:
        return {"certificate_code": None, "contract_version": None, "completion_fingerprint": None}
    await session.execute(
        text("""
        INSERT INTO academy_certificates (
            tenant_id,enrollment_id,path_id,subject,certificate_code,contract_version,completion_fingerprint
        ) VALUES (
            :tenant_id,:enrollment_id,:path_id,:subject,:certificate_code,'academy-completion-v1',:completion_fingerprint
        ) ON CONFLICT (tenant_id,enrollment_id) DO NOTHING
    """),
        {
            "tenant_id": principal.tenant_id,
            "enrollment_id": enrollment_id,
            "path_id": path_id,
            "subject": principal.subject,
            "certificate_code": certificate_code,
            "completion_fingerprint": completion_fingerprint,
        },
    )
    certificate = (
        (
            await session.execute(
                text("""
        SELECT certificate_code, contract_version, completion_fingerprint
        FROM academy_certificates
        WHERE tenant_id=:tenant_id AND enrollment_id=:enrollment_id
    """),
                {"tenant_id": principal.tenant_id, "enrollment_id": enrollment_id},
            )
        )
        .mappings()
        .one()
    )
    return dict(certificate)
