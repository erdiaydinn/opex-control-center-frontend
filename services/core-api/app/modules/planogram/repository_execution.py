from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.planogram.execution import (
    PlanogramExecutionError,
    plan_fingerprint,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def _plan_event(
    session: AsyncSession,
    principal: Principal,
    plan_version_id: UUID,
    *,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO planogram_plan_events (
                tenant_id, plan_version_id, event_type, actor_subject,
                from_status, to_status, reason, payload
            ) VALUES (
                :tenant_id, :plan_version_id, :event_type, :actor_subject,
                :from_status, :to_status, :reason, CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "plan_version_id": plan_version_id,
            "event_type": event_type,
            "actor_subject": principal.subject,
            "from_status": from_status,
            "to_status": to_status,
            "reason": reason,
            "payload": _json(payload or {}),
        },
    )


async def list_plan_versions(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, store_dna_version_id, store_code, version_number,
                           source, status, plan_fingerprint, optimizer_fingerprint,
                           physical_truth_attested, created_by, created_at, updated_at,
                           submitted_by, submitted_at, approved_by, approved_at,
                           rejected_by, rejected_at, rejection_reason
                    FROM planogram_plan_versions
                    WHERE tenant_id=:tenant_id
                    ORDER BY store_code, version_number DESC
                    """
                ),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def create_plan_draft(
    session: AsyncSession,
    principal: Principal,
    *,
    store_dna_version_id: UUID,
    store_code: str,
    source: str,
    plan_payload: dict[str, Any],
    optimizer_fingerprint: str | None,
) -> dict[str, Any]:
    normalized_store = store_code.strip().upper()
    fingerprint = plan_fingerprint(plan_payload)
    row = (
        (
            await session.execute(
                text(
                    """
                    WITH store_lock AS MATERIALIZED (
                        SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))
                    ), next_version AS (
                        SELECT COALESCE(MAX(version_number), 0) + 1 AS value
                        FROM planogram_plan_versions, store_lock
                        WHERE tenant_id=:tenant_id AND store_code=:store_code
                    )
                    INSERT INTO planogram_plan_versions (
                        tenant_id, store_dna_version_id, store_code, version_number,
                        source, plan_payload, plan_fingerprint, optimizer_fingerprint,
                        created_by
                    )
                    SELECT :tenant_id, :store_dna_version_id, :store_code,
                           next_version.value, :source, CAST(:plan_payload AS jsonb),
                           :plan_fingerprint, :optimizer_fingerprint, :created_by
                    FROM next_version
                    WHERE NOT EXISTS (
                        SELECT 1 FROM planogram_plan_versions
                        WHERE tenant_id=:tenant_id AND store_code=:store_code
                          AND status IN ('draft','submitted')
                    )
                    RETURNING id, store_dna_version_id, store_code, version_number,
                              source, status, plan_fingerprint, optimizer_fingerprint,
                              physical_truth_attested, created_by, created_at
                    """
                ),
                {
                    "lock_key": f"planogram-plan:{principal.tenant_id}:{normalized_store}",
                    "tenant_id": principal.tenant_id,
                    "store_dna_version_id": store_dna_version_id,
                    "store_code": normalized_store,
                    "source": source,
                    "plan_payload": _json(plan_payload),
                    "plan_fingerprint": fingerprint,
                    "optimizer_fingerprint": optimizer_fingerprint,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PlanogramExecutionError("active_plan_draft_or_submission_exists")
    result = dict(row)
    await _plan_event(
        session,
        principal,
        result["id"],
        event_type="drafted",
        from_status=None,
        to_status="draft",
        payload={"plan_fingerprint": fingerprint, "physical_truth_attested": False},
    )
    return result


async def submit_plan(
    session: AsyncSession,
    principal: Principal,
    plan_version_id: UUID,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    UPDATE planogram_plan_versions
                    SET status='submitted', submitted_by=:actor_subject,
                        submitted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant_id AND id=:plan_version_id AND status='draft'
                    RETURNING id, store_code, version_number, status,
                              physical_truth_attested, submitted_by, submitted_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "plan_version_id": plan_version_id,
                    "actor_subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PlanogramExecutionError("plan_draft_not_found_or_not_submittable")
    result = dict(row)
    await _plan_event(
        session,
        principal,
        plan_version_id,
        event_type="submitted",
        from_status="draft",
        to_status="submitted",
        payload={"physical_truth_attested": bool(result["physical_truth_attested"])},
    )
    return result


async def approve_plan(
    session: AsyncSession,
    principal: Principal,
    plan_version_id: UUID,
) -> dict[str, Any]:
    target = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, store_code, status, submitted_by, physical_truth_attested
                    FROM planogram_plan_versions
                    WHERE tenant_id=:tenant_id AND id=:plan_version_id
                    FOR UPDATE
                    """
                ),
                {"tenant_id": principal.tenant_id, "plan_version_id": plan_version_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if target is None or target["status"] != "submitted":
        raise PlanogramExecutionError("plan_submission_not_found_or_not_approvable")
    if target["submitted_by"] == principal.subject:
        raise PlanogramExecutionError("plan_maker_checker_required")
    if not target["physical_truth_attested"]:
        raise PlanogramExecutionError("external_physical_truth_attestation_required")

    store_code = str(target["store_code"])
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"planogram-plan:{principal.tenant_id}:{store_code}"},
    )
    superseded = (
        (
            await session.execute(
                text(
                    """
                    UPDATE planogram_plan_versions
                    SET status='superseded', updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant_id AND store_code=:store_code
                      AND status='approved' AND id<>:plan_version_id
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "store_code": store_code,
                    "plan_version_id": plan_version_id,
                },
            )
        )
        .mappings()
        .all()
    )
    for previous in superseded:
        await _plan_event(
            session,
            principal,
            previous["id"],
            event_type="superseded",
            from_status="approved",
            to_status="superseded",
            reason="new_plan_version_approved",
        )
    try:
        approved = (
            (
                await session.execute(
                    text(
                        """
                        UPDATE planogram_plan_versions
                        SET status='approved', approved_by=:actor_subject,
                            approved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                        WHERE tenant_id=:tenant_id AND id=:plan_version_id
                          AND status='submitted'
                        RETURNING id, store_code, version_number, status,
                                  plan_fingerprint, optimizer_fingerprint,
                                  physical_truth_attested, approved_by, approved_at
                        """
                    ),
                    {
                        "tenant_id": principal.tenant_id,
                        "plan_version_id": plan_version_id,
                        "actor_subject": principal.subject,
                    },
                )
            )
            .mappings()
            .one()
        )
    except DBAPIError as exc:
        raise PlanogramExecutionError("plan_approval_database_guard_rejected") from exc
    result = dict(approved)
    await _plan_event(
        session,
        principal,
        plan_version_id,
        event_type="approved",
        from_status="submitted",
        to_status="approved",
        payload={"plan_fingerprint": result["plan_fingerprint"]},
    )
    return result


async def reject_plan(
    session: AsyncSession,
    principal: Principal,
    plan_version_id: UUID,
    *,
    reason: str,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    UPDATE planogram_plan_versions
                    SET status='rejected', rejected_by=:actor_subject,
                        rejected_at=CURRENT_TIMESTAMP, rejection_reason=:reason,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant_id AND id=:plan_version_id
                      AND status='submitted'
                    RETURNING id, store_code, version_number, status,
                              rejected_by, rejected_at, rejection_reason
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "plan_version_id": plan_version_id,
                    "actor_subject": principal.subject,
                    "reason": reason,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PlanogramExecutionError("plan_submission_not_found_or_not_rejectable")
    result = dict(row)
    await _plan_event(
        session,
        principal,
        plan_version_id,
        event_type="rejected",
        from_status="submitted",
        to_status="rejected",
        reason=reason,
    )
    return result


async def _execution_event(
    session: AsyncSession,
    principal: Principal,
    assignment_id: UUID,
    *,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO planogram_execution_events (
                tenant_id, assignment_id, event_type, actor_subject, payload
            ) VALUES (
                :tenant_id, :assignment_id, :event_type, :actor_subject,
                CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "assignment_id": assignment_id,
            "event_type": event_type,
            "actor_subject": principal.subject,
            "payload": _json(payload or {}),
        },
    )


async def create_assignment(
    session: AsyncSession,
    principal: Principal,
    *,
    plan_version_id: UUID,
    effective_from: datetime,
    due_at: datetime | None,
) -> dict[str, Any]:
    try:
        row = (
            (
                await session.execute(
                    text(
                        """
                        INSERT INTO planogram_execution_assignments (
                            tenant_id, plan_version_id, store_code, assigned_by,
                            effective_from, due_at
                        )
                        SELECT :tenant_id, p.id, p.store_code, :assigned_by,
                               :effective_from, :due_at
                        FROM planogram_plan_versions p
                        WHERE p.tenant_id=:tenant_id AND p.id=:plan_version_id
                          AND p.status='approved' AND p.physical_truth_attested IS TRUE
                        RETURNING id, plan_version_id, store_code, status,
                                  assigned_by, assigned_at, effective_from, due_at
                        """
                    ),
                    {
                        "tenant_id": principal.tenant_id,
                        "plan_version_id": plan_version_id,
                        "assigned_by": principal.subject,
                        "effective_from": effective_from,
                        "due_at": due_at,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
    except DBAPIError as exc:
        raise PlanogramExecutionError("execution_assignment_database_guard_rejected") from exc
    if row is None:
        raise PlanogramExecutionError("approved_attested_plan_required_for_assignment")
    result = dict(row)
    await _execution_event(
        session,
        principal,
        result["id"],
        event_type="assigned",
        payload={"plan_version_id": str(plan_version_id)},
    )
    return result


async def acknowledge_assignment(
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
                    SET status='acknowledged', acknowledged_by=:actor_subject,
                        acknowledged_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant_id AND id=:assignment_id AND status='assigned'
                    RETURNING id, plan_version_id, store_code, status,
                              acknowledged_by, acknowledged_at
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
        raise PlanogramExecutionError("assignment_not_found_or_not_acknowledgeable")
    result = dict(row)
    await _execution_event(
        session,
        principal,
        assignment_id,
        event_type="acknowledged",
    )
    return result


async def list_assignments(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT a.id, a.plan_version_id, a.store_code, a.status,
                           a.assigned_by, a.assigned_at, a.effective_from, a.due_at,
                           a.acknowledged_by, a.acknowledged_at,
                           COUNT(o.id) AS observation_count,
                           COUNT(o.id) FILTER (WHERE o.result='compliant') AS compliant_count,
                           COUNT(o.id) FILTER (WHERE o.result='deviation') AS deviation_count
                    FROM planogram_execution_assignments a
                    LEFT JOIN planogram_compliance_observations o
                      ON o.tenant_id=a.tenant_id AND o.assignment_id=a.id
                    WHERE a.tenant_id=:tenant_id
                    GROUP BY a.id
                    ORDER BY a.assigned_at DESC
                    """
                ),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def get_assignment_plan(
    session: AsyncSession,
    principal: Principal,
    assignment_id: UUID,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT a.id AS assignment_id, a.plan_version_id, a.store_code,
                           a.status AS assignment_status, p.status AS plan_status,
                           p.physical_truth_attested, p.plan_payload, p.plan_fingerprint
                    FROM planogram_execution_assignments a
                    JOIN planogram_plan_versions p
                      ON p.tenant_id=a.tenant_id AND p.id=a.plan_version_id
                    WHERE a.tenant_id=:tenant_id AND a.id=:assignment_id
                    """
                ),
                {"tenant_id": principal.tenant_id, "assignment_id": assignment_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PlanogramExecutionError("execution_assignment_not_found")
    return dict(row)


async def insert_compliance_observation(
    session: AsyncSession,
    principal: Principal,
    *,
    assignment_id: UUID,
    plan_version_id: UUID,
    field_promotion_id: UUID,
    candidate_fingerprint: str,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO planogram_compliance_observations (
                        tenant_id, assignment_id, plan_version_id, field_promotion_id,
                        candidate_fingerprint, sku, expected_locations, actual_location,
                        result, deviation_codes, accepted_by
                    ) VALUES (
                        :tenant_id, :assignment_id, :plan_version_id, :field_promotion_id,
                        :candidate_fingerprint, :sku, CAST(:expected_locations AS jsonb),
                        CAST(:actual_location AS jsonb), :result, :deviation_codes,
                        :accepted_by
                    )
                    ON CONFLICT (tenant_id, field_promotion_id) DO NOTHING
                    RETURNING id, assignment_id, plan_version_id, field_promotion_id,
                              sku, result, deviation_codes, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "assignment_id": assignment_id,
                    "plan_version_id": plan_version_id,
                    "field_promotion_id": field_promotion_id,
                    "candidate_fingerprint": candidate_fingerprint,
                    "sku": evaluation["sku"],
                    "expected_locations": _json(evaluation["expected_locations"]),
                    "actual_location": _json(evaluation["actual_location"]),
                    "result": evaluation["result"],
                    "deviation_codes": evaluation["deviation_codes"],
                    "accepted_by": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        existing = (
            (
                await session.execute(
                    text(
                        """
                        SELECT id, assignment_id, plan_version_id, field_promotion_id,
                               sku, result, deviation_codes, created_at
                        FROM planogram_compliance_observations
                        WHERE tenant_id=:tenant_id AND field_promotion_id=:field_promotion_id
                        """
                    ),
                    {
                        "tenant_id": principal.tenant_id,
                        "field_promotion_id": field_promotion_id,
                    },
                )
            )
            .mappings()
            .one()
        )
        return {**dict(existing), "idempotent_replay": True}
    return {**dict(row), "idempotent_replay": False}
