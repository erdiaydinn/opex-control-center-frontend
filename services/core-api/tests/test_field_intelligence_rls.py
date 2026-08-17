from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

TENANT_A = UUID("00000000-0000-0000-0000-00000000f101")
TENANT_B = UUID("00000000-0000-0000-0000-00000000f102")


async def set_tenant_context(connection: AsyncConnection, tenant_id: UUID) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def seed_tenant(
    connection: AsyncConnection,
    tenant_id: UUID,
    slug: str,
) -> None:
    await set_tenant_context(connection, tenant_id)
    await connection.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name)
            VALUES (:tenant_id, :slug, :display_name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "tenant_id": tenant_id,
            "slug": slug,
            "display_name": slug,
        },
    )


@pytest.mark.asyncio
async def test_field_locations_rls_blocks_cross_tenant_reads_and_writes() -> None:
    engine = create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as connection:
            await seed_tenant(connection, TENANT_A, "field-tenant-a")
            await connection.execute(
                text(
                    """
                    INSERT INTO field_locations (
                        tenant_id,
                        location_id,
                        name,
                        active
                    ) VALUES (
                        :tenant_id,
                        'A-STORE-001',
                        'Tenant A Store',
                        TRUE
                    )
                    ON CONFLICT (tenant_id, location_id) DO NOTHING
                    """
                ),
                {"tenant_id": TENANT_A},
            )

        async with engine.begin() as connection:
            await seed_tenant(connection, TENANT_B, "field-tenant-b")

        async with engine.begin() as connection:
            await set_tenant_context(connection, TENANT_A)
            tenant_a_count = await connection.scalar(
                text("SELECT count(*) FROM field_locations")
            )

        async with engine.begin() as connection:
            await set_tenant_context(connection, TENANT_B)
            tenant_b_count = await connection.scalar(
                text("SELECT count(*) FROM field_locations")
            )

        async with engine.begin() as connection:
            no_context_count = await connection.scalar(
                text("SELECT count(*) FROM field_locations")
            )

        assert tenant_a_count == 1
        assert tenant_b_count == 0
        assert no_context_count == 0

        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await set_tenant_context(connection, TENANT_B)
                await connection.execute(
                    text(
                        """
                        INSERT INTO field_locations (
                            tenant_id,
                            location_id,
                            name,
                            active
                        ) VALUES (
                            :tenant_id,
                            'CROSS-TENANT-WRITE',
                            'Must Be Rejected',
                            TRUE
                        )
                        """
                    ),
                    {"tenant_id": TENANT_A},
                )
    finally:
        await engine.dispose()
