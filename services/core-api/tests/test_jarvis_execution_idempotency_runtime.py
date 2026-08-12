from __future__ import annotations

import os
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.jarvis_execution_idempotency import (
    JarvisIdempotencyConflict,
    JarvisIdempotencyReplay,
    PostgresJarvisExecutionIdempotencyStore,
    actor_subject_sha256,
    idempotency_key_sha256,
)

pytestmark = pytest.mark.skipif(
    os.getenv("EAY_RUN_JARVIS_IDEMPOTENCY_DB_TEST") != "1",
    reason="Jarvis idempotency PostgreSQL integration is opt-in",
)

TENANT_A = UUID("00000000-0000-0000-0000-00000000a110")
TENANT_B = UUID("00000000-0000-0000-0000-00000000b110")
ACTOR = "sensitive-runtime-actor"
KEY = "request-20260812-runtime-0001"


async def set_tenant(connection, tenant_id: UUID) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def seed_tenant(connection, tenant_id: UUID, slug: str) -> None:
    await set_tenant(connection, tenant_id)
    await connection.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status)
            VALUES (:tenant_id, :slug, :slug, 'active')
            ON CONFLICT (id)
            DO UPDATE SET display_name = EXCLUDED.display_name,
                          status = 'active'
            """
        ),
        {"tenant_id": tenant_id, "slug": slug},
    )


async def delete_tenant(connection, tenant_id: UUID) -> None:
    await set_tenant(connection, tenant_id)
    await connection.execute(
        text("DELETE FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": tenant_id},
    )


@pytest.mark.asyncio
async def test_runtime_idempotency_is_durable_unique_and_tenant_isolated() -> None:
    settings = get_settings()
    migrator = create_async_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
    )
    runtime = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
    store = PostgresJarvisExecutionIdempotencyStore(runtime)

    try:
        async with migrator.begin() as connection:
            await seed_tenant(connection, TENANT_A, "jarvis-idemp-a")
            await seed_tenant(connection, TENANT_B, "jarvis-idemp-b")

        first = await store.reserve(
            tenant_id=TENANT_A,
            actor_subject=ACTOR,
            idempotency_key=KEY,
            request_fingerprint="a" * 64,
        )
        assert first.state == "reserved"

        with pytest.raises(JarvisIdempotencyReplay) as replay_info:
            await store.reserve(
                tenant_id=TENANT_A,
                actor_subject=ACTOR,
                idempotency_key=KEY,
                request_fingerprint="a" * 64,
            )
        assert replay_info.value.state == "reserved"

        with pytest.raises(JarvisIdempotencyConflict):
            await store.reserve(
                tenant_id=TENANT_A,
                actor_subject=ACTOR,
                idempotency_key=KEY,
                request_fingerprint="b" * 64,
            )

        dispatched = await store.transition(
            tenant_id=TENANT_A,
            actor_subject=ACTOR,
            idempotency_key=KEY,
            request_fingerprint="a" * 64,
            expected_state="reserved",
            new_state="dispatched",
        )
        assert dispatched.state == "dispatched"

        with pytest.raises(JarvisIdempotencyReplay) as dispatched_replay:
            await store.reserve(
                tenant_id=TENANT_A,
                actor_subject=ACTOR,
                idempotency_key=KEY,
                request_fingerprint="a" * 64,
            )
        assert dispatched_replay.value.state == "dispatched"

        tenant_b = await store.reserve(
            tenant_id=TENANT_B,
            actor_subject=ACTOR,
            idempotency_key=KEY,
            request_fingerprint="c" * 64,
        )
        assert tenant_b.state == "reserved"

        async with runtime.begin() as connection:
            await set_tenant(connection, TENANT_B)
            cross_tenant_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM jarvis_execution_idempotency
                    WHERE tenant_id = :tenant_a
                    """
                ),
                {"tenant_a": TENANT_A},
            )
        assert cross_tenant_count == 0

        async with migrator.begin() as connection:
            await set_tenant(connection, TENANT_A)
            stored = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT actor_subject_sha256,
                               idempotency_key_sha256,
                               request_fingerprint,
                               state
                        FROM jarvis_execution_idempotency
                        WHERE tenant_id = :tenant_id
                        """
                        ),
                        {"tenant_id": TENANT_A},
                    )
                )
                .mappings()
                .one()
            )

        assert stored["actor_subject_sha256"] == actor_subject_sha256(ACTOR)
        assert stored["idempotency_key_sha256"] == idempotency_key_sha256(KEY)
        assert stored["request_fingerprint"] == "a" * 64
        assert stored["state"] == "dispatched"
        assert ACTOR not in repr(stored)
        assert KEY not in repr(stored)

        releasable_key = "request-20260812-runtime-release"
        await store.reserve(
            tenant_id=TENANT_A,
            actor_subject=ACTOR,
            idempotency_key=releasable_key,
            request_fingerprint="d" * 64,
        )
        await store.release_reserved(
            tenant_id=TENANT_A,
            actor_subject=ACTOR,
            idempotency_key=releasable_key,
            request_fingerprint="d" * 64,
        )
        released_reuse = await store.reserve(
            tenant_id=TENANT_A,
            actor_subject=ACTOR,
            idempotency_key=releasable_key,
            request_fingerprint="e" * 64,
        )
        assert released_reuse.state == "reserved"

        expiring_key = "request-20260812-runtime-expired"
        await store.reserve(
            tenant_id=TENANT_A,
            actor_subject=ACTOR,
            idempotency_key=expiring_key,
            request_fingerprint="f" * 64,
        )
        async with migrator.begin() as connection:
            await set_tenant(connection, TENANT_A)
            await connection.execute(
                text(
                    """
                    UPDATE jarvis_execution_idempotency
                    SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                    WHERE tenant_id = :tenant_id
                      AND actor_subject_sha256 = :actor_sha
                      AND idempotency_key_sha256 = :key_sha
                    """
                ),
                {
                    "tenant_id": TENANT_A,
                    "actor_sha": actor_subject_sha256(ACTOR),
                    "key_sha": idempotency_key_sha256(expiring_key),
                },
            )
        recycled = await store.reserve(
            tenant_id=TENANT_A,
            actor_subject=ACTOR,
            idempotency_key=expiring_key,
            request_fingerprint="1" * 64,
        )
        assert recycled.request_fingerprint == "1" * 64
        assert recycled.state == "reserved"
    finally:
        try:
            async with migrator.begin() as connection:
                await delete_tenant(connection, TENANT_A)
                await delete_tenant(connection, TENANT_B)
        finally:
            await runtime.dispose()
            await migrator.dispose()
