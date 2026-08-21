from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.planogram.store_dna import (
    StoreDnaStateError,
    clone_configuration,
    configuration_fingerprint,
)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


async def _record_store_dna_event(
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
        INSERT INTO planogram_store_dna_events (
            tenant_id, store_dna_version_id, event_type, actor_subject,
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


async def list_store_dna_versions(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text("""
                SELECT
                    id, store_code, store_name, version_number, source, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, created_by, created_at, updated_at,
                    submitted_by, submitted_at, approved_by, approved_at,
                    rejected_by, rejected_at, rejection_reason,
                    supersedes_version_id
                FROM planogram_store_dna_versions
                WHERE tenant_id=:tenant_id
                ORDER BY store_code, version_number DESC
                """),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def create_store_dna_draft(
    session: AsyncSession,
    principal: Principal,
    *,
    store_code: str,
    store_name: str | None,
    source: str,
    configuration: dict[str, Any],
    summary: dict[str, int],
    configuration_sha256: str,
    geometry_attested: bool,
    supersedes_version_id: UUID | None = None,
    event_type: str = "bootstrapped",
    event_reason: str | None = None,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text("""
                WITH store_lock AS MATERIALIZED (
                    SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))
                ),
                next_version AS (
                    SELECT COALESCE(MAX(version_number), 0) + 1 AS value
                    FROM planogram_store_dna_versions, store_lock
                    WHERE tenant_id=:tenant_id AND store_code=:store_code
                )
                INSERT INTO planogram_store_dna_versions (
                    tenant_id, store_code, store_name, version_number, source,
                    status, configuration, summary, configuration_sha256,
                    geometry_attested, created_by, supersedes_version_id
                )
                SELECT
                    :tenant_id, :store_code, :store_name, next_version.value, :source,
                    'draft', CAST(:configuration AS jsonb), CAST(:summary AS jsonb),
                    :configuration_sha256, :geometry_attested, :created_by,
                    :supersedes_version_id
                FROM next_version
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM planogram_store_dna_versions
                    WHERE tenant_id=:tenant_id
                      AND store_code=:store_code
                      AND status IN ('draft', 'submitted')
                )
                RETURNING
                    id, store_code, store_name, version_number, source, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, created_by, created_at, updated_at,
                    submitted_by, submitted_at, approved_by, approved_at,
                    rejected_by, rejected_at, rejection_reason,
                    supersedes_version_id
                """),
                {
                    "lock_key": f"planogram-store-dna:{principal.tenant_id}:{store_code}",
                    "tenant_id": principal.tenant_id,
                    "store_code": store_code,
                    "store_name": store_name,
                    "source": source,
                    "configuration": _json_text(configuration),
                    "summary": _json_text(summary),
                    "configuration_sha256": configuration_sha256,
                    "geometry_attested": geometry_attested,
                    "created_by": principal.subject,
                    "supersedes_version_id": supersedes_version_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise StoreDnaStateError("active_draft_or_submission_exists")

    result = dict(row)
    await _record_store_dna_event(
        session,
        principal,
        result["id"],
        event_type=event_type,
        from_status=None,
        to_status="draft",
        reason=event_reason,
        payload={"configuration_sha256": configuration_sha256},
    )
    return result


async def update_store_dna_draft(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
    *,
    store_code: str,
    store_name: str | None,
    source: str,
    configuration: dict[str, Any],
    summary: dict[str, int],
    configuration_sha256: str,
    geometry_attested: bool,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text("""
                UPDATE planogram_store_dna_versions
                SET store_name=:store_name,
                    source=:source,
                    configuration=CAST(:configuration AS jsonb),
                    summary=CAST(:summary AS jsonb),
                    configuration_sha256=:configuration_sha256,
                    geometry_attested=:geometry_attested,
                    updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:tenant_id
                  AND id=:version_id
                  AND store_code=:store_code
                  AND status='draft'
                RETURNING
                    id, store_code, store_name, version_number, source, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, created_by, created_at, updated_at,
                    submitted_by, submitted_at, approved_by, approved_at,
                    rejected_by, rejected_at, rejection_reason,
                    supersedes_version_id
                """),
                {
                    "tenant_id": principal.tenant_id,
                    "version_id": version_id,
                    "store_code": store_code,
                    "store_name": store_name,
                    "source": source,
                    "configuration": _json_text(configuration),
                    "summary": _json_text(summary),
                    "configuration_sha256": configuration_sha256,
                    "geometry_attested": geometry_attested,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise StoreDnaStateError("draft_not_found_or_not_editable")

    result = dict(row)
    await _record_store_dna_event(
        session,
        principal,
        version_id,
        event_type="updated",
        from_status="draft",
        to_status="draft",
        payload={"configuration_sha256": configuration_sha256},
    )
    return result


async def submit_store_dna(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text("""
                UPDATE planogram_store_dna_versions
                SET status='submitted',
                    submitted_by=:actor_subject,
                    submitted_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:tenant_id
                  AND id=:version_id
                  AND status='draft'
                RETURNING
                    id, store_code, store_name, version_number, source, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, created_by, created_at, updated_at,
                    submitted_by, submitted_at, approved_by, approved_at,
                    rejected_by, rejected_at, rejection_reason,
                    supersedes_version_id
                """),
                {
                    "tenant_id": principal.tenant_id,
                    "version_id": version_id,
                    "actor_subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise StoreDnaStateError("draft_not_found_or_not_submittable")

    result = dict(row)
    await _record_store_dna_event(
        session,
        principal,
        version_id,
        event_type="submitted",
        from_status="draft",
        to_status="submitted",
        payload={"geometry_attested": bool(result["geometry_attested"])},
    )
    return result


async def approve_store_dna(
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
                SELECT id, store_code, status, submitted_by
                FROM planogram_store_dna_versions
                WHERE tenant_id=:tenant_id AND id=:version_id
                FOR UPDATE
                """),
                {"tenant_id": principal.tenant_id, "version_id": version_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if target is None or target["status"] != "submitted":
        raise StoreDnaStateError("submission_not_found_or_not_approvable")
    if target["submitted_by"] == principal.subject:
        raise StoreDnaStateError("maker_checker_required")

    store_code = str(target["store_code"])
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"planogram-store-dna:{principal.tenant_id}:{store_code}"},
    )

    superseded_rows = (
        (
            await session.execute(
                text("""
                UPDATE planogram_store_dna_versions
                SET status='superseded', updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:tenant_id
                  AND store_code=:store_code
                  AND status='approved'
                  AND id<>:version_id
                RETURNING id
                """),
                {
                    "tenant_id": principal.tenant_id,
                    "store_code": store_code,
                    "version_id": version_id,
                },
            )
        )
        .mappings()
        .all()
    )
    for row in superseded_rows:
        await _record_store_dna_event(
            session,
            principal,
            row["id"],
            event_type="superseded",
            from_status="approved",
            to_status="superseded",
            reason="new_store_dna_version_approved",
        )

    approved = (
        (
            await session.execute(
                text("""
                UPDATE planogram_store_dna_versions
                SET status='approved',
                    approved_by=:actor_subject,
                    approved_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:tenant_id
                  AND id=:version_id
                  AND status='submitted'
                RETURNING
                    id, store_code, store_name, version_number, source, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, created_by, created_at, updated_at,
                    submitted_by, submitted_at, approved_by, approved_at,
                    rejected_by, rejected_at, rejection_reason,
                    supersedes_version_id
                """),
                {
                    "tenant_id": principal.tenant_id,
                    "version_id": version_id,
                    "actor_subject": principal.subject,
                },
            )
        )
        .mappings()
        .one()
    )
    result = dict(approved)
    await _record_store_dna_event(
        session,
        principal,
        version_id,
        event_type="approved",
        from_status="submitted",
        to_status="approved",
        reason=note,
        payload={"geometry_attested": bool(result["geometry_attested"])},
    )
    return result


async def reject_store_dna(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
    *,
    reason: str,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text("""
                UPDATE planogram_store_dna_versions
                SET status='rejected',
                    rejected_by=:actor_subject,
                    rejected_at=CURRENT_TIMESTAMP,
                    rejection_reason=:reason,
                    updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=:tenant_id
                  AND id=:version_id
                  AND status='submitted'
                RETURNING
                    id, store_code, store_name, version_number, source, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, created_by, created_at, updated_at,
                    submitted_by, submitted_at, approved_by, approved_at,
                    rejected_by, rejected_at, rejection_reason,
                    supersedes_version_id
                """),
                {
                    "tenant_id": principal.tenant_id,
                    "version_id": version_id,
                    "actor_subject": principal.subject,
                    "reason": reason,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise StoreDnaStateError("submission_not_found_or_not_rejectable")

    result = dict(row)
    await _record_store_dna_event(
        session,
        principal,
        version_id,
        event_type="rejected",
        from_status="submitted",
        to_status="rejected",
        reason=reason,
    )
    return result


async def revise_store_dna(
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
                SELECT
                    id, store_code, store_name, status, configuration, summary,
                    configuration_sha256, geometry_attested
                FROM planogram_store_dna_versions
                WHERE tenant_id=:tenant_id AND id=:version_id
                """),
                {"tenant_id": principal.tenant_id, "version_id": version_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None or source["status"] not in {"rejected", "approved", "superseded"}:
        raise StoreDnaStateError("version_not_revisable")

    configuration = clone_configuration(dict(source["configuration"]))
    return await create_store_dna_draft(
        session,
        principal,
        store_code=str(source["store_code"]),
        store_name=source["store_name"],
        source="warehouse_revision",
        configuration=configuration,
        summary=dict(source["summary"]),
        configuration_sha256=configuration_fingerprint(configuration),
        geometry_attested=bool(source["geometry_attested"]),
        supersedes_version_id=source["id"],
        event_type="revised",
        event_reason=reason,
    )


async def get_approved_store_dna(
    session: AsyncSession,
    principal: Principal,
    store_code: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text("""
                SELECT
                    id, store_code, store_name, version_number, status,
                    configuration, summary, configuration_sha256,
                    geometry_attested, approved_by, approved_at
                FROM planogram_store_dna_versions
                WHERE tenant_id=:tenant_id
                  AND store_code=:store_code
                  AND status='approved'
                """),
                {"tenant_id": principal.tenant_id, "store_code": store_code},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None
