from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from app.core.resources import engine


async def _set_tenant(connection, tenant_id: str) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def _location_from_row(row) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "location_id": str(row.location_id),
        "region": str(row.region or "") or None,
        "active": bool(row.active),
    }


async def get_run_location(
    tenant_id: str,
    audit_run_id: UUID,
) -> dict[str, object] | None:
    """Resolve the DB-authoritative location of an Audit run inside one tenant."""

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT ar.location_id, fl.region, fl.active
                FROM audit_runs ar
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id
                 AND fl.location_id = ar.location_id
                WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                  AND ar.id = CAST(:audit_run_id AS UUID)
                """
            ),
            {
                "tenant_id": tenant_id,
                "audit_run_id": str(audit_run_id),
            },
        )
        return _location_from_row(result.first())


async def get_action_location(
    tenant_id: str,
    action_id: UUID,
) -> dict[str, object] | None:
    """Resolve the DB-authoritative location of an Audit action through its run."""

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT ar.location_id, fl.region, fl.active
                FROM audit_actions aa
                JOIN audit_runs ar
                  ON ar.tenant_id = aa.tenant_id
                 AND ar.id = aa.audit_run_id
                JOIN field_locations fl
                  ON fl.tenant_id = ar.tenant_id
                 AND fl.location_id = ar.location_id
                WHERE aa.tenant_id = CAST(:tenant_id AS UUID)
                  AND aa.id = CAST(:action_id AS UUID)
                """
            ),
            {
                "tenant_id": tenant_id,
                "action_id": str(action_id),
            },
        )
        return _location_from_row(result.first())
