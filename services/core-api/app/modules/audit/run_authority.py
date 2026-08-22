from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text

from app.core.resources import engine

from .accountability import resolve_location_manager_subject
from .repository import AuditRepositoryError
from .schemas import AuditRunStart


def _dict(row) -> dict[str, object]:
    return dict(row._mapping)


async def start_authoritative_run(
    tenant_id: str,
    actor_subject: str,
    payload: AuditRunStart,
) -> dict[str, object]:
    """Start a run with manager identity resolved by server-owned accountability."""

    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
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
                SELECT 1
                FROM field_locations
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND location_id = :location_id
                  AND active IS TRUE
                """
            ),
            {"tenant_id": tenant_id, "location_id": payload.location_id},
        )
        if not location.first():
            raise AuditRepositoryError("audit location is not active")

        manager_subject = await resolve_location_manager_subject(
            connection,
            tenant_id=tenant_id,
            location_id=payload.location_id,
        )
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
                "field_mission_id": (
                    str(payload.field_mission_id)
                    if payload.field_mission_id
                    else None
                ),
                "location_id": payload.location_id,
                "auditor_subject": actor_subject,
                "manager_subject": manager_subject,
                "source_mode": payload.source_mode,
                "started_at": now,
            },
        )
        return _dict(result.one())
