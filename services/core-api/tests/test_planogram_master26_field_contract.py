from __future__ import annotations

import os

import asyncpg
import pytest

ADAPTER_KEY = "planogram.compliance_observation.v1"


def _dsn(env_name: str) -> str:
    return os.environ[env_name].replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.asyncio
async def test_field_promotion_schema_does_not_reject_compliance_adapter() -> None:
    connection = await asyncpg.connect(_dsn("OPEX_MIGRATION_DATABASE_URL"))
    try:
        rows = await connection.fetch(
            """
            SELECT conname, pg_get_constraintdef(oid) AS definition
            FROM pg_constraint
            WHERE conrelid='field_promotion_requests'::regclass
              AND contype='c'
            ORDER BY conname
            """
        )
        adapter_allowlists: list[str] = []
        for row in rows:
            definition = str(row["definition"])
            normalized = definition.lower()
            if "adapter_key" not in normalized:
                continue
            if " = any" in normalized or " in (" in normalized:
                adapter_allowlists.append(definition)
        for definition in adapter_allowlists:
            assert ADAPTER_KEY in definition, (
                "Field promotion adapter CHECK constraint rejects Master-26 adapter: "
                f"{definition}"
            )

        primary_key = await connection.fetchval(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid='field_promotion_requests'::regclass
              AND contype='p'
            """
        )
        assert primary_key is not None
        assert "tenant_id" in str(primary_key)
        assert "id" in str(primary_key)
    finally:
        await connection.close()
