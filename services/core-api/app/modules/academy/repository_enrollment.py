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
    row = (await session.execute(text("""
        INSERT INTO academy_enrollments (
            tenant_id, path_id, subject, source, status, assigned_by, due_at
        ) SELECT :tenant_id, lp.id, :subject, 'manual', 'assigned', :assigned_by, :due_at
          FROM academy_learning_paths AS lp
          WHERE lp.tenant_id=:tenant_id AND lp.id=:path_id AND lp.status='published'
        ON CONFLICT (tenant_id, subject, path_id)
        DO UPDATE SET due_at=COALESCE(EXCLUDED.due_at, academy_enrollments.due_at)
        RETURNING id, path_id, subject, source, status, assigned_at, due_at
    """), {
        "tenant_id": principal.tenant_id, "path_id": path_id,
        "subject": subject.strip(), "assigned_by": principal.subject, "due_at": due_at,
    })).mappings().one_or_none()
    return dict(row) if row else None


async def reconcile_role_enrollments(session: AsyncSession, principal: Principal) -> list[dict[str, Any]]:
    rows = (await session.execute(text("""
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
    """), {
        "tenant_id": principal.tenant_id, "subject": principal.subject,
        "roles": roles_json(principal),
    })).mappings().all()
    return [dict(row) for row in rows]


async def list_enrollments(session: AsyncSession, principal: Principal) -> list[dict[str, Any]]:
    rows = (await session.execute(text("""
        SELECT e.id, e.path_id, lp.key, lp.title_i18n, e.source, e.status,
               e.assigned_at, e.due_at, e.started_at, e.completed_at,
               e.completion_revoked_at
        FROM academy_enrollments AS e
        JOIN academy_learning_paths AS lp
          ON lp.tenant_id=e.tenant_id AND lp.id=e.path_id
        WHERE e.tenant_id=:tenant_id AND e.subject=:subject
        ORDER BY COALESCE(e.due_at, 'infinity'::timestamptz), e.assigned_at DESC
    """), {
        "tenant_id": principal.tenant_id,
        "subject": principal.subject,
    })).mappings().all()
    return [dict(row) for row in rows]
