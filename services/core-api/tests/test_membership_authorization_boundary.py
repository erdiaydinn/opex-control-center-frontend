"""Durable membership-ID authorization boundary tests."""

import inspect
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.resources import resolve_membership_access

TENANT_A = UUID(
    "00000000-0000-0000-0000-000000009a01"
)

TENANT_B = UUID(
    "00000000-0000-0000-0000-000000009b01"
)

MEMBERSHIP_A = UUID(
    "00000000-0000-0000-0000-000000009a11"
)


async def set_tenant_context(
    connection,
    tenant_id: UUID,
) -> None:
    await connection.execute(
        text(
            """
            SELECT set_config(
                'app.tenant_id',
                :tenant_id,
                true
            )
            """
        ),
        {
            "tenant_id": str(tenant_id),
        },
    )


async def cleanup(
    connection,
) -> None:
    for tenant_id in (
        TENANT_A,
        TENANT_B,
    ):
        await set_tenant_context(
            connection,
            tenant_id,
        )

        await connection.execute(
            text(
                """
                DELETE FROM tenants
                WHERE id = :tenant_id
                """
            ),
            {
                "tenant_id": tenant_id,
            },
        )


def test_membership_authorization_api_has_no_external_identity_input() -> None:
    signature = inspect.signature(
        resolve_membership_access
    )

    assert tuple(
        signature.parameters
    ) == (
        "tenant_id",
        "membership_id",
    )

    source = inspect.getsource(
        resolve_membership_access
    )

    forbidden = (
        "external_subject",
        ":subject",
        "issuer",
        "provider_id",
        "email",
        "preferred_username",
    )

    for value in forbidden:
        assert value not in source


@pytest.mark.asyncio
async def test_membership_authorization_is_tenant_bound_and_fail_closed() -> None:
    settings = get_settings()

    admin_engine = create_async_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )

    try:
        async with admin_engine.begin() as connection:
            await cleanup(
                connection
            )

            for tenant_id, slug in (
                (
                    TENANT_A,
                    "membership-authz-a",
                ),
                (
                    TENANT_B,
                    "membership-authz-b",
                ),
            ):
                await set_tenant_context(
                    connection,
                    tenant_id,
                )

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

            await set_tenant_context(
                connection,
                TENANT_A,
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO memberships (
                        id,
                        tenant_id,
                        external_subject,
                        status
                    )
                    VALUES (
                        :membership_id,
                        :tenant_id,
                        'legacy-only-test-subject',
                        'active'
                    )
                    """
                ),
                {
                    "membership_id":
                        MEMBERSHIP_A,
                    "tenant_id":
                        TENANT_A,
                },
            )

        # Correct tenant + immutable membership ID resolves.
        result = await resolve_membership_access(
            tenant_id=str(TENANT_A),
            membership_id=str(MEMBERSHIP_A),
        )

        assert result is not None
        assert result[
            "tenant_status"
        ] == "active"

        assert result[
            "membership_status"
        ] == "active"

        assert result[
            "membership_id"
        ] == str(MEMBERSHIP_A)

        assert result["roles"] == ()
        assert (
            result[
                "permission_assignments"
            ]
            == ()
        )

        # Same internal membership UUID presented under another
        # tenant must never resolve.
        cross_tenant = (
            await resolve_membership_access(
                tenant_id=str(TENANT_B),
                membership_id=str(
                    MEMBERSHIP_A
                ),
            )
        )

        assert cross_tenant is not None
        assert cross_tenant[
            "tenant_status"
        ] == "active"

        assert cross_tenant[
            "membership_id"
        ] is None

        assert cross_tenant[
            "membership_status"
        ] is None

        assert cross_tenant["roles"] == ()

        assert (
            cross_tenant[
                "permission_assignments"
            ]
            == ()
        )

        # Unknown tenant also fails closed.
        missing_tenant = (
            await resolve_membership_access(
                tenant_id=(
                    "00000000-0000-0000-"
                    "0000-000000009c01"
                ),
                membership_id=str(
                    MEMBERSHIP_A
                ),
            )
        )

        assert missing_tenant is None

    finally:
        try:
            async with admin_engine.begin() as connection:
                await cleanup(
                    connection
                )
        finally:
            await admin_engine.dispose()
