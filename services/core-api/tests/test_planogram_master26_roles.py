from __future__ import annotations

import os

import asyncpg
import pytest

from app.core.permission_catalog import (
    PLANOGRAM_ADMIN_PERMISSIONS,
    PLANOGRAM_EDITOR_PERMISSIONS,
    SYSTEM_ROLE_PERMISSIONS,
)

TENANT_A = "11111111-1111-4111-8111-111111111111"


def _dsn(env_name: str) -> str:
    return os.environ[env_name].replace("postgresql+asyncpg://", "postgresql://", 1)


def test_planogram_system_role_contract_is_least_privilege() -> None:
    assert SYSTEM_ROLE_PERMISSIONS["planogram_editor"] == PLANOGRAM_EDITOR_PERMISSIONS
    assert SYSTEM_ROLE_PERMISSIONS["planogram_admin"] == PLANOGRAM_ADMIN_PERMISSIONS

    assert "action:planogram:edit" in PLANOGRAM_EDITOR_PERMISSIONS
    assert "action:planogram:approve" not in PLANOGRAM_EDITOR_PERMISSIONS
    assert "action:planogram:acceptFieldEvidence" not in PLANOGRAM_EDITOR_PERMISSIONS

    assert "action:planogram:approve" in PLANOGRAM_ADMIN_PERMISSIONS
    assert "action:planogram:acceptFieldEvidence" in PLANOGRAM_ADMIN_PERMISSIONS
    assert "module:planogram:admin" in PLANOGRAM_ADMIN_PERMISSIONS


@pytest.mark.asyncio
async def test_existing_tenant_role_seed_matches_catalog() -> None:
    connection = await asyncpg.connect(_dsn("OPEX_MIGRATION_DATABASE_URL"))
    try:
        await connection.execute(
            """
            INSERT INTO tenants (id, slug, display_name)
            VALUES ($1::uuid, 'master26-role-a', 'Master 26 Role A')
            ON CONFLICT (id) DO NOTHING
            """,
            TENANT_A,
        )
        # Migration 0036 seeds roles for tenants that exist at migration time.
        # CI applies migrations before this test, so the main acceptance fixture
        # is normally created by the PostgreSQL test. If another isolated test
        # created the tenant after migration, explicitly assert the catalog path
        # rather than silently fabricating a role row here.
        rows = await connection.fetch(
            """
            SELECT r.key, rp.permission_key
            FROM roles r
            JOIN role_permissions rp
              ON rp.tenant_id=r.tenant_id AND rp.role_id=r.id
            WHERE r.tenant_id=$1::uuid
              AND r.key IN ('planogram_editor','planogram_admin')
              AND r.is_system IS TRUE
            ORDER BY r.key, rp.permission_key
            """,
            TENANT_A,
        )
        grouped: dict[str, set[str]] = {}
        for row in rows:
            grouped.setdefault(str(row["key"]), set()).add(str(row["permission_key"]))
        assert grouped.get("planogram_editor") == set(PLANOGRAM_EDITOR_PERMISSIONS)
        assert grouped.get("planogram_admin") == set(PLANOGRAM_ADMIN_PERMISSIONS)
    finally:
        await connection.close()
