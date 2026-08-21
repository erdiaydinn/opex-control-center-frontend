from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.resources import engine

from .accountability import resolve_location_manager_subject
from .control_contracts import parse_question_controls
from .repository import AuditConflictError, AuditRepositoryError
from .visit_planning import (
    AuditVisitCreate,
    AuditVisitNoteCreate,
    AuditVisitRunStart,
    build_visit_plan,
)


def _row_dict(row) -> dict[str, object]:
    return dict(row._mapping)


async def _set_tenant(connection, tenant_id: str) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def _serialize(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def _require_active_location(connection, tenant_id: str, location_id: str) -> None:
    result = await connection.execute(
        text(
            """
            SELECT 1
            FROM field_locations
            WHERE tenant_id = CAST(:tenant_id AS UUID)
              AND location_id = :location_id
              AND active IS TRUE
            """
        ),
        {"tenant_id": tenant_id, "location_id": location_id},
    )
    if not result.first():
        raise AuditRepositoryError("audit visit location is not active")


async def _require_active_program(
    connection,
    tenant_id: str,
    program_key: str,
    program_version: int,
    *,
    now: datetime,
) -> dict[str, object]:
    result = await connection.execute(
        text(
            """
            SELECT program_key, version, settings
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
            "program_key": program_key,
            "program_version": program_version,
            "now": now,
        },
    )
    row = result.first()
    if not row:
        raise AuditRepositoryError("audit visit program is not active/effective")
    return _row_dict(row)


def _validate_scope_against_program(
    payload: AuditVisitCreate,
    settings: dict[str, object],
) -> None:
    controls = parse_question_controls(settings)
    if not controls:
        raise AuditRepositoryError(
            "scored visits require a governed question_controls library"
        )

    approved = {control.item_key for control in controls}
    supplied = {entry.item_key for entry in payload.scope}
    missing = sorted(approved - supplied)
    unknown = sorted(supplied - approved)
    if missing or unknown:
        parts: list[str] = []
        if missing:
            parts.append(f"missing approved items: {', '.join(missing[:10])}")
        if unknown:
            parts.append(f"unknown items: {', '.join(unknown[:10])}")
        raise AuditRepositoryError(
            "visit scope must cover the exact approved question library; " + "; ".join(parts)
        )


async def create_visit_manifest(
    tenant_id: str,
    actor_subject: str,
    payload: AuditVisitCreate,
) -> dict[str, object]:
    now = datetime.now(UTC)
    plan = build_visit_plan(payload)
    try:
        async with engine.begin() as connection:
            await _set_tenant(connection, tenant_id)
            await _require_active_location(connection, tenant_id, payload.location_id)

            if payload.program_key is not None and payload.program_version is not None:
                program = await _require_active_program(
                    connection,
                    tenant_id,
                    payload.program_key,
                    payload.program_version,
                    now=now,
                )
                settings = program.get("settings")
                if not isinstance(settings, dict):
                    raise AuditRepositoryError("audit program settings are invalid")
                _validate_scope_against_program(payload, settings)

            result = await connection.execute(
                text(
                    """
                    INSERT INTO audit_visit_manifests (
                        tenant_id, location_id, program_key, program_version,
                        visit_type, title, score_mode, official_compliance_eligible,
                        scope_manifest, people_topics, scope_fingerprint, rationale,
                        created_by
                    ) VALUES (
                        CAST(:tenant_id AS UUID), :location_id, :program_key,
                        :program_version, :visit_type, :title, :score_mode,
                        :official_compliance_eligible, CAST(:scope_manifest AS JSONB),
                        CAST(:people_topics AS JSONB), :scope_fingerprint, :rationale,
                        :created_by
                    )
                    RETURNING id, location_id, program_key, program_version,
                              visit_type, title, status, score_mode,
                              official_compliance_eligible, scope_manifest,
                              people_topics, scope_fingerprint, rationale,
                              created_by, created_at, completed_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "location_id": payload.location_id,
                    "program_key": payload.program_key,
                    "program_version": payload.program_version,
                    "visit_type": payload.visit_type,
                    "title": payload.title,
                    "score_mode": plan.score_mode,
                    "official_compliance_eligible": plan.official_compliance_eligible,
                    "scope_manifest": _serialize(
                        [entry.model_dump(mode="json") for entry in payload.scope]
                    ),
                    "people_topics": _serialize(list(payload.people_topics)),
                    "scope_fingerprint": plan.scope_fingerprint,
                    "rationale": payload.rationale,
                    "created_by": actor_subject,
                },
            )
            visit = _row_dict(result.one())
            visit["in_scope_count"] = plan.in_scope_count
            visit["out_of_scope_count"] = plan.out_of_scope_count
            visit["section_count"] = plan.section_count
            return visit
    except IntegrityError as exc:
        raise AuditConflictError("audit visit manifest is invalid or conflicts") from exc


async def get_visit_location(
    tenant_id: str,
    visit_manifest_id: UUID,
) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT fl.location_id, fl.name, fl.region, fl.city, fl.active
                FROM audit_visit_manifests avm
                JOIN field_locations fl
                  ON fl.tenant_id = avm.tenant_id
                 AND fl.location_id = avm.location_id
                WHERE avm.tenant_id = CAST(:tenant_id AS UUID)
                  AND avm.id = CAST(:visit_manifest_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "visit_manifest_id": str(visit_manifest_id)},
        )
        row = result.first()
        return _row_dict(row) if row else None


async def get_visit_manifest(
    tenant_id: str,
    visit_manifest_id: UUID,
) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT id, location_id, program_key, program_version,
                       visit_type, title, status, score_mode,
                       official_compliance_eligible, scope_manifest,
                       people_topics, scope_fingerprint, rationale,
                       created_by, created_at, completed_at
                FROM audit_visit_manifests
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:visit_manifest_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "visit_manifest_id": str(visit_manifest_id)},
        )
        row = result.first()
        return _row_dict(row) if row else None


async def list_visit_manifests(
    tenant_id: str,
    *,
    location_ids: frozenset[str] | None,
    regions: frozenset[str] | None,
    unrestricted: bool,
    limit: int = 100,
) -> list[dict[str, object]]:
    if not unrestricted and not location_ids and not regions:
        return []
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT avm.id, avm.location_id, fl.name AS location_name,
                       fl.region, avm.program_key, avm.program_version,
                       avm.visit_type, avm.title, avm.status, avm.score_mode,
                       avm.official_compliance_eligible, avm.scope_manifest,
                       avm.people_topics, avm.scope_fingerprint, avm.rationale,
                       avm.created_by, avm.created_at, avm.completed_at
                FROM audit_visit_manifests avm
                JOIN field_locations fl
                  ON fl.tenant_id = avm.tenant_id
                 AND fl.location_id = avm.location_id
                WHERE avm.tenant_id = CAST(:tenant_id AS UUID)
                  AND (
                    :unrestricted
                    OR avm.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
                    OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
                  )
                ORDER BY avm.created_at DESC
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
        return [_row_dict(row) for row in result]


async def append_visit_note(
    tenant_id: str,
    actor_subject: str,
    visit_manifest_id: UUID,
    payload: AuditVisitNoteCreate,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                INSERT INTO audit_visit_notes (
                    tenant_id, visit_manifest_id, note_type, note,
                    source_refs, created_by
                )
                SELECT CAST(:tenant_id AS UUID), avm.id, :note_type, :note,
                       CAST(:source_refs AS JSONB), :created_by
                FROM audit_visit_manifests avm
                WHERE avm.tenant_id = CAST(:tenant_id AS UUID)
                  AND avm.id = CAST(:visit_manifest_id AS UUID)
                  AND avm.status = 'active'
                RETURNING id, visit_manifest_id, note_type, note,
                          source_refs, created_by, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "visit_manifest_id": str(visit_manifest_id),
                "note_type": payload.note_type,
                "note": payload.note.strip(),
                "source_refs": _serialize(list(payload.source_refs)),
                "created_by": actor_subject,
            },
        )
        row = result.first()
        if not row:
            raise AuditRepositoryError("active audit visit not found")
        return _row_dict(row)


async def list_visit_notes(
    tenant_id: str,
    visit_manifest_id: UUID,
) -> list[dict[str, object]]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT id, visit_manifest_id, note_type, note,
                       source_refs, created_by, created_at
                FROM audit_visit_notes
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND visit_manifest_id = CAST(:visit_manifest_id AS UUID)
                ORDER BY created_at, id
                """
            ),
            {"tenant_id": tenant_id, "visit_manifest_id": str(visit_manifest_id)},
        )
        return [_row_dict(row) for row in result]


async def start_visit_run(
    tenant_id: str,
    actor_subject: str,
    visit_manifest_id: UUID,
    payload: AuditVisitRunStart,
) -> dict[str, object]:
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            await _set_tenant(connection, tenant_id)
            visit_result = await connection.execute(
                text(
                    """
                    SELECT id, location_id, program_key, program_version,
                           visit_type, status, score_mode,
                           official_compliance_eligible
                    FROM audit_visit_manifests
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                      AND id = CAST(:visit_manifest_id AS UUID)
                    FOR UPDATE
                    """
                ),
                {"tenant_id": tenant_id, "visit_manifest_id": str(visit_manifest_id)},
            )
            visit_row = visit_result.first()
            if not visit_row:
                raise AuditRepositoryError("audit visit not found")
            visit = _row_dict(visit_row)
            if visit["status"] != "active":
                raise AuditConflictError("audit visit is not active")
            if visit["score_mode"] == "NO_SCORE":
                raise AuditRepositoryError("non-scored people visit cannot start an audit run")

            program_key = str(visit["program_key"] or "")
            program_version = int(visit["program_version"] or 0)
            await _require_active_program(
                connection,
                tenant_id,
                program_key,
                program_version,
                now=now,
            )
            location_id = str(visit["location_id"])
            await _require_active_location(connection, tenant_id, location_id)
            manager_subject = await resolve_location_manager_subject(
                connection,
                tenant_id=tenant_id,
                location_id=location_id,
            )

            result = await connection.execute(
                text(
                    """
                    INSERT INTO audit_runs (
                        tenant_id, program_key, program_version, field_mission_id,
                        location_id, auditor_subject, manager_subject,
                        source_mode, started_at, visit_manifest_id,
                        visit_score_mode, official_compliance_eligible
                    ) VALUES (
                        CAST(:tenant_id AS UUID), :program_key, :program_version,
                        CAST(:field_mission_id AS UUID), :location_id, :auditor_subject,
                        :manager_subject, :source_mode, :started_at,
                        CAST(:visit_manifest_id AS UUID), :visit_score_mode,
                        :official_compliance_eligible
                    )
                    RETURNING id, program_key, program_version, location_id,
                              auditor_subject, manager_subject, status, source_mode,
                              progress_percent, final_score, started_at,
                              visit_manifest_id, visit_score_mode,
                              official_compliance_eligible
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "program_key": program_key,
                    "program_version": program_version,
                    "field_mission_id": (
                        str(payload.field_mission_id) if payload.field_mission_id else None
                    ),
                    "location_id": location_id,
                    "auditor_subject": actor_subject,
                    "manager_subject": manager_subject,
                    "source_mode": payload.source_mode,
                    "started_at": now,
                    "visit_manifest_id": str(visit_manifest_id),
                    "visit_score_mode": visit["score_mode"],
                    "official_compliance_eligible": bool(
                        visit["official_compliance_eligible"]
                    ),
                },
            )
            run = _row_dict(result.one())
            run["visit_type"] = visit["visit_type"]
            return run
    except IntegrityError as exc:
        raise AuditConflictError("audit visit run already exists or is invalid") from exc


async def complete_visit_manifest(
    tenant_id: str,
    visit_manifest_id: UUID,
) -> dict[str, object]:
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT id, status, score_mode
                FROM audit_visit_manifests
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:visit_manifest_id AS UUID)
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "visit_manifest_id": str(visit_manifest_id)},
        )
        row = result.first()
        if not row:
            raise AuditRepositoryError("audit visit not found")
        visit = _row_dict(row)
        if visit["status"] != "active":
            raise AuditConflictError("audit visit is not active")

        if visit["score_mode"] != "NO_SCORE":
            run_result = await connection.execute(
                text(
                    """
                    SELECT status
                    FROM audit_runs
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                      AND visit_manifest_id = CAST(:visit_manifest_id AS UUID)
                    """
                ),
                {"tenant_id": tenant_id, "visit_manifest_id": str(visit_manifest_id)},
            )
            run_row = run_result.first()
            if not run_row or str(run_row.status) != "completed":
                raise AuditConflictError(
                    "scored audit visit cannot complete before its audit run completes"
                )

        updated = await connection.execute(
            text(
                """
                UPDATE audit_visit_manifests
                SET status = 'completed', completed_at = :completed_at
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:visit_manifest_id AS UUID)
                  AND status = 'active'
                RETURNING id, location_id, program_key, program_version,
                          visit_type, title, status, score_mode,
                          official_compliance_eligible, scope_fingerprint,
                          completed_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "visit_manifest_id": str(visit_manifest_id),
                "completed_at": now,
            },
        )
        return _row_dict(updated.one())
