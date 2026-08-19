from __future__ import annotations

import os
from uuid import uuid4

import asyncpg
import pytest

GENESIS_HASH = "0" * 64


def _integration_enabled() -> bool:
    return os.getenv("EAY_JARVIS_SECURITY_POSTGRES_INTEGRATION") == "1"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _integration_enabled(),
    reason="PostgreSQL Jarvis audit-chain acceptance is opt-in",
)
async def test_postgres_audit_chain_is_per_tenant_verifiable_and_append_only() -> None:
    connection = await asyncpg.connect(os.environ["EAY_TEST_MIGRATOR_DSN"])
    tenant_a = uuid4()
    tenant_b = uuid4()
    try:
        async def insert_event(tenant_id, sequence: int):
            event_id = uuid4()
            await connection.execute(
                """
                INSERT INTO public.audit_events(
                    id,
                    tenant_id,
                    actor_subject,
                    action,
                    resource_type,
                    resource_id,
                    decision,
                    request_id,
                    data,
                    created_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb,
                    clock_timestamp() + ($10::text || ' microseconds')::interval
                )
                """,
                event_id,
                tenant_id,
                "jarvis-security-test",
                "ai_tool_execution_authorized",
                "ai_tool",
                f"execution-{sequence}",
                "allow",
                f"request-{sequence}-{event_id}",
                '{"test":true}',
                sequence,
            )
            return event_id

        first_a = await insert_event(tenant_a, 1)
        second_a = await insert_event(tenant_a, 2)
        first_b = await insert_event(tenant_b, 3)

        rows_a = await connection.fetch(
            """
            SELECT id, chain_sequence, previous_event_hash, event_hash,
                   event_payload,
                   public.audit_event_hash_v1(
                       chain_sequence,
                       previous_event_hash,
                       event_payload
                   ) AS recomputed_hash
            FROM public.audit_events
            WHERE tenant_id = $1
            ORDER BY chain_sequence
            """,
            tenant_a,
        )
        rows_b = await connection.fetch(
            """
            SELECT id, chain_sequence, previous_event_hash, event_hash
            FROM public.audit_events
            WHERE tenant_id = $1
            ORDER BY chain_sequence
            """,
            tenant_b,
        )

        assert [row["id"] for row in rows_a] == [first_a, second_a]
        assert [row["chain_sequence"] for row in rows_a] == [1, 2]
        assert rows_a[0]["previous_event_hash"] == GENESIS_HASH
        assert rows_a[1]["previous_event_hash"] == rows_a[0]["event_hash"]
        assert all(
            row["event_hash"] == row["recomputed_hash"]
            for row in rows_a
        )

        assert [row["id"] for row in rows_b] == [first_b]
        assert rows_b[0]["chain_sequence"] == 1
        assert rows_b[0]["previous_event_hash"] == GENESIS_HASH

        with pytest.raises(asyncpg.PostgresError):
            await connection.execute(
                "UPDATE public.audit_events SET data = '{}'::jsonb WHERE id = $1",
                first_a,
            )

        with pytest.raises(asyncpg.PostgresError, match="server controlled"):
            await connection.execute(
                """
                INSERT INTO public.audit_events(
                    id, tenant_id, actor_subject, action, resource_type,
                    resource_id, decision, request_id, data, created_at,
                    chain_sequence, previous_event_hash, event_hash, event_payload
                )
                VALUES (
                    $1, $2, 'attacker', 'forge', 'audit', 'forged', 'allow',
                    'forged-request', '{}'::jsonb, clock_timestamp(),
                    999, $3, $3, '{}'
                )
                """,
                uuid4(),
                tenant_a,
                "f" * 64,
            )
    finally:
        await connection.close()
