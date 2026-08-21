from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.resources import engine

from .schemas import (
    AuditActionCreate,
    AuditActionUpdate,
    AuditAssuranceReviewCreate,
    AuditDecisionEventCreate,
    AuditProgramActivate,
    AuditProgramCreate,
    AuditRedactionReceiptCreate,
    AuditRunStart,
)


class AuditRepositoryError(ValueError):
    pass


class AuditConflictError(AuditRepositoryError):
    pass


async def _set_tenant(connection, tenant_id: str) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def _row_dict(row) -> dict[str, object]:
    return dict(row._mapping)


def _serialize(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def get_location(tenant_id: str, location_id: str) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT location_id, name, region, city, active
                FROM field_locations
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND location_id = :location_id
                """
            ),
            {"tenant_id": tenant_id, "location_id": location_id},
        )
        row = result.first()
        return _row_dict(row) if row else None


async def create_program(
    tenant_id: str,
    actor_subject: str,
    payload: AuditProgramCreate,
) -> dict[str, object]:
    statement = text(
        """
        INSERT INTO audit_program_versions (
            tenant_id, program_key, version, name_i18n,
            field_template_id, field_template_version,
            scoring_policy, settings, created_by
        )
        SELECT
            CAST(:tenant_id AS UUID), :program_key, :version, CAST(:name_i18n AS JSONB),
            :field_template_id, :field_template_version,
            CAST(:scoring_policy AS JSONB), CAST(:settings AS JSONB), :created_by
        FROM field_templates ft
        WHERE ft.tenant_id = CAST(:tenant_id AS UUID)
          AND ft.template_id = :field_template_id
          AND ft.version = :field_template_version
        RETURNING program_key, version, status, effective_from,
                  field_template_id, field_template_version, created_at
        """
    )
    values = {
        "tenant_id": tenant_id,
        "program_key": payload.program_key,
        "version": payload.version,
        "name_i18n": _serialize(payload.name_i18n),
        "field_template_id": payload.field_template_id,
        "field_template_version": payload.field_template_version,
        "scoring_policy": _serialize(payload.scoring_policy),
        "settings": _serialize(payload.settings),
        "created_by": actor_subject,
    }
    try:
        async with engine.begin() as connection:
            await _set_tenant(connection, tenant_id)
            result = await connection.execute(statement, values)
            row = result.first()
            if not row:
                raise AuditRepositoryError("referenced governed Field template does not exist")
            return _row_dict(row)
    except IntegrityError as exc:
        raise AuditConflictError("audit program version already exists or is invalid") from exc


async def activate_program(
    tenant_id: str,
    program_key: str,
    version: int,
    payload: AuditProgramActivate,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        existing = await connection.execute(
            text(
                """
                SELECT status
                FROM audit_program_versions
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND program_key = :program_key
                  AND version = :version
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "program_key": program_key, "version": version},
        )
        if not existing.first():
            raise AuditRepositoryError("audit program version not found")

        await connection.execute(
            text(
                """
                UPDATE audit_program_versions
                SET status = 'retired'
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND program_key = :program_key
                  AND status = 'active'
                  AND version <> :version
                """
            ),
            {"tenant_id": tenant_id, "program_key": program_key, "version": version},
        )
        result = await connection.execute(
            text(
                """
                UPDATE audit_program_versions
                SET status = 'active', effective_from = :effective_from
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND program_key = :program_key
                  AND version = :version
                RETURNING program_key, version, status, effective_from,
                          field_template_id, field_template_version
                """
            ),
            {
                "tenant_id": tenant_id,
                "program_key": program_key,
                "version": version,
                "effective_from": payload.effective_from,
            },
        )
        return _row_dict(result.one())


async def list_programs(tenant_id: str) -> list[dict[str, object]]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT program_key, version, name_i18n, status, effective_from,
                       field_template_id, field_template_version, scoring_policy, settings,
                       created_by, created_at
                FROM audit_program_versions
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                ORDER BY program_key, version DESC
                """
            ),
            {"tenant_id": tenant_id},
        )
        return [_row_dict(row) for row in result]


async def start_run(
    tenant_id: str,
    actor_subject: str,
    payload: AuditRunStart,
) -> dict[str, object]:
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        program = await connection.execute(
            text(
                """
                SELECT 1
                FROM audit_program_versions
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND program_key = :program_key
                  AND version = :program_version
                  AND status = 'active'
                  AND effective_from <= :now
                """
            ),
            {
                "tenant_id": tenant_id,
                "program_key": payload.program_key,
                "program_version": payload.program_version,
                "now": now,
            },
        )
        if not program.first():
            raise AuditRepositoryError("audit program is not active/effective")

        location = await connection.execute(
            text(
                """
                SELECT 1 FROM field_locations
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND location_id = :location_id
                  AND active IS TRUE
                """
            ),
            {"tenant_id": tenant_id, "location_id": payload.location_id},
        )
        if not location.first():
            raise AuditRepositoryError("audit location is not active")

        result = await connection.execute(
            text(
                """
                INSERT INTO audit_runs (
                    tenant_id, program_key, program_version, field_mission_id,
                    location_id, auditor_subject, manager_subject,
                    source_mode, started_at
                ) VALUES (
                    CAST(:tenant_id AS UUID), :program_key, :program_version,
                    CAST(:field_mission_id AS UUID), :location_id, :auditor_subject,
                    :manager_subject, :source_mode, :started_at
                )
                RETURNING id, program_key, program_version, location_id,
                          auditor_subject, manager_subject, status, source_mode,
                          progress_percent, final_score, started_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "program_key": payload.program_key,
                "program_version": payload.program_version,
                "field_mission_id": str(payload.field_mission_id) if payload.field_mission_id else None,
                "location_id": payload.location_id,
                "auditor_subject": actor_subject,
                "manager_subject": payload.manager_subject,
                "source_mode": payload.source_mode,
                "started_at": now,
            },
        )
        return _row_dict(result.one())


async def list_runs(
    tenant_id: str,
    *,
    location_ids: frozenset[str] | None,
    regions: frozenset[str] | None,
    unrestricted: bool,
    limit: int = 100,
) -> list[dict[str, object]]:
    if not unrestricted and not location_ids and not regions:
        return []
    statement = text(
        """
        SELECT ar.id, ar.program_key, ar.program_version, ar.location_id,
               fl.name AS location_name, fl.region, ar.auditor_subject,
               ar.manager_subject, ar.status, ar.source_mode,
               ar.progress_percent, ar.final_score, ar.started_at,
               ar.submitted_at, ar.completed_at
        FROM audit_runs ar
        JOIN field_locations fl
          ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
        WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
          AND (
            :unrestricted
            OR ar.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
            OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
          )
        ORDER BY ar.started_at DESC
        LIMIT :limit
        """
    )
    values = {
        "tenant_id": tenant_id,
        "unrestricted": unrestricted,
        "location_ids": sorted(location_ids or ()),
        "regions": sorted(regions or ()),
        "limit": max(1, min(limit, 500)),
    }
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(statement, values)
        return [_row_dict(row) for row in result]


async def append_redaction_receipt(
    tenant_id: str,
    audit_run_id: UUID,
    payload: AuditRedactionReceiptCreate,
) -> dict[str, object]:
    try:
        async with engine.begin() as connection:
            await _set_tenant(connection, tenant_id)
            result = await connection.execute(
                text(
                    """
                    INSERT INTO audit_redaction_receipts (
                        tenant_id, audit_run_id, location_id, device_id, media_kind,
                        source_fingerprint, redacted_evidence_ref, privacy_policy_version,
                        detector_model_ref, frame_count, processed_frame_count
                    )
                    SELECT CAST(:tenant_id AS UUID), ar.id, :location_id, :device_id,
                           :media_kind, :source_fingerprint, :redacted_evidence_ref,
                           :privacy_policy_version, :detector_model_ref,
                           :frame_count, :processed_frame_count
                    FROM audit_runs ar
                    WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                      AND ar.id = CAST(:audit_run_id AS UUID)
                      AND ar.location_id = :location_id
                    RETURNING id, audit_run_id, location_id, media_kind,
                              source_fingerprint, redacted_evidence_ref,
                              privacy_policy_version, detector_model_ref,
                              frame_count, processed_frame_count, created_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "audit_run_id": str(audit_run_id),
                    "location_id": payload.location_id,
                    "device_id": payload.device_id,
                    "media_kind": payload.media_kind,
                    "source_fingerprint": payload.source_fingerprint,
                    "redacted_evidence_ref": payload.redacted_evidence_ref,
                    "privacy_policy_version": payload.privacy_policy_version,
                    "detector_model_ref": payload.detector_model_ref,
                    "frame_count": payload.frame_count,
                    "processed_frame_count": payload.processed_frame_count,
                },
            )
            row = result.first()
            if not row:
                raise AuditRepositoryError("audit run/location mismatch")
            return _row_dict(row)
    except IntegrityError as exc:
        raise AuditConflictError("redaction receipt already exists or is invalid") from exc


async def append_decision_event(
    tenant_id: str,
    actor_subject: str,
    audit_run_id: UUID,
    payload: AuditDecisionEventCreate,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                INSERT INTO audit_item_decision_events (
                    tenant_id, audit_run_id, item_key, decision_source,
                    decision, confidence, model_or_rule_ref, reason,
                    evidence_refs, actor_subject
                )
                SELECT CAST(:tenant_id AS UUID), ar.id, :item_key, :decision_source,
                       :decision, :confidence, :model_or_rule_ref, :reason,
                       CAST(:evidence_refs AS JSONB), :actor_subject
                FROM audit_runs ar
                WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                  AND ar.id = CAST(:audit_run_id AS UUID)
                  AND ar.status <> 'cancelled'
                RETURNING id, audit_run_id, item_key, decision_source,
                          decision, confidence, model_or_rule_ref, reason,
                          evidence_refs, actor_subject, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "item_key": payload.item_key,
                "decision_source": payload.decision_source,
                "decision": payload.decision,
                "confidence": payload.confidence,
                "model_or_rule_ref": payload.model_or_rule_ref,
                "reason": payload.reason,
                "evidence_refs": _serialize(payload.evidence_refs),
                "actor_subject": actor_subject,
            },
        )
        row = result.first()
        if not row:
            raise AuditRepositoryError("audit run not found or cancelled")
        return _row_dict(row)


async def create_action(
    tenant_id: str,
    actor_subject: str,
    audit_run_id: UUID,
    payload: AuditActionCreate,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                INSERT INTO audit_actions (
                    tenant_id, audit_run_id, item_key, title, description,
                    risk_class, priority, assignee_subject, due_at, created_by
                )
                SELECT CAST(:tenant_id AS UUID), ar.id, :item_key, :title, :description,
                       :risk_class, :priority, :assignee_subject, :due_at, :created_by
                FROM audit_runs ar
                WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                  AND ar.id = CAST(:audit_run_id AS UUID)
                  AND ar.status <> 'cancelled'
                RETURNING id, audit_run_id, item_key, title, description,
                          risk_class, priority, status, assignee_subject,
                          due_at, version, created_by, created_at, updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "item_key": payload.item_key,
                "title": payload.title,
                "description": payload.description,
                "risk_class": payload.risk_class,
                "priority": payload.priority,
                "assignee_subject": payload.assignee_subject,
                "due_at": payload.due_at,
                "created_by": actor_subject,
            },
        )
        row = result.first()
        if not row:
            raise AuditRepositoryError("audit run not found or cancelled")
        return _row_dict(row)


async def list_actions(
    tenant_id: str,
    *,
    location_ids: frozenset[str] | None,
    regions: frozenset[str] | None,
    unrestricted: bool,
    limit: int = 100,
) -> list[dict[str, object]]:
    if not unrestricted and not location_ids and not regions:
        return []
    statement = text(
        """
        SELECT aa.id, aa.audit_run_id, aa.item_key, aa.title, aa.description,
               aa.risk_class, aa.priority, aa.status, aa.assignee_subject,
               aa.due_at, aa.closure_evidence_ref, aa.verification_receipt_ref,
               aa.version, aa.created_by, aa.created_at, aa.updated_at,
               ar.program_key, ar.program_version, ar.location_id,
               fl.name AS location_name, fl.region, ar.started_at AS audit_started_at,
               COALESCE(origin.field_definition, '{}'::jsonb) AS origin_field
        FROM audit_actions aa
        JOIN audit_runs ar
          ON ar.tenant_id = aa.tenant_id AND ar.id = aa.audit_run_id
        JOIN field_locations fl
          ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
        JOIN audit_program_versions apv
          ON apv.tenant_id = ar.tenant_id
         AND apv.program_key = ar.program_key
         AND apv.version = ar.program_version
        JOIN field_templates ft
          ON ft.tenant_id = apv.tenant_id
         AND ft.template_id = apv.field_template_id
         AND ft.version = apv.field_template_version
        LEFT JOIN LATERAL (
          SELECT field_definition
          FROM jsonb_array_elements(COALESCE(ft.schema->'fields', '[]'::jsonb))
               AS field_definition
          WHERE field_definition->>'key' = aa.item_key
          LIMIT 1
        ) origin ON TRUE
        WHERE aa.tenant_id = CAST(:tenant_id AS UUID)
          AND (
            :unrestricted
            OR ar.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
            OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
          )
        ORDER BY (aa.status = 'closed'), aa.due_at, aa.created_at DESC
        LIMIT :limit
        """
    )
    values = {
        "tenant_id": tenant_id,
        "unrestricted": unrestricted,
        "location_ids": sorted(location_ids or ()),
        "regions": sorted(regions or ()),
        "limit": max(1, min(limit, 500)),
    }
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(statement, values)
        return [_row_dict(row) for row in result]


async def get_action(tenant_id: str, action_id: UUID) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT aa.id, aa.audit_run_id, aa.item_key, aa.title, aa.description,
                       aa.risk_class, aa.priority, aa.status, aa.assignee_subject,
                       aa.due_at, aa.closure_evidence_ref, aa.verification_receipt_ref,
                       aa.version, aa.created_by, aa.created_at, aa.updated_at,
                       ar.program_key, ar.program_version, ar.location_id,
                       fl.name AS location_name, fl.region, ar.started_at AS audit_started_at,
                       COALESCE(origin.field_definition, '{}'::jsonb) AS origin_field
                FROM audit_actions aa
                JOIN audit_runs ar ON ar.tenant_id = aa.tenant_id AND ar.id = aa.audit_run_id
                JOIN field_locations fl ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                JOIN audit_program_versions apv
                  ON apv.tenant_id = ar.tenant_id AND apv.program_key = ar.program_key
                 AND apv.version = ar.program_version
                JOIN field_templates ft
                  ON ft.tenant_id = apv.tenant_id AND ft.template_id = apv.field_template_id
                 AND ft.version = apv.field_template_version
                LEFT JOIN LATERAL (
                  SELECT field_definition
                  FROM jsonb_array_elements(COALESCE(ft.schema->'fields', '[]'::jsonb)) AS field_definition
                  WHERE field_definition->>'key' = aa.item_key
                  LIMIT 1
                ) origin ON TRUE
                WHERE aa.tenant_id = CAST(:tenant_id AS UUID)
                  AND aa.id = CAST(:action_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "action_id": str(action_id)},
        )
        row = result.first()
        return _row_dict(row) if row else None


_ALLOWED_ACTION_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"in_progress", "rejected"}),
    "in_progress": frozenset({"submitted_for_verification", "rejected"}),
    "submitted_for_verification": frozenset({"ai_verified", "human_verified", "rejected"}),
    "ai_verified": frozenset({"closed", "rejected"}),
    "human_verified": frozenset({"closed", "rejected"}),
    "rejected": frozenset({"in_progress"}),
    "closed": frozenset(),
}


async def update_action(
    tenant_id: str,
    action_id: UUID,
    payload: AuditActionUpdate,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        existing = await connection.execute(
            text(
                """
                SELECT status, version
                FROM audit_actions
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:action_id AS UUID)
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "action_id": str(action_id)},
        )
        row = existing.first()
        if not row:
            raise AuditRepositoryError("audit action not found")
        if row.version != payload.expected_version:
            raise AuditConflictError("audit action version conflict")
        if payload.status != row.status and payload.status not in _ALLOWED_ACTION_TRANSITIONS[row.status]:
            raise AuditConflictError(f"invalid audit action transition: {row.status} -> {payload.status}")

        result = await connection.execute(
            text(
                """
                UPDATE audit_actions
                SET status = :status,
                    assignee_subject = COALESCE(:assignee_subject, assignee_subject),
                    due_at = COALESCE(:due_at, due_at),
                    closure_evidence_ref = :closure_evidence_ref,
                    verification_receipt_ref = :verification_receipt_ref,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:action_id AS UUID)
                  AND version = :expected_version
                RETURNING id, audit_run_id, item_key, title, description,
                          risk_class, priority, status, assignee_subject, due_at,
                          closure_evidence_ref, verification_receipt_ref,
                          version, created_by, created_at, updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "action_id": str(action_id),
                "status": payload.status,
                "assignee_subject": payload.assignee_subject,
                "due_at": payload.due_at,
                "closure_evidence_ref": payload.closure_evidence_ref,
                "verification_receipt_ref": payload.verification_receipt_ref,
                "expected_version": payload.expected_version,
            },
        )
        updated = result.first()
        if not updated:
            raise AuditConflictError("audit action changed concurrently")
        return _row_dict(updated)


async def append_assurance_review(
    tenant_id: str,
    actor_subject: str,
    audit_run_id: UUID,
    payload: AuditAssuranceReviewCreate,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                INSERT INTO audit_assurance_reviews (
                    tenant_id, audit_run_id, item_key, state,
                    reviewer_subject, disposition, reason
                )
                SELECT CAST(:tenant_id AS UUID), ar.id, :item_key, :state,
                       :reviewer_subject, :disposition, :reason
                FROM audit_runs ar
                WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                  AND ar.id = CAST(:audit_run_id AS UUID)
                RETURNING id, audit_run_id, item_key, state,
                          reviewer_subject, disposition, reason, reviewed_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
                "item_key": payload.item_key,
                "state": payload.state,
                "reviewer_subject": actor_subject,
                "disposition": payload.disposition,
                "reason": payload.reason,
            },
        )
        row = result.first()
        if not row:
            raise AuditRepositoryError("audit run not found")
        return _row_dict(row)
