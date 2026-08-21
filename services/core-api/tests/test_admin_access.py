from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.resources import update_tenant_member_access

TENANT_ID = UUID("00000000-0000-0000-0000-0000000000a1")


async def set_tenant_context(connection) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(TENANT_ID)},
    )


@pytest.mark.asyncio
async def test_last_active_super_admin_cannot_be_removed() -> None:
    engine = create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )

    membership_id = None

    try:
        async with engine.begin() as connection:
            await set_tenant_context(connection)

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
                        'admin-access-test',
                        'Admin Access Test',
                        'active'
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"tenant_id": TENANT_ID},
            )

            for key, name in (
                ("super_admin", "Super Admin"),
                ("viewer", "Viewer"),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO roles (
                            tenant_id,
                            key,
                            name,
                            is_system
                        )
                        VALUES (
                            :tenant_id,
                            :key,
                            :name,
                            true
                        )
                        ON CONFLICT (tenant_id, key)
                        DO UPDATE SET
                            name = EXCLUDED.name,
                            is_system = true
                        """
                    ),
                    {
                        "tenant_id": TENANT_ID,
                        "key": key,
                        "name": name,
                    },
                )

            membership_id = await connection.scalar(
                text(
                    """
                    INSERT INTO memberships (
                        tenant_id,
                        external_subject,
                        status
                    )
                    VALUES (
                        :tenant_id,
                        'last-super-admin-test',
                        'active'
                    )
                    ON CONFLICT (tenant_id, external_subject)
                    DO UPDATE SET status = 'active'
                    RETURNING id
                    """
                ),
                {"tenant_id": TENANT_ID},
            )

            await connection.execute(
                text(
                    """
                    DELETE FROM membership_roles
                    WHERE tenant_id = :tenant_id
                      AND membership_id = :membership_id
                    """
                ),
                {
                    "tenant_id": TENANT_ID,
                    "membership_id": membership_id,
                },
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO membership_roles (
                        tenant_id,
                        membership_id,
                        role_id
                    )
                    SELECT
                        :tenant_id,
                        :membership_id,
                        id
                    FROM roles
                    WHERE tenant_id = :tenant_id
                      AND key = 'super_admin'
                    """
                ),
                {
                    "tenant_id": TENANT_ID,
                    "membership_id": membership_id,
                },
            )

        with pytest.raises(
            ValueError,
            match="Cannot remove or suspend the last active super admin",
        ):
            await update_tenant_member_access(
                tenant_id=str(TENANT_ID),
                membership_id=str(membership_id),
                membership_status="active",
                roles=("viewer",),
            )

        async with engine.begin() as connection:
            await set_tenant_context(connection)

            status_value = await connection.scalar(
                text(
                    """
                    SELECT status
                    FROM memberships
                    WHERE tenant_id = :tenant_id
                      AND id = :membership_id
                    """
                ),
                {
                    "tenant_id": TENANT_ID,
                    "membership_id": membership_id,
                },
            )

            roles = (
                await connection.execute(
                    text(
                        """
                        SELECT r.key
                        FROM membership_roles AS mr
                        JOIN roles AS r
                          ON r.tenant_id = mr.tenant_id
                         AND r.id = mr.role_id
                        WHERE mr.tenant_id = :tenant_id
                          AND mr.membership_id = :membership_id
                        ORDER BY r.key
                        """
                    ),
                    {
                        "tenant_id": TENANT_ID,
                        "membership_id": membership_id,
                    },
                )
            ).scalars().all()

        assert status_value == "active"
        assert roles == ["super_admin"]

    finally:
        async with engine.begin() as connection:
            await set_tenant_context(connection)
            await connection.execute(
                text(
                    """
                    DELETE FROM tenants
                    WHERE id = :tenant_id
                    """
                ),
                {"tenant_id": TENANT_ID},
            )

        await engine.dispose()
