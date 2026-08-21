from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.planogram.execution import PlanogramExecutionError, plan_fingerprint
from app.modules.planogram.repository_execution import _json, _plan_event


async def update_plan_draft(
    session: AsyncSession,
    principal: Principal,
    plan_version_id: UUID,
    *,
    plan_payload: dict[str, Any],
    optimizer_fingerprint: str | None,
) -> dict[str, Any]:
    fingerprint = plan_fingerprint(plan_payload)
    row = (
        (
            await session.execute(
                text(
                    """
                    UPDATE planogram_plan_versions
                    SET plan_payload=CAST(:plan_payload AS jsonb),
                        plan_fingerprint=:plan_fingerprint,
                        optimizer_fingerprint=:optimizer_fingerprint,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant_id AND id=:plan_version_id
                      AND status='draft'
                    RETURNING id, store_dna_version_id, store_code, version_number,
                              source, status, plan_fingerprint, optimizer_fingerprint,
                              physical_truth_attested, updated_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "plan_version_id": plan_version_id,
                    "plan_payload": _json(plan_payload),
                    "plan_fingerprint": fingerprint,
                    "optimizer_fingerprint": optimizer_fingerprint,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PlanogramExecutionError("plan_draft_not_found_or_not_editable")
    result = dict(row)
    await _plan_event(
        session,
        principal,
        plan_version_id,
        event_type="updated",
        from_status="draft",
        to_status="draft",
        payload={"plan_fingerprint": fingerprint},
    )
    return result
