from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.resources import engine

from .repository import AuditConflictError, AuditRepositoryError
from .schemas import AuditLocationManagerAssignmentCreate


async def _set_tenant(connection: AsyncConnection, tenant_id: str) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def _dict(row) -> dict[str, object]:
    return dict(row._mapping)


async def resolve_location_manager_subject(
    connection: AsyncConnection,
    *,
    tenant_id: str,
    location_id: str,
) -> str | None:
    """Resolve only an active member that still holds the canonical Audit Manager role."""

    result = await connection.execute(
        text(
            """
            SELECT m.external_subject
            FROM audit_location_manager_assignments a
            JOIN memberships m
              ON m.tenant_id = a.tenant_id
             AND m.id = a.manager_membership_id
             AND m.status = 'active'
            JOIN membership_roles mr
              ON mr.tenant_id = m.tenant_id
             AND mr.membership_id = m.id
            JOIN roles r
              ON r.tenant_id = mr.tenant_id
             AND r.id = mr.role_id
             AND r.key = 'audit_manager'
             AND r.is_system IS TRUE
            WHERE a.tenant_id = CAST(:tenant_id AS UUID)
              AND a.location_id = :location_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "location_id": location_id},
    )
    row = result.first()
    return str(row.external_subject) if row else None


async def get_location_manager_assignment(
    tenant_id: str,
    location_id: str,
) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT a.location_id, a.manager_membership_id, a.source_ref,
                       a.version, a.updated_by, a.updated_at,
                       m.external_subject AS manager_subject,
                       m.email AS manager_email,
                       m.display_name AS manager_display_name,
                       m.status AS manager_membership_status,
                       EXISTS (
                         SELECT 1
                         FROM membership_roles mr
                         JOIN roles r
                           ON r.tenant_id = mr.tenant_id AND r.id = mr.role_id
                         WHERE mr.tenant_id = a.tenant_id
                           AND mr.membership_id = a.manager_membership_id
                           AND r.key = 'audit_manager'
                           AND r.is_system IS TRUE
                       ) AS has_audit_manager_role
                FROM audit_location_manager_assignments a
                JOIN memberships m
                  ON m.tenant_id = a.tenant_id AND m.id = a.manager_membership_id
                WHERE a.tenant_id = CAST(:tenant_id AS UUID)
                  AND a.location_id = :location_id
                """
            ),
            {"tenant_id": tenant_id, "location_id": location_id},
        )
        row = result.first()
        return _dict(row) if row else None


async def list_location_manager_assignments(
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
                SELECT a.location_id, fl.name AS location_name, fl.region,
                       a.manager_membership_id, m.external_subject AS manager_subject,
                       m.email AS manager_email, m.display_name AS manager_display_name,
                       m.status AS manager_membership_status,
                       a.source_ref, a.version, a.updated_by, a.updated_at,
                       EXISTS (
                         SELECT 1
                         FROM membership_roles mr
                         JOIN roles r
                           ON r.tenant_id = mr.tenant_id AND r.id = mr.role_id
                         WHERE mr.tenant_id = a.tenant_id
                           AND mr.membership_id = a.manager_membership_id
                           AND r.key = 'audit_manager'
                           AND r.is_system IS TRUE
                       ) AS has_audit_manager_role
                FROM audit_location_manager_assignments a
                JOIN field_locations fl
                  ON fl.tenant_id = a.tenant_id AND fl.location_id = a.location_id
                JOIN memberships m
                  ON m.tenant_id = a.tenant_id AND m.id = a.manager_membership_id
                WHERE a.tenant_id = CAST(:tenant_id AS UUID)
                  AND (
                    :unrestricted
                    OR a.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
                    OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
                  )
                ORDER BY COALESCE(fl.region, ''), fl.name, a.location_id
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


async def assign_location_manager(
    tenant_id: str,
    actor_subject: str,
    location_id: str,
    payload: AuditLocationManagerAssignmentCreate,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
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
            {"tenant_id": tenant_id, "location_id": location_id},
        )
        if not location.first():
            raise AuditRepositoryError("audit location is not active")

        manager = await connection.execute(
            text(
                """
                SELECT m.external_subject
                FROM memberships m
                JOIN membership_roles mr
                  ON mr.tenant_id = m.tenant_id AND mr.membership_id = m.id
                JOIN roles r
                  ON r.tenant_id = mr.tenant_id AND r.id = mr.role_id
                WHERE m.tenant_id = CAST(:tenant_id AS UUID)
                  AND m.id = CAST(:membership_id AS UUID)
                  AND m.status = 'active'
                  AND r.key = 'audit_manager'
                  AND r.is_system IS TRUE
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "membership_id": str(payload.manager_membership_id),
            },
        )
        if not manager.first():
            raise AuditRepositoryError(
                "assigned manager must be an active membership with audit_manager role"
            )

        current = await connection.execute(
            text(
                """
                SELECT version
                FROM audit_location_manager_assignments
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND location_id = :location_id
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "location_id": location_id},
        )
        current_row = current.first()
        if current_row is None and payload.expected_version is not None:
            raise AuditConflictError("manager assignment does not exist")
        if current_row is not None and payload.expected_version is None:
            raise AuditConflictError(
                "existing manager assignment requires expected_version"
            )
        if (
            current_row is not None
            and current_row.version != payload.expected_version
        ):
            raise AuditConflictError("manager assignment version conflict")

        if current_row is None:
            result = await connection.execute(
                text(
                    """
                    INSERT INTO audit_location_manager_assignments (
                        tenant_id, location_id, manager_membership_id,
                        source_ref, updated_by
                    ) VALUES (
                        CAST(:tenant_id AS UUID), :location_id,
                        CAST(:manager_membership_id AS UUID), :source_ref, :updated_by
                    )
                    RETURNING location_id, manager_membership_id, source_ref,
                              version, updated_by, updated_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "location_id": location_id,
                    "manager_membership_id": str(payload.manager_membership_id),
                    "source_ref": payload.source_ref,
                    "updated_by": actor_subject,
                },
            )
        else:
            result = await connection.execute(
                text(
                    """
                    UPDATE audit_location_manager_assignments
                    SET manager_membership_id = CAST(:manager_membership_id AS UUID),
                        source_ref = :source_ref,
                        version = version + 1,
                        updated_by = :updated_by,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                      AND location_id = :location_id
                      AND version = :expected_version
                    RETURNING location_id, manager_membership_id, source_ref,
                              version, updated_by, updated_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "location_id": location_id,
                    "manager_membership_id": str(payload.manager_membership_id),
                    "source_ref": payload.source_ref,
                    "updated_by": actor_subject,
                    "expected_version": payload.expected_version,
                },
            )
        row = result.first()
        if not row:
            raise AuditConflictError("manager assignment changed concurrently")
        return _dict(row)