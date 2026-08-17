from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.planogram.execution import PlanogramExecutionError
from app.modules.planogram.repository_execution import _execution_event


async def close_assignment(
    session: AsyncSession,
    principal: Principal,
    assignment_id: UUID,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    UPDATE planogram_execution_assignments
                    SET status='closed', closed_by=:actor_subject,
                        closed_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant_id AND id=:assignment_id
                      AND status IN ('assigned','acknowledged')
                    RETURNING id, plan_version_id, store_code, status,
                              closed_by, closed_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "assignment_id": assignment_id,
                    "actor_subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PlanogramExecutionError("assignment_not_found_or_not_closable")
    result = dict(row)
    await _execution_event(
        session,
        principal,
        assignment_id,
        event_type="closed",
    )
    return result
