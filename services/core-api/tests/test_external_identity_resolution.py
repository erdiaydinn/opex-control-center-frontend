"""External identity -> membership resolution security boundary."""

import inspect
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.resources import (
    resolve_external_identity_membership,
)

TENANT_A = UUID(
    "00000000-0000-0000-0000-00000000aa01"
)

TENANT_B = UUID(
    "00000000-0000-0000-0000-00000000bb01"
)

MEMBER_A1 = UUID(
    "00000000-0000-0000-0000-00000000aa11"
)

MEMBER_A2 = UUID(
    "00000000-0000-0000-0000-00000000aa12"
)

MEMBER_B1 = UUID(
    "00000000-0000-0000-0000-00000000bb11"
)

PROVIDER_A1 = UUID(
    "00000000-0000-0000-0000-00000000aa21"
)

PROVIDER_A2 = UUID(
    "00000000-0000-0000-0000-00000000aa22"
)

PROVIDER_B1 = UUID(
    "00000000-0000-0000-0000-00000000bb21"
)

SUBJECT = "CaseSensitive-Subject-001"


async def set_tenant(
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
        await set_tenant(
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


def test_identity_resolver_is_mapping_only() -> None:
    signature = inspect.signature(
        resolve_external_identity_membership
    )

    assert tuple(
        signature.parameters
    ) == (
        "tenant_id",
        "provider_id",
        "subject",
    )

    source = inspect.getsource(
        resolve_external_identity_membership
    )

    # Authentication resolves identity only.
    # Authorization belongs to resolve_membership_access().
    forbidden = (
        "membership_roles",
        "role_permissions",
        "permission_assignments",
        "roles AS",
        "external_subject",
        "email",
        "issuer",
    )

    for value in forbidden:
        assert value not in source


@pytest.mark.asyncio
async def test_external_identity_resolution_is_exact_and_fail_closed() -> None:
    settings = get_settings()

    admin_engine = create_async_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )

    try:
        async with admin_engine.begin() as connection:
            await cleanup(connection)

            for tenant_id, slug in (
                (
                    TENANT_A,
                    "external-identity-a",
                ),
                (
                    TENANT_B,
                    "external-identity-b",
                ),
            ):
                await set_tenant(
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

            for (
                tenant_id,
                membership_id,
                legacy_subject,
            ) in (
                (
                    TENANT_A,
                    MEMBER_A1,
                    "legacy-a1",
                ),
                (
                    TENANT_A,
                    MEMBER_A2,
                    "legacy-a2",
                ),
                (
                    TENANT_B,
                    MEMBER_B1,
                    "legacy-b1",
                ),
            ):
                await set_tenant(
                    connection,
                    tenant_id,
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
                            :legacy_subject,
                            'active'
                        )
                        """
                    ),
                    {
                        "membership_id":
                            membership_id,
                        "tenant_id":
                            tenant_id,
                        "legacy_subject":
                            legacy_subject,
                    },
                )

            for (
                tenant_id,
                provider_id,
                provider_key,
            ) in (
                (
                    TENANT_A,
                    PROVIDER_A1,
                    "provider-a1",
                ),
                (
                    TENANT_A,
                    PROVIDER_A2,
                    "provider-a2",
                ),
                (
                    TENANT_B,
                    PROVIDER_B1,
                    "provider-b1",
                ),
            ):
                await set_tenant(
                    connection,
                    tenant_id,
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO identity_providers (
                            id,
                            tenant_id,
                            provider_key,
                            protocol,
                            display_name,
                            status
                        )
                        VALUES (
                            :provider_id,
                            :tenant_id,
                            :provider_key,
                            'oidc',
                            :provider_key,
                            'active'
                        )
                        """
                    ),
                    {
                        "provider_id":
                            provider_id,
                        "tenant_id":
                            tenant_id,
                        "provider_key":
                            provider_key,
                    },
                )

            # Same external subject may exist at different
            # providers and map to different memberships.
            for (
                tenant_id,
                provider_id,
                membership_id,
            ) in (
                (
                    TENANT_A,
                    PROVIDER_A1,
                    MEMBER_A1,
                ),
                (
                    TENANT_A,
                    PROVIDER_A2,
                    MEMBER_A2,
                ),
                (
                    TENANT_B,
                    PROVIDER_B1,
                    MEMBER_B1,
                ),
            ):
                await set_tenant(
                    connection,
                    tenant_id,
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO external_identities (
                            tenant_id,
                            provider_id,
                            membership_id,
                            subject,
                            status
                        )
                        VALUES (
                            :tenant_id,
                            :provider_id,
                            :membership_id,
                            :subject,
                            'active'
                        )
                        """
                    ),
                    {
                        "tenant_id":
                            tenant_id,
                        "provider_id":
                            provider_id,
                        "membership_id":
                            membership_id,
                        "subject":
                            SUBJECT,
                    },
                )

        # Exact provider + exact subject.
        resolved_a1 = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_A),
                provider_id=str(PROVIDER_A1),
                subject=SUBJECT,
            )
        )

        assert resolved_a1 == str(
            MEMBER_A1
        )

        # Same subject, different provider, different account.
        resolved_a2 = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_A),
                provider_id=str(PROVIDER_A2),
                subject=SUBJECT,
            )
        )

        assert resolved_a2 == str(
            MEMBER_A2
        )

        # Same subject in another tenant remains isolated.
        resolved_b1 = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_B),
                provider_id=str(PROVIDER_B1),
                subject=SUBJECT,
            )
        )

        assert resolved_b1 == str(
            MEMBER_B1
        )

        # Provider from another tenant cannot be reused.
        cross_tenant_provider = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_A),
                provider_id=str(PROVIDER_B1),
                subject=SUBJECT,
            )
        )

        assert cross_tenant_provider is None

        # Subject identity is exact and case-sensitive.
        case_changed = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_A),
                provider_id=str(PROVIDER_A1),
                subject=SUBJECT.lower(),
            )
        )

        assert case_changed is None

        # Unknown subject fails closed.
        unknown_subject = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_A),
                provider_id=str(PROVIDER_A1),
                subject="unknown-subject",
            )
        )

        assert unknown_subject is None


        # Disabled external identity fails closed.
        async with admin_engine.begin() as connection:
            await set_tenant(
                connection,
                TENANT_A,
            )

            await connection.execute(
                text(
                    """
                    UPDATE external_identities
                    SET status = 'disabled'
                    WHERE tenant_id = :tenant_id
                      AND provider_id = :provider_id
                      AND subject = :subject
                    """
                ),
                {
                    "tenant_id":
                        TENANT_A,
                    "provider_id":
                        PROVIDER_A1,
                    "subject":
                        SUBJECT,
                },
            )

        disabled_identity = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_A),
                provider_id=str(PROVIDER_A1),
                subject=SUBJECT,
            )
        )

        assert disabled_identity is None


        # Restore identity, disable provider.
        async with admin_engine.begin() as connection:
            await set_tenant(
                connection,
                TENANT_A,
            )

            await connection.execute(
                text(
                    """
                    UPDATE external_identities
                    SET status = 'active'
                    WHERE tenant_id = :tenant_id
                      AND provider_id = :provider_id
                      AND subject = :subject
                    """
                ),
                {
                    "tenant_id":
                        TENANT_A,
                    "provider_id":
                        PROVIDER_A1,
                    "subject":
                        SUBJECT,
                },
            )

            await connection.execute(
                text(
                    """
                    UPDATE identity_providers
                    SET status = 'disabled'
                    WHERE tenant_id = :tenant_id
                      AND id = :provider_id
                    """
                ),
                {
                    "tenant_id":
                        TENANT_A,
                    "provider_id":
                        PROVIDER_A1,
                },
            )

        disabled_provider = (
            await resolve_external_identity_membership(
                tenant_id=str(TENANT_A),
                provider_id=str(PROVIDER_A1),
                subject=SUBJECT,
            )
        )

        assert disabled_provider is None

    finally:
        try:
            async with admin_engine.begin() as connection:
                await cleanup(
                    connection
                )
        finally:
            await admin_engine.dispose()
