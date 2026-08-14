"""Permanent adversarial gate for provider-neutral identity foundation."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

TENANT_A = UUID("00000000-0000-0000-0000-000000008a01")
TENANT_B = UUID("00000000-0000-0000-0000-000000008b01")

MEMBER_A1 = UUID("00000000-0000-0000-0000-000000008a11")
MEMBER_A2 = UUID("00000000-0000-0000-0000-000000008a12")
MEMBER_B1 = UUID("00000000-0000-0000-0000-000000008b11")

PROVIDER_A1 = UUID("00000000-0000-0000-0000-000000008a21")
PROVIDER_A2 = UUID("00000000-0000-0000-0000-000000008a22")
PROVIDER_A3 = UUID("00000000-0000-0000-0000-000000008a23")
PROVIDER_A4 = UUID("00000000-0000-0000-0000-000000008a24")
PROVIDER_B1 = UUID("00000000-0000-0000-0000-000000008b21")

ISSUER = "https://identity.shared.example/oauth2/default"

IDENTITY_TABLES = (
    "identity_providers",
    "oidc_provider_configs",
    "external_identities",
)


async def _tenant(connection, tenant_id: UUID) -> None:
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
        {"tenant_id": str(tenant_id)},
    )


async def _cleanup(connection) -> None:
    for tenant_id in (TENANT_A, TENANT_B):
        await _tenant(connection, tenant_id)

        await connection.execute(
            text(
                """
                DELETE FROM tenants
                WHERE id = :tenant_id
                """
            ),
            {"tenant_id": tenant_id},
        )


async def _expect_integrity(
    connection,
    statement: str,
    params: dict,
) -> None:
    with pytest.raises(IntegrityError):
        async with connection.begin_nested():
            await connection.execute(
                text(statement),
                params,
            )


async def _runtime_write_must_fail(
    engine,
    statement: str,
    params: dict,
) -> None:
    async with engine.connect() as connection:
        transaction = await connection.begin()

        try:
            await _tenant(connection, TENANT_A)

            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(statement),
                    params,
                )
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_identity_foundation_adversarial_boundary() -> None:
    settings = get_settings()

    admin_engine = create_async_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )

    runtime_engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )

    try:
        # --------------------------------------------------------
        # Migration revision + fixture setup.
        # --------------------------------------------------------
        async with admin_engine.begin() as connection:
            revision = await connection.scalar(
                text(
                    """
                    SELECT version_num
                    FROM alembic_version
                    """
                )
            )

            assert revision is not None

            revision_prefix = str(
                revision
            ).split("_", 1)[0]

            assert revision_prefix.isdigit()
            assert int(revision_prefix) >= 7

            await _cleanup(connection)

            for tenant_id, slug in (
                (TENANT_A, "identity-ci-a"),
                (TENANT_B, "identity-ci-b"),
            ):
                await _tenant(connection, tenant_id)

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

            for tenant_id, membership_id, subject in (
                (TENANT_A, MEMBER_A1, "legacy-a1"),
                (TENANT_A, MEMBER_A2, "legacy-a2"),
                (TENANT_B, MEMBER_B1, "legacy-b1"),
            ):
                await _tenant(connection, tenant_id)

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
                            :subject,
                            'active'
                        )
                        """
                    ),
                    {
                        "membership_id": membership_id,
                        "tenant_id": tenant_id,
                        "subject": subject,
                    },
                )

            for tenant_id, provider_id, provider_key in (
                (TENANT_A, PROVIDER_A1, "okta-primary"),
                (TENANT_B, PROVIDER_B1, "okta-primary"),
            ):
                await _tenant(connection, tenant_id)

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
                        "provider_id": provider_id,
                        "tenant_id": tenant_id,
                        "provider_key": provider_key,
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO oidc_provider_configs (
                            provider_id,
                            tenant_id,
                            issuer,
                            client_id,
                            audiences,
                            scopes,
                            allowed_algorithms,
                            token_endpoint_auth_method
                        )
                        VALUES (
                            :provider_id,
                            :tenant_id,
                            :issuer,
                            'public-client',
                            ARRAY['opex-core-api']::text[],
                            ARRAY['openid']::text[],
                            ARRAY['RS256']::text[],
                            'none'
                        )
                        """
                    ),
                    {
                        "provider_id": provider_id,
                        "tenant_id": tenant_id,
                        "issuer": ISSUER,
                    },
                )

            for identity_id, tenant_id, provider_id, membership_id in (
                (
                    UUID("00000000-0000-0000-0000-000000008a31"),
                    TENANT_A,
                    PROVIDER_A1,
                    MEMBER_A1,
                ),
                (
                    UUID("00000000-0000-0000-0000-000000008b31"),
                    TENANT_B,
                    PROVIDER_B1,
                    MEMBER_B1,
                ),
            ):
                await _tenant(connection, tenant_id)

                await connection.execute(
                    text(
                        """
                        INSERT INTO external_identities (
                            id,
                            tenant_id,
                            provider_id,
                            membership_id,
                            subject,
                            status
                        )
                        VALUES (
                            :identity_id,
                            :tenant_id,
                            :provider_id,
                            :membership_id,
                            'shared-subject',
                            'active'
                        )
                        """
                    ),
                    {
                        "identity_id": identity_id,
                        "tenant_id": tenant_id,
                        "provider_id": provider_id,
                        "membership_id": membership_id,
                    },
                )

            # Same issuer and subject across different tenants
            # are intentionally legal.
            await _tenant(connection, TENANT_A)

            # Cross-tenant provider link must fail.
            await _expect_integrity(
                connection,
                """
                INSERT INTO external_identities (
                    tenant_id,
                    provider_id,
                    membership_id,
                    subject
                )
                VALUES (
                    :tenant_id,
                    :provider_id,
                    :membership_id,
                    'cross-tenant-attack'
                )
                """,
                {
                    "tenant_id": TENANT_A,
                    "provider_id": PROVIDER_B1,
                    "membership_id": MEMBER_A2,
                },
            )

            # Duplicate provider subject must fail.
            await _expect_integrity(
                connection,
                """
                INSERT INTO external_identities (
                    tenant_id,
                    provider_id,
                    membership_id,
                    subject
                )
                VALUES (
                    :tenant_id,
                    :provider_id,
                    :membership_id,
                    'shared-subject'
                )
                """,
                {
                    "tenant_id": TENANT_A,
                    "provider_id": PROVIDER_A1,
                    "membership_id": MEMBER_A2,
                },
            )

            # Create spare providers for configuration attacks.
            for provider_id, key in (
                (PROVIDER_A2, "duplicate-issuer"),
                (PROVIDER_A3, "http-issuer"),
                (PROVIDER_A4, "bad-algorithm"),
            ):
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
                            :key,
                            'oidc',
                            :key,
                            'active'
                        )
                        """
                    ),
                    {
                        "provider_id": provider_id,
                        "tenant_id": TENANT_A,
                        "key": key,
                    },
                )

            # Duplicate issuer in same tenant.
            await _expect_integrity(
                connection,
                """
                INSERT INTO oidc_provider_configs (
                    provider_id,
                    tenant_id,
                    issuer,
                    client_id,
                    audiences,
                    scopes,
                    allowed_algorithms,
                    token_endpoint_auth_method
                )
                VALUES (
                    :provider_id,
                    :tenant_id,
                    :issuer,
                    'duplicate',
                    ARRAY['opex-core-api']::text[],
                    ARRAY['openid']::text[],
                    ARRAY['RS256']::text[],
                    'none'
                )
                """,
                {
                    "provider_id": PROVIDER_A2,
                    "tenant_id": TENANT_A,
                    "issuer": ISSUER,
                },
            )

            # HTTP issuer.
            await _expect_integrity(
                connection,
                """
                INSERT INTO oidc_provider_configs (
                    provider_id,
                    tenant_id,
                    issuer,
                    client_id,
                    audiences,
                    scopes,
                    allowed_algorithms,
                    token_endpoint_auth_method
                )
                VALUES (
                    :provider_id,
                    :tenant_id,
                    'http://attacker.example',
                    'bad-http',
                    ARRAY['opex-core-api']::text[],
                    ARRAY['openid']::text[],
                    ARRAY['RS256']::text[],
                    'none'
                )
                """,
                {
                    "provider_id": PROVIDER_A3,
                    "tenant_id": TENANT_A,
                },
            )

            # Symmetric algorithm downgrade.
            await _expect_integrity(
                connection,
                """
                INSERT INTO oidc_provider_configs (
                    provider_id,
                    tenant_id,
                    issuer,
                    client_id,
                    audiences,
                    scopes,
                    allowed_algorithms,
                    token_endpoint_auth_method
                )
                VALUES (
                    :provider_id,
                    :tenant_id,
                    'https://identity-hs.example',
                    'bad-alg',
                    ARRAY['opex-core-api']::text[],
                    ARRAY['openid']::text[],
                    ARRAY['HS256']::text[],
                    'none'
                )
                """,
                {
                    "provider_id": PROVIDER_A4,
                    "tenant_id": TENANT_A,
                },
            )

            # RLS must be enabled AND forced.
            rls_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            c.relname,
                            c.relrowsecurity,
                            c.relforcerowsecurity
                        FROM pg_catalog.pg_class AS c
                        JOIN pg_catalog.pg_namespace AS n
                          ON n.oid = c.relnamespace
                        WHERE n.nspname = 'public'
                          AND c.relname IN (
                              'identity_providers',
                              'oidc_provider_configs',
                              'external_identities'
                          )
                        ORDER BY c.relname
                        """
                    )
                )
            ).all()

            assert len(rls_rows) == 3
            assert all(
                enabled and forced
                for _, enabled, forced in rls_rows
            )

            # Runtime and backup identities are SELECT-only.
            for role in ("opex_runtime", "opex_backup"):
                for table_name in IDENTITY_TABLES:
                    assert await connection.scalar(
                        text(
                            """
                            SELECT has_table_privilege(
                                :role,
                                :table_name,
                                'SELECT'
                            )
                            """
                        ),
                        {
                            "role": role,
                            "table_name": table_name,
                        },
                    )

                    for privilege in (
                        "INSERT",
                        "UPDATE",
                        "DELETE",
                        "TRUNCATE",
                    ):
                        assert not await connection.scalar(
                            text(
                                """
                                SELECT has_table_privilege(
                                    :role,
                                    :table_name,
                                    :privilege
                                )
                                """
                            ),
                            {
                                "role": role,
                                "table_name": table_name,
                                "privilege": privilege,
                            },
                        )

        # --------------------------------------------------------
        # Real runtime role: fail closed without tenant context.
        # --------------------------------------------------------
        async with runtime_engine.begin() as connection:
            count = int(
                await connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM identity_providers"
                    )
                )
                or 0
            )

            assert count == 0

        # Tenant A sees A only.
        async with runtime_engine.begin() as connection:
            await _tenant(connection, TENANT_A)

            tenants = (
                await connection.execute(
                    text(
                        """
                        SELECT DISTINCT tenant_id
                        FROM identity_providers
                        """
                    )
                )
            ).scalars().all()

            assert tenants == [TENANT_A]

        # Tenant B sees B only.
        async with runtime_engine.begin() as connection:
            await _tenant(connection, TENANT_B)

            tenants = (
                await connection.execute(
                    text(
                        """
                        SELECT DISTINCT tenant_id
                        FROM identity_providers
                        """
                    )
                )
            ).scalars().all()

            assert tenants == [TENANT_B]

        # Actual runtime mutations must be denied.
        await _runtime_write_must_fail(
            runtime_engine,
            """
            INSERT INTO identity_providers (
                tenant_id,
                provider_key,
                protocol,
                display_name,
                status
            )
            VALUES (
                :tenant_id,
                'runtime-attack',
                'oidc',
                'Runtime Attack',
                'active'
            )
            """,
            {"tenant_id": TENANT_A},
        )

        await _runtime_write_must_fail(
            runtime_engine,
            """
            UPDATE identity_providers
            SET display_name = 'ATTACKED'
            WHERE tenant_id = :tenant_id
            """,
            {"tenant_id": TENANT_A},
        )

        await _runtime_write_must_fail(
            runtime_engine,
            """
            DELETE FROM identity_providers
            WHERE tenant_id = :tenant_id
            """,
            {"tenant_id": TENANT_A},
        )

    finally:
        try:
            async with admin_engine.begin() as connection:
                await _cleanup(connection)
        finally:
            await runtime_engine.dispose()
            await admin_engine.dispose()
