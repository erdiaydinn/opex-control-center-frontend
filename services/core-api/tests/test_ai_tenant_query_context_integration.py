from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

import app.core.ai_tenant_query_context as query_store
from app.core.ai_tenant_query_context import (
    ABSENT_QUERY_CONTEXT_FINGERPRINT,
    AiTenantQueryContext,
    AiTenantQueryContextConflict,
    get_ai_tenant_query_context,
    put_ai_tenant_query_context,
)
from app.core.config import get_settings


async def set_tenant_context(connection, tenant_id: UUID) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def seed_tenant(
    connection,
    *,
    tenant_id: UUID,
    slug: str,
) -> None:
    await set_tenant_context(connection, tenant_id)
    await connection.execute(
        text(
            """
            INSERT INTO tenants (
                id,
                slug,
                display_name,
                status
            )
            VALUES (
                :tenant_id,
                :slug,
                :slug,
                'active'
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "slug": slug,
        },
    )


def context(
    entity_id: str,
    *,
    source_reference: str,
) -> AiTenantQueryContext:
    return AiTenantQueryContext(
        version=1,
        entity_ids=(entity_id,),
        source_reference=source_reference,
    )


@pytest.mark.asyncio
async def test_query_context_is_rls_bound_concurrency_safe_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    entity_a = f"TEST_ENTITY_{tenant_a.hex[:12].upper()}"
    entity_b = f"TEST_ENTITY_{tenant_b.hex[:12].upper()}"
    source_a = f"data-catalog:review:{tenant_a.hex}"
    source_b = f"data-catalog:review:{tenant_b.hex}"

    settings = get_settings()
    runtime_engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
    migration_engine = create_async_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
    )

    try:
        # Test-fixture setup is privileged on purpose. Runtime query-context
        # behavior below always uses the RLS-bound opex_runtime identity.
        async with migration_engine.begin() as connection:
            await seed_tenant(
                connection,
                tenant_id=tenant_a,
                slug=f"query-context-a-{tenant_a.hex}",
            )
            await seed_tenant(
                connection,
                tenant_id=tenant_b,
                slug=f"query-context-b-{tenant_b.hex}",
            )

        assert await get_ai_tenant_query_context(
            tenant_id=str(tenant_a)
        ) is None

        with pytest.raises(AiTenantQueryContextConflict):
            await put_ai_tenant_query_context(
                tenant_id=str(tenant_a),
                expected_record_fingerprint="a" * 64,
                context=context(
                    entity_a,
                    source_reference=source_a,
                ),
                actor_subject="admin-a",
                request_id="query-context-wrong-cas",
            )

        created_a = await put_ai_tenant_query_context(
            tenant_id=str(tenant_a),
            expected_record_fingerprint=(
                ABSENT_QUERY_CONTEXT_FINGERPRINT
            ),
            context=context(
                entity_a,
                source_reference=source_a,
            ),
            actor_subject="admin-a",
            request_id="query-context-create-a",
        )
        created_b = await put_ai_tenant_query_context(
            tenant_id=str(tenant_b),
            expected_record_fingerprint=(
                ABSENT_QUERY_CONTEXT_FINGERPRINT
            ),
            context=context(
                entity_b,
                source_reference=source_b,
            ),
            actor_subject="admin-b",
            request_id="query-context-create-b",
        )

        assert created_a.changed is True
        assert created_b.changed is True

        record_a = await get_ai_tenant_query_context(
            tenant_id=str(tenant_a)
        )
        record_b = await get_ai_tenant_query_context(
            tenant_id=str(tenant_b)
        )
        assert record_a is not None
        assert record_b is not None
        assert record_a.context.entity_ids == (entity_a,)
        assert record_b.context.entity_ids == (entity_b,)

        async with runtime_engine.begin() as connection:
            await set_tenant_context(connection, tenant_a)
            visible = (
                await connection.execute(
                    text(
                        """
                        SELECT tenant_id, entity_ids
                        FROM ai_tenant_query_contexts
                        ORDER BY tenant_id
                        """
                    )
                )
            ).mappings().all()

            audit = (
                await connection.execute(
                    text(
                        """
                        SELECT data
                        FROM audit_events
                        WHERE tenant_id = :tenant_id
                          AND action = 'ai_tenant_query_context_changed'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_a},
                )
            ).mappings().first()

        assert len(visible) == 1
        assert visible[0]["tenant_id"] == tenant_a
        assert visible[0]["entity_ids"] == [entity_a]

        assert audit is not None
        serialized_audit = json.dumps(
            audit["data"],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert entity_a not in serialized_audit
        assert source_a not in serialized_audit
        assert "source_reference_sha256" in serialized_audit
        assert "new_record_fingerprint" in serialized_audit

        with pytest.raises(AiTenantQueryContextConflict):
            await put_ai_tenant_query_context(
                tenant_id=str(tenant_a),
                expected_record_fingerprint=(
                    ABSENT_QUERY_CONTEXT_FINGERPRINT
                ),
                context=context(
                    entity_a,
                    source_reference=source_a,
                ),
                actor_subject="admin-a",
                request_id="query-context-stale",
            )

        no_op = await put_ai_tenant_query_context(
            tenant_id=str(tenant_a),
            expected_record_fingerprint=(
                record_a.record_fingerprint
            ),
            context=record_a.context,
            actor_subject="admin-a",
            request_id="query-context-noop",
        )
        assert no_op.changed is False

        async with runtime_engine.begin() as connection:
            await set_tenant_context(connection, tenant_a)
            no_op_audit_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM audit_events
                    WHERE tenant_id = :tenant_id
                      AND request_id = 'query-context-noop'
                    """
                ),
                {"tenant_id": tenant_a},
            )
        assert no_op_audit_count == 0

        async def fail_audit(*args, **kwargs) -> None:
            del args, kwargs
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr(
            query_store,
            "_write_query_context_audit_in_transaction",
            fail_audit,
        )

        changed_context = context(
            f"{entity_a}_NEXT",
            source_reference=f"{source_a}:next",
        )
        with pytest.raises(RuntimeError, match="audit unavailable"):
            await put_ai_tenant_query_context(
                tenant_id=str(tenant_a),
                expected_record_fingerprint=(
                    record_a.record_fingerprint
                ),
                context=changed_context,
                actor_subject="admin-a",
                request_id="query-context-audit-fail",
            )

        after_failure = await get_ai_tenant_query_context(
            tenant_id=str(tenant_a)
        )
        assert after_failure is not None
        assert after_failure.record_fingerprint == (
            record_a.record_fingerprint
        )
        assert after_failure.context == record_a.context

        # The runtime role intentionally has no DELETE on the authority table.
        async with runtime_engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await set_tenant_context(connection, tenant_a)
                with pytest.raises(DBAPIError):
                    await connection.execute(
                        text(
                            """
                            DELETE FROM ai_tenant_query_contexts
                            WHERE tenant_id = :tenant_id
                            """
                        ),
                        {"tenant_id": tenant_a},
                    )
            finally:
                await transaction.rollback()

    finally:
        await runtime_engine.dispose()
        await migration_engine.dispose()
