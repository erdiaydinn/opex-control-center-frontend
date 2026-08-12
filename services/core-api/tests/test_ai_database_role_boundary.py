"""Database-role separation rules for future AI SQL execution."""

import os

import asyncpg
import pytest
from sqlalchemy.engine import make_url


def _asyncpg_dsn(environment_name: str) -> str:
    value = os.environ[environment_name]

    url = make_url(value).set(
        drivername="postgresql"
    )

    # Credential remains in memory only; never log this value.
    return url.render_as_string(
        hide_password=False
    )


@pytest.mark.asyncio
async def test_runtime_role_cannot_assume_ai_reader() -> None:
    connection = await asyncpg.connect(
        _asyncpg_dsn("OPEX_DATABASE_URL")
    )

    try:
        current_user = await connection.fetchval(
            "SELECT current_user"
        )

        assert current_user == "opex_runtime"

        membership = await connection.fetchval(
            """
            SELECT pg_has_role(
                current_user,
                'opex_ai_reader',
                'MEMBER'
            )
            """
        )

        assert membership is False

        with pytest.raises(
            asyncpg.exceptions.InsufficientPrivilegeError
        ):
            await connection.execute(
                "SET ROLE opex_ai_reader"
            )

    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_ai_reader_is_fail_closed() -> None:
    connection = await asyncpg.connect(
        _asyncpg_dsn(
            "OPEX_MIGRATION_DATABASE_URL"
        )
    )

    try:
        role = await connection.fetchrow(
            """
            SELECT
                rolcanlogin,
                rolsuper,
                rolcreatedb,
                rolcreaterole,
                rolinherit,
                rolbypassrls
            FROM pg_roles
            WHERE rolname = 'opex_ai_reader'
            """
        )

        assert role is not None
        assert role["rolcanlogin"] is False
        assert role["rolsuper"] is False
        assert role["rolcreatedb"] is False
        assert role["rolcreaterole"] is False
        assert role["rolinherit"] is False
        assert role["rolbypassrls"] is False

        memberships = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM pg_auth_members m
            JOIN pg_roles granted
              ON granted.oid = m.roleid
            WHERE granted.rolname = 'opex_ai_reader'
            """
        )

        assert memberships == 0

        readable_tables = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM pg_class c
            JOIN pg_namespace n
              ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND has_table_privilege(
                    'opex_ai_reader',
                    c.oid,
                    'SELECT'
                  )
            """
        )

        assert readable_tables == 0

    finally:
        await connection.close()
