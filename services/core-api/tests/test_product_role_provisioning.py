from __future__ import annotations

import os
from uuid import UUID

import asyncpg
import pytest

from app.core.permission_catalog import (
    ACADEMY_ADMIN_PERMISSIONS,
    ACADEMY_INSTRUCTOR_PERMISSIONS,
    ACADEMY_LEARNER_PERMISSIONS,
    FIELD_MANAGER_PERMISSIONS,
    FIELD_WORKER_PERMISSIONS,
    PLANOGRAM_ADMIN_PERMISSIONS,
    PLANOGRAM_EDITOR_PERMISSIONS,
)

TENANT = UUID("22222222-2222-4222-8222-222222222248")
EXPECTED = {
    "academy_learner": set(ACADEMY_LEARNER_PERMISSIONS),
    "academy_instructor": set(ACADEMY_INSTRUCTOR_PERMISSIONS),
    "academy_admin": set(ACADEMY_ADMIN_PERMISSIONS),
    "field_worker": set(FIELD_WORKER_PERMISSIONS),
    "field_manager": set(FIELD_MANAGER_PERMISSIONS),
    "planogram_editor": set(PLANOGRAM_EDITOR_PERMISSIONS),
    "planogram_admin": set(PLANOGRAM_ADMIN_PERMISSIONS),
}


def _dsn() -> str:
    return os.environ["OPEX_MIGRATION_DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


@pytest.mark.asyncio
async def test_new_tenant_receives_canonical_product_roles_atomically() -> None:
    connection = await asyncpg.connect(_dsn())
    try:
        await connection.execute(
            "DELETE FROM tenants WHERE id=$1::uuid",
            TENANT,
        )
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO tenants(id,slug,display_name)
                VALUES($1::uuid,'product-role-provisioning','Product Role Provisioning')
                """,
                TENANT,
            )

            rows = await connection.fetch(
                """
                SELECT r.key, r.is_system, rp.permission_key
                FROM roles AS r
                LEFT JOIN role_permissions AS rp
                  ON rp.tenant_id=r.tenant_id AND rp.role_id=r.id
                WHERE r.tenant_id=$1::uuid
                  AND r.key = ANY($2::varchar[])
                ORDER BY r.key, rp.permission_key
                """,
                TENANT,
                list(EXPECTED),
            )

            grouped: dict[str, set[str]] = {}
            system_flags: dict[str, bool] = {}
            for row in rows:
                role_key = str(row["key"])
                system_flags[role_key] = bool(row["is_system"])
                if row["permission_key"] is not None:
                    grouped.setdefault(role_key, set()).add(str(row["permission_key"]))

            assert set(system_flags) == set(EXPECTED)
            assert all(system_flags.values())
            assert grouped == EXPECTED
    finally:
        await connection.close()
