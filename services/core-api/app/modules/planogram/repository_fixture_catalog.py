from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.planogram.fixture_catalog import FixtureCatalogStateError


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


async def _record_event(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
    *,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text("""
        INSERT INTO planogram_fixture_catalog_events (
            tenant_id, fixture_catalog_version_id, event_type, actor_subject,
            from_status, to_status, reason, payload
        ) VALUES (
            :tenant_id, :version_id, :event_type, :actor_subject,
            :from_status, :to_status, :reason, CAST(:payload AS jsonb)
        )
        """),
        {
            "tenant_id": principal.tenant_id,
            "version_id": version_id,
            "event_type": event_type,
            "actor_subject": principal.subject,
            "from_status": from_status,
            "to_status": to_status,
            "reason": reason,
            "payload": _json_text(payload or {}),
        },
    )


async def list_fixture_catalog_versions(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = ((await session.execute(text("""
        SELECT id, fixture_code, fixture_name, version_number, status,
               record, record_sha256, created_by, created_at, updated_at,
               submitted_by, submitted_at, approved_by, approved_at,
               rejected_by, rejected_at, rejection_reason, supersedes_version_id
        FROM planogram_fixture_catalog_versions
        WHERE tenant_id=:tenant_id
        ORDER BY fixture_code, version_number DESC
        """), {"tenant_id": principal.tenant_id})).mappings().all())
    return [dict(row) for row in rows]


async def create_fixture_catalog_draft(
    session: AsyncSession,
    principal: Principal,
    *,
    fixture_code: str,
    fixture_name: str,
    record: dict[str, Any],
    record_sha256: str,
    supersedes_version_id: UUID | None = None,
    event_type: str = "created",
    event_reason: str | None = None,
) -> dict[str, Any]:
    row = ((await session.execute(text("""
        WITH fixture_lock AS MATERIALIZED (
            SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))
        ), next_version AS (
            SELECT COALESCE(MAX(version_number), 0) + 1 AS value
            FROM planogram_fixture_catalog_versions, fixture_lock
            WHERE tenant_id=:tenant_id AND fixture_code=:fixture_code
        )
        INSERT INTO planogram_fixture_catalog_versions (
            tenant_id, fixture_code, fixture_name, version_number, status,
            record, record_sha256, created_by, supersedes_version_id
        )
        SELECT :tenant_id, :fixture_code, :fixture_name, next_version.value, 'draft',
               CAST(:record AS jsonb), :record_sha256, :created_by, :supersedes_version_id
        FROM next_version
        WHERE NOT EXISTS (
            SELECT 1 FROM planogram_fixture_catalog_versions
            WHERE tenant_id=:tenant_id AND fixture_code=:fixture_code
              AND status IN ('draft','submitted')
        )
        RETURNING id, fixture_code, fixture_name, version_number, status,
                  record, record_sha256, created_by, created_at, updated_at,
                  submitted_by, submitted_at, approved_by, approved_at,
                  rejected_by, rejected_at, rejection_reason, supersedes_version_id
        """), {
            "lock_key": f"planogram-fixture-catalog:{principal.tenant_id}:{fixture_code}",
            "tenant_id": principal.tenant_id,
            "fixture_code": fixture_code,
            "fixture_name": fixture_name,
            "record": _json_text(record),
            "record_sha256": record_sha256,
            "created_by": principal.subject,
            "supersedes_version_id": supersedes_version_id,
        })).mappings().one_or_none())
    if row is None:
        raise FixtureCatalogStateError("active_fixture_catalog_draft_or_submission_exists")
    result = dict(row)
    await _record_event(session, principal, result["id"], event_type=event_type,
                        from_status=None, to_status="draft", reason=event_reason,
                        payload={"record_sha256": record_sha256})
    return result


async def update_fixture_catalog_draft(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
    *,
    fixture_code: str,
    fixture_name: str,
    record: dict[str, Any],
    record_sha256: str,
) -> dict[str, Any]:
    row = ((await session.execute(text("""
        UPDATE planogram_fixture_catalog_versions
        SET fixture_name=:fixture_name, record=CAST(:record AS jsonb),
            record_sha256=:record_sha256, updated_at=CURRENT_TIMESTAMP
        WHERE tenant_id=:tenant_id AND id=:version_id
          AND fixture_code=:fixture_code AND status='draft'
        RETURNING id, fixture_code, fixture_name, version_number, status,
                  record, record_sha256, created_by, created_at, updated_at,
                  submitted_by, submitted_at, approved_by, approved_at,
                  rejected_by, rejected_at, rejection_reason, supersedes_version_id
        """), {
            "tenant_id": principal.tenant_id, "version_id": version_id,
            "fixture_code": fixture_code, "fixture_name": fixture_name,
            "record": _json_text(record), "record_sha256": record_sha256,
        })).mappings().one_or_none())
    if row is None:
        raise FixtureCatalogStateError("fixture_catalog_draft_not_found_or_not_editable")
    result = dict(row)
    await _record_event(session, principal, version_id, event_type="updated",
                        from_status="draft", to_status="draft",
                        payload={"record_sha256": record_sha256})
    return result


async def submit_fixture_catalog(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
) -> dict[str, Any]:
    row = ((await session.execute(text("""
        UPDATE planogram_fixture_catalog_versions
        SET status='submitted', submitted_by=:actor_subject,
            submitted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
        WHERE tenant_id=:tenant_id AND id=:version_id AND status='draft'
        RETURNING id, fixture_code, fixture_name, version_number, status,
                  record, record_sha256, created_by, created_at, updated_at,
                  submitted_by, submitted_at, approved_by, approved_at,
                  rejected_by, rejected_at, rejection_reason, supersedes_version_id
        """), {
            "tenant_id": principal.tenant_id, "version_id": version_id,
            "actor_subject": principal.subject,
        })).mappings().one_or_none())
    if row is None:
        raise FixtureCatalogStateError("fixture_catalog_draft_not_found_or_not_submittable")
    result = dict(row)
    await _record_event(session, principal, version_id, event_type="submitted",
                        from_status="draft", to_status="submitted",
                        payload={"record_sha256": result["record_sha256"]})
    return result


async def approve_fixture_catalog(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
    *,
    note: str | None,
) -> dict[str, Any]:
    target = (
        (
            await session.execute(
                text("""
                SELECT id, fixture_code, status, submitted_by
                FROM planogram_fixture_catalog_versions
                WHERE tenant_id=:tenant_id AND id=:version_id FOR UPDATE
                """),
                {"tenant_id": principal.tenant_id, "version_id": version_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if target is None or target["status"] != "submitted":
        raise FixtureCatalogStateError("fixture_catalog_submission_not_found_or_not_approvable")
    if target["submitted_by"] == principal.subject:
        raise FixtureCatalogStateError("maker_checker_required")

    fixture_code = str(target["fixture_code"])
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"planogram-fixture-catalog:{principal.tenant_id}:{fixture_code}"},
    )
    superseded = ((await session.execute(text("""
        UPDATE planogram_fixture_catalog_versions
        SET status='superseded', updated_at=CURRENT_TIMESTAMP
        WHERE tenant_id=:tenant_id AND fixture_code=:fixture_code
          AND status='approved' AND id<>:version_id RETURNING id
        """), {
            "tenant_id": principal.tenant_id, "fixture_code": fixture_code,
            "version_id": version_id,
        })).mappings().all())
    for old in superseded:
        await _record_event(session, principal, old["id"], event_type="superseded",
                            from_status="approved", to_status="superseded",
                            reason="new_fixture_catalog_version_approved")

    row = ((await session.execute(text("""
        UPDATE planogram_fixture_catalog_versions
        SET status='approved', approved_by=:actor_subject,
            approved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
        WHERE tenant_id=:tenant_id AND id=:version_id AND status='submitted'
        RETURNING id, fixture_code, fixture_name, version_number, status,
                  record, record_sha256, created_by, created_at, updated_at,
                  submitted_by, submitted_at, approved_by, approved_at,
                  rejected_by, rejected_at, rejection_reason, supersedes_version_id
        """), {
            "tenant_id": principal.tenant_id, "version_id": version_id,
            "actor_subject": principal.subject,
        })).mappings().one())
    result = dict(row)
    await _record_event(session, principal, version_id, event_type="approved",
                        from_status="submitted", to_status="approved", reason=note,
                        payload={"record_sha256": result["record_sha256"]})
    return result


async def reject_fixture_catalog(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
    *,
    reason: str,
) -> dict[str, Any]:
    row = ((await session.execute(text("""
        UPDATE planogram_fixture_catalog_versions
        SET status='rejected', rejected_by=:actor_subject,
            rejected_at=CURRENT_TIMESTAMP, rejection_reason=:reason,
            updated_at=CURRENT_TIMESTAMP
        WHERE tenant_id=:tenant_id AND id=:version_id AND status='submitted'
        RETURNING id, fixture_code, fixture_name, version_number, status,
                  record, record_sha256, created_by, created_at, updated_at,
                  submitted_by, submitted_at, approved_by, approved_at,
                  rejected_by, rejected_at, rejection_reason, supersedes_version_id
        """), {
            "tenant_id": principal.tenant_id, "version_id": version_id,
            "actor_subject": principal.subject, "reason": reason,
        })).mappings().one_or_none())
    if row is None:
        raise FixtureCatalogStateError("fixture_catalog_submission_not_found_or_not_rejectable")
    result = dict(row)
    await _record_event(session, principal, version_id, event_type="rejected",
                        from_status="submitted", to_status="rejected", reason=reason)
    return result


async def revise_fixture_catalog(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
    *,
    reason: str,
) -> dict[str, Any]:
    source = (
        (
            await session.execute(
                text("""
                SELECT id, fixture_code, fixture_name, status, record, record_sha256
                FROM planogram_fixture_catalog_versions
                WHERE tenant_id=:tenant_id AND id=:version_id
                  AND status IN ('approved','rejected','superseded')
                """),
                {"tenant_id": principal.tenant_id, "version_id": version_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        raise FixtureCatalogStateError("fixture_catalog_version_not_revisable")
    return await create_fixture_catalog_draft(
        session, principal, fixture_code=str(source["fixture_code"]),
        fixture_name=str(source["fixture_name"]), record=dict(source["record"]),
        record_sha256=str(source["record_sha256"]), supersedes_version_id=source["id"],
        event_type="revised", event_reason=reason,
    )


async def get_approved_fixture_catalog_versions(
    session: AsyncSession,
    principal: Principal,
    version_ids: Iterable[UUID],
) -> dict[UUID, dict[str, Any]]:
    requested = tuple(dict.fromkeys(version_ids))
    if not requested:
        return {}
    rows = ((await session.execute(text("""
        SELECT id, fixture_code, fixture_name, version_number, status,
               record, record_sha256, approved_by, approved_at
        FROM planogram_fixture_catalog_versions
        WHERE tenant_id=:tenant_id AND status='approved' AND id = ANY(:version_ids)
        """), {
            "tenant_id": principal.tenant_id, "version_ids": list(requested),
        })).mappings().all())
    result = {row["id"]: dict(row) for row in rows}
    if any(version_id not in result for version_id in requested):
        raise FixtureCatalogStateError("approved_fixture_catalog_version_not_found")
    return result
