from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.resources import engine

from .repository import AuditConflictError, AuditRepositoryError
from .schemas import (
    AuditDecisionEventCreate,
    AuditManagerAssuranceDecision,
    AuditStandardsAssuranceDecision,
)

_BINARY_DECISIONS = frozenset({"PASS", "FAIL"})


async def _set_tenant(connection: AsyncConnection, tenant_id: str) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def _dict(row) -> dict[str, object]:
    return dict(row._mapping)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def _notify(
    connection: AsyncConnection,
    *,
    tenant_id: str,
    recipient_subject: str,
    event_key: str,
    payload: dict[str, object],
    idempotency_root: str,
) -> None:
    for channel in ("IN_APP", "EMAIL"):
        await connection.execute(
            text(
                """
                INSERT INTO platform_notification_outbox (
                    tenant_id, module, event_key, recipient_subject,
                    channel, payload, idempotency_key
                ) VALUES (
                    CAST(:tenant_id AS UUID), 'audit', :event_key, :recipient_subject,
                    :channel, CAST(:payload AS JSONB), :idempotency_key
                )
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                """
            ),
            {
                "tenant_id": tenant_id,
                "event_key": event_key,
                "recipient_subject": recipient_subject,
                "channel": channel,
                "payload": _json(payload),
                "idempotency_key": f"{idempotency_root}:{channel.lower()}",
            },
        )


async def append_auditor_decision_and_route(
    tenant_id: str,
    actor_subject: str,
    audit_run_id: UUID,
    payload: AuditDecisionEventCreate,
) -> dict[str, object]:
    """Persist the auditor decision and atomically open/refresh assurance if needed."""

    if payload.decision_source != "AUDITOR":
        raise AuditRepositoryError("auditor assurance path only accepts AUDITOR decisions")

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        run_result = await connection.execute(
            text(
                """
                SELECT ar.id, ar.location_id, ar.auditor_subject, ar.manager_subject,
                       ar.status, fl.region
                FROM audit_runs ar
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                  AND ar.id = CAST(:audit_run_id AS UUID)
                FOR UPDATE OF ar
                """
            ),
            {"tenant_id": tenant_id, "audit_run_id": str(audit_run_id)},
        )
        run = run_result.first()
        if not run or run.status == "cancelled":
            raise AuditRepositoryError("audit run not found or cancelled")
        if run.auditor_subject != actor_subject:
            raise AuditRepositoryError("auditor decision actor does not own this audit run")

        decision_result = await connection.execute(
            text(
                """
                INSERT INTO audit_item_decision_events (
                    tenant_id, audit_run_id, item_key, decision_source,
                    decision, confidence, model_or_rule_ref, reason,
                    evidence_refs, actor_subject
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:audit_run_id AS UUID), :item_key,
                    'AUDITOR', :decision, :confidence, :model_or_rule_ref, :reason,
                    CAST(:evidence_refs AS JSONB), :actor_subject
                )
                RETURNING id, audit_run_id, item_key, decision_source,
                          decision, confidence, model_or_rule_ref, reason,
                          evidence_refs, actor_subject, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "item_key": payload.item_key,
                "decision": payload.decision,
                "confidence": payload.confidence,
                "model_or_rule_ref": payload.model_or_rule_ref,
                "reason": payload.reason,
                "evidence_refs": _json(payload.evidence_refs),
                "actor_subject": actor_subject,
            },
        )
        decision = _dict(decision_result.one())

        ai_result = await connection.execute(
            text(
                """
                SELECT id, decision, confidence, model_or_rule_ref, actor_subject, created_at
                FROM audit_item_decision_events
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND audit_run_id = CAST(:audit_run_id AS UUID)
                  AND item_key = :item_key
                  AND decision_source = 'AI'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "item_key": payload.item_key,
            },
        )
        ai = ai_result.first()
        comparable = (
            ai is not None
            and ai.decision in _BINARY_DECISIONS
            and payload.decision in _BINARY_DECISIONS
        )
        if not comparable or ai.decision == payload.decision:
            return {"decision": decision, "assurance_case": None}

        initial_state = "MANAGER_REVIEW" if run.manager_subject else "MANAGER_UNASSIGNED"
        case_result = await connection.execute(
            text(
                """
                INSERT INTO audit_assurance_cases (
                    tenant_id, audit_run_id, item_key, ai_decision_event_id,
                    auditor_decision_event_id, auditor_subject, manager_subject, state
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:audit_run_id AS UUID), :item_key,
                    CAST(:ai_decision_event_id AS UUID), CAST(:auditor_decision_event_id AS UUID),
                    :auditor_subject, :manager_subject, :state
                )
                ON CONFLICT (tenant_id, audit_run_id, item_key) DO UPDATE SET
                    ai_decision_event_id = EXCLUDED.ai_decision_event_id,
                    auditor_decision_event_id = EXCLUDED.auditor_decision_event_id,
                    auditor_subject = EXCLUDED.auditor_subject,
                    manager_subject = EXCLUDED.manager_subject,
                    state = EXCLUDED.state,
                    manager_disposition = NULL,
                    standards_disposition = NULL,
                    resolved_at = NULL,
                    version = audit_assurance_cases.version + 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, audit_run_id, item_key, ai_decision_event_id,
                          auditor_decision_event_id, auditor_subject, manager_subject,
                          state, manager_disposition, standards_disposition,
                          version, opened_at, updated_at, resolved_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "item_key": payload.item_key,
                "ai_decision_event_id": str(ai.id),
                "auditor_decision_event_id": str(decision["id"]),
                "auditor_subject": actor_subject,
                "manager_subject": run.manager_subject,
                "state": initial_state,
            },
        )
        case = _dict(case_result.one())

        if run.manager_subject:
            await _notify(
                connection,
                tenant_id=tenant_id,
                recipient_subject=run.manager_subject,
                event_key="audit.assurance.manager_review_required",
                idempotency_root=(
                    f"audit-assurance:{case['id']}:{case['version']}:manager"
                ),
                payload={
                    "assurance_case_id": str(case["id"]),
                    "audit_run_id": str(audit_run_id),
                    "item_key": payload.item_key,
                    "location_id": run.location_id,
                    "region": run.region,
                    "auditor_subject": actor_subject,
                    "ai_decision": ai.decision,
                    "auditor_decision": payload.decision,
                },
            )

        return {"decision": decision, "assurance_case": case}


async def get_assurance_case(
    tenant_id: str,
    case_id: UUID,
) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT c.*, ar.location_id, fl.region
                FROM audit_assurance_cases c
                JOIN audit_runs ar
                  ON ar.tenant_id = c.tenant_id AND ar.id = c.audit_run_id
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                WHERE c.tenant_id = CAST(:tenant_id AS UUID)
                  AND c.id = CAST(:case_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "case_id": str(case_id)},
        )
        row = result.first()
        return _dict(row) if row else None


async def list_assurance_cases(
    tenant_id: str,
    *,
    location_ids: frozenset[str] | None,
    regions: frozenset[str] | None,
    unrestricted: bool,
    limit: int,
) -> list[dict[str, object]]:
    if not unrestricted and not location_ids and not regions:
        return []
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT c.*, ar.location_id, fl.name AS location_name, fl.region,
                       ai.decision AS ai_decision, aud.decision AS auditor_decision
                FROM audit_assurance_cases c
                JOIN audit_runs ar
                  ON ar.tenant_id = c.tenant_id AND ar.id = c.audit_run_id
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                JOIN audit_item_decision_events ai
                  ON ai.tenant_id = c.tenant_id AND ai.id = c.ai_decision_event_id
                JOIN audit_item_decision_events aud
                  ON aud.tenant_id = c.tenant_id AND aud.id = c.auditor_decision_event_id
                WHERE c.tenant_id = CAST(:tenant_id AS UUID)
                  AND (
                    :unrestricted
                    OR ar.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
                    OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
                  )
                ORDER BY c.updated_at DESC
                LIMIT :limit
                """
            ),
            {
                "tenant_id": tenant_id,
                "unrestricted": unrestricted,
                "location_ids": sorted(location_ids or ()),
                "regions": sorted(regions or ()),
                "limit": max(1, min(limit, 500)),
            },
        )
        return [_dict(row) for row in result]


async def manager_decide_assurance_case(
    tenant_id: str,
    actor_subject: str,
    case_id: UUID,
    payload: AuditManagerAssuranceDecision,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        current_result = await connection.execute(
            text(
                """
                SELECT c.*, ar.location_id, fl.region
                FROM audit_assurance_cases c
                JOIN audit_runs ar
                  ON ar.tenant_id = c.tenant_id AND ar.id = c.audit_run_id
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                WHERE c.tenant_id = CAST(:tenant_id AS UUID)
                  AND c.id = CAST(:case_id AS UUID)
                FOR UPDATE OF c
                """
            ),
            {"tenant_id": tenant_id, "case_id": str(case_id)},
        )
        current = current_result.first()
        if not current:
            raise AuditRepositoryError("assurance case not found")
        if current.version != payload.expected_version:
            raise AuditConflictError("assurance case version conflict")
        if current.state != "MANAGER_REVIEW":
            raise AuditConflictError("assurance case is not awaiting manager review")
        if current.manager_subject != actor_subject:
            raise AuditRepositoryError("assurance case belongs to a different manager")

        await connection.execute(
            text(
                """
                INSERT INTO audit_assurance_reviews (
                    tenant_id, audit_run_id, item_key, state,
                    reviewer_subject, disposition, reason
                ) VALUES (
                    CAST(:tenant_id AS UUID), :audit_run_id, :item_key,
                    'MANAGER_REVIEW', :reviewer_subject, :disposition, :reason
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": current.audit_run_id,
                "item_key": current.item_key,
                "reviewer_subject": actor_subject,
                "disposition": payload.disposition,
                "reason": payload.reason,
            },
        )

        standards_subjects: list[str] = []
        if payload.disposition == "AUDITOR_CONFIRMED":
            members = await connection.execute(
                text(
                    """
                    SELECT DISTINCT m.external_subject
                    FROM memberships m
                    JOIN membership_roles mr
                      ON mr.tenant_id = m.tenant_id AND mr.membership_id = m.id
                    JOIN roles r
                      ON r.tenant_id = mr.tenant_id AND r.id = mr.role_id
                    WHERE m.tenant_id = CAST(:tenant_id AS UUID)
                      AND m.status = 'active'
                      AND r.key = 'audit_standards'
                      AND r.is_system IS TRUE
                    ORDER BY m.external_subject
                    """
                ),
                {"tenant_id": tenant_id},
            )
            standards_subjects = [row.external_subject for row in members]

        next_state = "RESOLVED"
        if payload.disposition == "AUDITOR_CONFIRMED":
            next_state = (
                "OPERATIONS_STANDARDS_REVIEW"
                if standards_subjects
                else "OPERATIONS_STANDARDS_UNASSIGNED"
            )

        updated_result = await connection.execute(
            text(
                """
                UPDATE audit_assurance_cases
                SET state = :state,
                    manager_disposition = :manager_disposition,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP,
                    resolved_at = CASE
                      WHEN :manager_disposition = 'AUDITOR_CONFIRMED' THEN NULL
                      ELSE CURRENT_TIMESTAMP
                    END
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:case_id AS UUID)
                  AND version = :expected_version
                RETURNING *
                """
            ),
            {
                "tenant_id": tenant_id,
                "case_id": str(case_id),
                "expected_version": payload.expected_version,
                "state": next_state,
                "manager_disposition": payload.disposition,
            },
        )
        updated = updated_result.first()
        if not updated:
            raise AuditConflictError("assurance case changed concurrently")
        result = _dict(updated)

        for subject in standards_subjects:
            await _notify(
                connection,
                tenant_id=tenant_id,
                recipient_subject=subject,
                event_key="audit.assurance.operations_standards_review_required",
                idempotency_root=(
                    f"audit-assurance:{case_id}:{result['version']}:standards:{subject}"
                ),
                payload={
                    "assurance_case_id": str(case_id),
                    "audit_run_id": str(current.audit_run_id),
                    "item_key": current.item_key,
                    "location_id": current.location_id,
                    "region": current.region,
                    "auditor_subject": current.auditor_subject,
                    "manager_subject": actor_subject,
                    "manager_disposition": payload.disposition,
                },
            )
        return result


async def standards_decide_assurance_case(
    tenant_id: str,
    actor_subject: str,
    case_id: UUID,
    payload: AuditStandardsAssuranceDecision,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        current_result = await connection.execute(
            text(
                """
                SELECT *
                FROM audit_assurance_cases
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:case_id AS UUID)
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "case_id": str(case_id)},
        )
        current = current_result.first()
        if not current:
            raise AuditRepositoryError("assurance case not found")
        if current.version != payload.expected_version:
            raise AuditConflictError("assurance case version conflict")
        if current.state not in {
            "OPERATIONS_STANDARDS_REVIEW",
            "OPERATIONS_STANDARDS_UNASSIGNED",
        }:
            raise AuditConflictError("assurance case is not awaiting Operations Standards")

        await connection.execute(
            text(
                """
                INSERT INTO audit_assurance_reviews (
                    tenant_id, audit_run_id, item_key, state,
                    reviewer_subject, disposition, reason
                ) VALUES (
                    CAST(:tenant_id AS UUID), :audit_run_id, :item_key,
                    'OPERATIONS_STANDARDS_REVIEW', :reviewer_subject, :disposition, :reason
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": current.audit_run_id,
                "item_key": current.item_key,
                "reviewer_subject": actor_subject,
                "disposition": payload.disposition,
                "reason": payload.reason,
            },
        )
        updated_result = await connection.execute(
            text(
                """
                UPDATE audit_assurance_cases
                SET state = 'RESOLVED',
                    standards_disposition = :standards_disposition,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP,
                    resolved_at = CURRENT_TIMESTAMP
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:case_id AS UUID)
                  AND version = :expected_version
                RETURNING *
                """
            ),
            {
                "tenant_id": tenant_id,
                "case_id": str(case_id),
                "expected_version": payload.expected_version,
                "standards_disposition": payload.disposition,
            },
        )
        updated = updated_result.first()
        if not updated:
            raise AuditConflictError("assurance case changed concurrently")
        return _dict(updated)


async def auditor_assurance_summary(
    tenant_id: str,
    *,
    location_ids: frozenset[str] | None,
    regions: frozenset[str] | None,
    unrestricted: bool,
) -> list[dict[str, object]]:
    if not unrestricted and not location_ids and not regions:
        return []
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                WITH latest_ai AS (
                    SELECT DISTINCT ON (audit_run_id, item_key)
                           audit_run_id, item_key, decision
                    FROM audit_item_decision_events
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                      AND decision_source = 'AI'
                      AND decision IN ('PASS','FAIL')
                    ORDER BY audit_run_id, item_key, created_at DESC, id DESC
                ), latest_auditor AS (
                    SELECT DISTINCT ON (audit_run_id, item_key)
                           audit_run_id, item_key, decision, actor_subject
                    FROM audit_item_decision_events
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                      AND decision_source = 'AUDITOR'
                      AND decision IN ('PASS','FAIL')
                    ORDER BY audit_run_id, item_key, created_at DESC, id DESC
                )
                SELECT aud.actor_subject AS auditor_subject,
                       COUNT(*)::integer AS comparable_items,
                       COUNT(*) FILTER (WHERE ai.decision <> aud.decision)::integer
                         AS disagreements,
                       ROUND(
                         100.0 * COUNT(*) FILTER (WHERE ai.decision = aud.decision)
                         / NULLIF(COUNT(*), 0), 2
                       ) AS agreement_percent,
                       COUNT(*) FILTER (
                         WHERE c.manager_disposition = 'AI_CONFIRMED'
                       )::integer AS manager_ai_confirmed,
                       COUNT(*) FILTER (
                         WHERE c.manager_disposition = 'AUDITOR_CONFIRMED'
                       )::integer AS manager_auditor_confirmed,
                       COUNT(*) FILTER (
                         WHERE c.standards_disposition IS NOT NULL
                       )::integer AS standards_reviewed
                FROM latest_auditor aud
                JOIN latest_ai ai
                  ON ai.audit_run_id = aud.audit_run_id AND ai.item_key = aud.item_key
                JOIN audit_runs ar
                  ON ar.tenant_id = CAST(:tenant_id AS UUID) AND ar.id = aud.audit_run_id
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                LEFT JOIN audit_assurance_cases c
                  ON c.tenant_id = ar.tenant_id
                 AND c.audit_run_id = aud.audit_run_id
                 AND c.item_key = aud.item_key
                WHERE (
                    :unrestricted
                    OR ar.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
                    OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
                )
                GROUP BY aud.actor_subject
                ORDER BY disagreements DESC, comparable_items DESC, aud.actor_subject
                """
            ),
            {
                "tenant_id": tenant_id,
                "unrestricted": unrestricted,
                "location_ids": sorted(location_ids or ()),
                "regions": sorted(regions or ()),
            },
        )
        return [_dict(row) for row in result]
