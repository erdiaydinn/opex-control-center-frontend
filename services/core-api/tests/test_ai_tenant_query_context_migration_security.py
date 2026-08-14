from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_tenant_query_context_schema_is_force_rls_and_least_privilege() -> None:
    engine = create_async_engine(
        get_settings().migration_database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.connect() as connection:
            relation = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            relrowsecurity,
                            relforcerowsecurity
                        FROM pg_class
                        WHERE oid = 'ai_tenant_query_contexts'::regclass
                        """
                    )
                )
            ).mappings().one()

            fk_delete_action = await connection.scalar(
                text(
                    """
                    SELECT confdeltype
                    FROM pg_constraint
                    WHERE conrelid = 'ai_tenant_query_contexts'::regclass
                      AND confrelid = 'tenants'::regclass
                      AND contype = 'f'
                    """
                )
            )
            if isinstance(fk_delete_action, bytes):
                fk_delete_action = fk_delete_action.decode("ascii")

            privileges = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            has_table_privilege(
                                'opex_runtime',
                                'ai_tenant_query_contexts',
                                'SELECT'
                            ) AS can_select,
                            has_table_privilege(
                                'opex_runtime',
                                'ai_tenant_query_contexts',
                                'INSERT'
                            ) AS can_insert,
                            has_table_privilege(
                                'opex_runtime',
                                'ai_tenant_query_contexts',
                                'UPDATE'
                            ) AS can_update,
                            has_table_privilege(
                                'opex_runtime',
                                'ai_tenant_query_contexts',
                                'DELETE'
                            ) AS can_delete
                        """
                    )
                )
            ).mappings().one()

            policy = (
                await connection.execute(
                    text(
                        """
                        SELECT qual, with_check
                        FROM pg_policies
                        WHERE schemaname = 'public'
                          AND tablename = 'ai_tenant_query_contexts'
                          AND policyname = 'ai_tenant_query_context_isolation'
                        """
                    )
                )
            ).mappings().one()

        assert relation["relrowsecurity"] is True
        assert relation["relforcerowsecurity"] is True
        assert fk_delete_action == "r"
        assert privileges == {
            "can_select": True,
            "can_insert": True,
            "can_update": True,
            "can_delete": False,
        }
        assert "app.tenant_id" in str(policy["qual"])
        assert "app.tenant_id" in str(policy["with_check"])
    finally:
        await engine.dispose()
