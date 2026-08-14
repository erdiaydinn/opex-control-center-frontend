from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def get_required_quiz_ids(
    session: AsyncSession,
    principal: Principal,
    path_id: UUID,
) -> list[UUID]:
    result = await session.execute(
        text("""
        SELECT q.id
        FROM academy_quizzes AS q
        JOIN academy_learning_path_items AS lpi
          ON lpi.tenant_id=q.tenant_id AND lpi.content_version_id=q.content_version_id
         AND lpi.path_id=:path_id
        WHERE q.tenant_id=:tenant_id AND q.status='published' AND q.required=TRUE
        ORDER BY q.id
    """),
        {
            "tenant_id": principal.tenant_id,
            "path_id": path_id,
        },
    )
    return [row[0] for row in result.all()]


async def is_completion_revoked(
    session: AsyncSession,
    principal: Principal,
    enrollment_id: UUID,
) -> bool:
    value = await session.scalar(
        text("""
        SELECT EXISTS (
            SELECT 1 FROM academy_enrollments
            WHERE tenant_id=:tenant_id AND id=:enrollment_id
              AND subject=:subject AND status='revoked'
        )
    """),
        {
            "tenant_id": principal.tenant_id,
            "enrollment_id": enrollment_id,
            "subject": principal.subject,
        },
    )
    return bool(value)


async def revoke_completion(
    session: AsyncSession,
    principal: Principal,
    *,
    enrollment_id: UUID,
    reason: str,
) -> dict[str, Any] | None:
    enrollment = (
        (
            await session.execute(
                text("""
        UPDATE academy_enrollments
        SET status='revoked', completion_revoked_at=CURRENT_TIMESTAMP,
            completion_revoked_by=:actor, completion_revocation_reason=:reason
        WHERE tenant_id=:tenant_id AND id=:enrollment_id AND status='completed'
        RETURNING id, path_id, subject, status, completion_revoked_at
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "enrollment_id": enrollment_id,
                    "actor": principal.subject,
                    "reason": reason,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if enrollment is None:
        return None
    await session.execute(
        text("""
        UPDATE academy_certificates
        SET revoked_at=CURRENT_TIMESTAMP, revoked_by=:actor, revocation_reason=:reason
        WHERE tenant_id=:tenant_id AND enrollment_id=:enrollment_id AND revoked_at IS NULL
    """),
        {
            "tenant_id": principal.tenant_id,
            "enrollment_id": enrollment_id,
            "actor": principal.subject,
            "reason": reason,
        },
    )
    return dict(enrollment)
