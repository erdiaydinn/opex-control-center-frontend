from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Mapping
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

pytestmark = pytest.mark.skipif(
    os.getenv("EAY_RUN_AUDIT_HASH_CHAIN_DB_TEST") != "1",
    reason="Audit hash-chain PostgreSQL integration is opt-in",
)

TENANT_A = UUID("00000000-0000-0000-0000-00000000a111")
TENANT_B = UUID("00000000-0000-0000-0000-00000000b111")
GENESIS_HASH = "0" * 64
PRESEEDED_A = ("audit-pre-a-1", "audit-pre-a-2")
PRESEEDED_B = ("audit-pre-b-1",)


async def set_tenant(connection: AsyncConnection, tenant_id: UUID) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def recompute_hash(row: Mapping[str, object]) -> str:
    material = (
        "eay-audit-chain-v1|"
        f"{row['chain_sequence']}|"
        f"{row['previous_event_hash']}|"
        f"{row['event_payload']}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def assert_valid_chain(rows: list[Mapping[str, object]]) -> None:
    assert rows
    previous_hash = GENESIS_HASH
    for expected_sequence, row in enumerate(rows, start=1):
        assert row["chain_sequence"] == expected_sequence
        assert row["previous_event_hash"] == previous_hash
        assert isinstance(row["event_payload"], str)
        assert row["event_hash"] == recompute_hash(row)
        previous_hash = str(row["event_hash"])


async def fetch_chain(engine, tenant_id: UUID) -> list[Mapping[str, object]]:
    async with engine.begin() as connection:
        await set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT chain_sequence,
                       previous_event_hash,
                       event_hash,
                       event_payload,
                       request_id,
                       resource_id
                FROM audit_events
                WHERE tenant_id = :tenant_id
                ORDER BY chain_sequence
                """
            ),
            {"tenant_id": tenant_id},
        )
        return list(result.mappings().all())


async def insert_runtime_event(
    engine,
    *,
    tenant_id: UUID,
    request_id: str,
    resource_id: str | None = None,
) -> Mapping[str, object]:
    async with engine.begin() as connection:
        await set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                INSERT INTO audit_events (
                    tenant_id,
                    actor_subject,
                    action,
                    resource_type,
                    resource_id,
                    decision,
                    request_id,
                    data
                ) VALUES (
                    :tenant_id,
                    'runtime-audit-actor',
                    'ai_tool_execution_authorized',
                    'ai_tool_execution',
                    :resource_id,
                    'allowed',
                    :request_id,
                    CAST(:data AS jsonb)
                )
                RETURNING chain_sequence,
                          previous_event_hash,
                          event_hash,
                          event_payload,
                          request_id,
                          resource_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "request_id": request_id,
                "data": '{"source":"runtime-test"}',
            },
        )
        return result.mappings().one()


@pytest.mark.asyncio
async def test_audit_chain_backfill_runtime_and_concurrency_are_tenant_safe() -> None:
    settings = get_settings()
    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)

    try:
        tenant_a_before = await fetch_chain(runtime, TENANT_A)
        tenant_b_before = await fetch_chain(runtime, TENANT_B)

        assert [row["request_id"] for row in tenant_a_before] == list(PRESEEDED_A)
        assert [row["request_id"] for row in tenant_b_before] == list(PRESEEDED_B)
        assert tenant_a_before[0]["resource_id"] is None
        assert tenant_b_before[0]["resource_id"] is None
        assert_valid_chain(tenant_a_before)
        assert_valid_chain(tenant_b_before)
        assert tenant_a_before[0]["previous_event_hash"] == GENESIS_HASH
        assert tenant_b_before[0]["previous_event_hash"] == GENESIS_HASH

        nullable_insert = await insert_runtime_event(
            runtime,
            tenant_id=TENANT_A,
            request_id="audit-runtime-null-resource",
            resource_id=None,
        )
        assert nullable_insert["resource_id"] is None
        assert nullable_insert["chain_sequence"] == 3
        assert nullable_insert["event_hash"] == recompute_hash(nullable_insert)

        concurrent = await asyncio.gather(
            *(
                insert_runtime_event(
                    runtime,
                    tenant_id=TENANT_A,
                    request_id=f"audit-concurrent-{index:02d}",
                    resource_id=f"execution-{index:02d}",
                )
                for index in range(8)
            )
        )
        sequences = sorted(int(row["chain_sequence"]) for row in concurrent)
        assert sequences == list(range(4, 12))

        tenant_a_after = await fetch_chain(runtime, TENANT_A)
        tenant_b_after = await fetch_chain(runtime, TENANT_B)
        assert len(tenant_a_after) == 11
        assert len(tenant_b_after) == 1
        assert_valid_chain(tenant_a_after)
        assert_valid_chain(tenant_b_after)

        async with runtime.begin() as connection:
            await set_tenant(connection, TENANT_B)
            cross_tenant_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM audit_events
                    WHERE tenant_id = :tenant_a
                    """
                ),
                {"tenant_a": TENANT_A},
            )
        assert cross_tenant_count == 0

        with pytest.raises(DBAPIError):
            async with runtime.begin() as connection:
                await set_tenant(connection, TENANT_A)
                await connection.execute(
                    text(
                        """
                        INSERT INTO audit_events (
                            tenant_id,
                            actor_subject,
                            action,
                            resource_type,
                            resource_id,
                            decision,
                            request_id,
                            data,
                            chain_sequence,
                            previous_event_hash,
                            event_hash,
                            event_payload
                        ) VALUES (
                            :tenant_id,
                            'tamper-actor',
                            'tamper_attempt',
                            'audit_event',
                            NULL,
                            'denied',
                            'audit-tamper-insert',
                            '{}'::jsonb,
                            999,
                            :fake_hash,
                            :fake_hash,
                            'forged'
                        )
                        """
                    ),
                    {"tenant_id": TENANT_A, "fake_hash": "f" * 64},
                )

        with pytest.raises(DBAPIError):
            async with runtime.begin() as connection:
                await set_tenant(connection, TENANT_A)
                await connection.execute(
                    text(
                        """
                        UPDATE audit_events
                        SET event_hash = :fake_hash
                        WHERE tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": TENANT_A, "fake_hash": "e" * 64},
                )

        with pytest.raises(DBAPIError):
            async with runtime.begin() as connection:
                await set_tenant(connection, TENANT_A)
                await connection.execute(
                    text(
                        """
                        DELETE FROM audit_events
                        WHERE tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": TENANT_A},
                )

        final_rows = await fetch_chain(runtime, TENANT_A)
        assert len(final_rows) == 11
        assert_valid_chain(final_rows)
    finally:
        await runtime.dispose()
