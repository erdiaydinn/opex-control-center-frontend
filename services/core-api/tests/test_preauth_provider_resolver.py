"""Pre-auth OIDC provider resolver adversarial security boundary."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

FUNCTION = "public.resolve_preauth_oidc_providers(text)"
OWNER_ROLE = "opex_preauth_resolver_owner"
RUNTIME_ROLE = "opex_runtime"


def migration_database_url() -> str:
    value = os.environ.get(
        "OPEX_MIGRATION_DATABASE_URL",
        "",
    ).strip()

    if not value:
        raise RuntimeError(
            "OPEX_MIGRATION_DATABASE_URL is required"
        )

    return value


@pytest.mark.asyncio
async def test_preauth_resolver_catalog_privilege_boundary() -> None:
    engine = create_async_engine(
        migration_database_url(),
        pool_pre_ping=True,
        hide_parameters=True,
    )

    try:
        async with engine.connect() as connection:
            owner = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            oid,
                            rolcanlogin,
                            rolsuper,
                            rolcreatedb,
                            rolcreaterole,
                            rolinherit,
                            rolbypassrls
                        FROM pg_catalog.pg_roles
                        WHERE rolname = :role
                        """
                    ),
                    {
                        "role": OWNER_ROLE,
                    },
                )
            ).mappings().one()

            assert owner["rolcanlogin"] is False
            assert owner["rolsuper"] is False
            assert owner["rolcreatedb"] is False
            assert owner["rolcreaterole"] is False
            assert owner["rolinherit"] is False
            assert owner["rolbypassrls"] is True

            owner_oid = owner["oid"]

            function = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            p.oid,
                            p.proowner,
                            p.prosecdef,
                            p.provolatile::text AS provolatile,
                            p.proconfig
                        FROM pg_catalog.pg_proc AS p
                        WHERE p.oid =
                            CAST(
                                :signature
                                AS regprocedure
                            )::oid
                        """
                    ),
                    {
                        "signature": FUNCTION,
                    },
                )
            ).mappings().one()

            assert function["proowner"] == owner_oid
            assert function["prosecdef"] is True
            assert function["provolatile"] == "s"
            assert function["proconfig"] == [
                "search_path=pg_catalog"
            ]

            execute_grantees = {
                row["grantee"]
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT
                                CASE
                                    WHEN acl.grantee = 0
                                    THEN 'PUBLIC'
                                    ELSE r.rolname
                                END AS grantee
                            FROM pg_catalog.pg_proc AS p
                            CROSS JOIN LATERAL
                                pg_catalog.aclexplode(
                                    COALESCE(
                                        p.proacl,
                                        pg_catalog.acldefault(
                                            'f',
                                            p.proowner
                                        )
                                    )
                                ) AS acl
                            LEFT JOIN pg_catalog.pg_roles AS r
                              ON r.oid = acl.grantee
                            WHERE p.oid =
                                CAST(
                                    :signature
                                    AS regprocedure
                                )::oid
                              AND acl.privilege_type = 'EXECUTE'
                            """
                        ),
                        {
                            "signature": FUNCTION,
                        },
                    )
                ).mappings()
            }

            assert "PUBLIC" not in execute_grantees

            assert execute_grantees == {
                OWNER_ROLE,
                RUNTIME_ROLE,
            }

            membership_count = await connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM pg_catalog.pg_auth_members
                    WHERE roleid = :owner_oid
                       OR member = :owner_oid
                    """
                ),
                {
                    "owner_oid": owner_oid,
                },
            )

            assert membership_count == 0

            schema_usage = await connection.scalar(
                text(
                    """
                    SELECT pg_catalog.has_schema_privilege(
                        :role,
                        'public',
                        'USAGE'
                    )
                    """
                ),
                {
                    "role": OWNER_ROLE,
                },
            )

            schema_create = await connection.scalar(
                text(
                    """
                    SELECT pg_catalog.has_schema_privilege(
                        :role,
                        'public',
                        'CREATE'
                    )
                    """
                ),
                {
                    "role": OWNER_ROLE,
                },
            )

            assert schema_usage is True
            assert schema_create is False

            table_acls = {
                (
                    row["schema_name"],
                    row["relation_name"],
                    row["privilege_type"],
                )
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT
                                n.nspname AS schema_name,
                                c.relname AS relation_name,
                                acl.privilege_type
                            FROM pg_catalog.pg_class AS c
                            JOIN pg_catalog.pg_namespace AS n
                              ON n.oid = c.relnamespace
                            CROSS JOIN LATERAL
                                pg_catalog.aclexplode(
                                    c.relacl
                                ) AS acl
                            WHERE acl.grantee = :owner_oid
                            """
                        ),
                        {
                            "owner_oid": owner_oid,
                        },
                    )
                ).mappings()
            }

            assert table_acls == {
                (
                    "public",
                    "tenants",
                    "SELECT",
                ),
                (
                    "public",
                    "tenant_domains",
                    "SELECT",
                ),
                (
                    "public",
                    "identity_providers",
                    "SELECT",
                ),
                (
                    "public",
                    "oidc_provider_configs",
                    "SELECT",
                ),
            }

            owned_relation_count = await connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM pg_catalog.pg_class
                    WHERE relowner = :owner_oid
                    """
                ),
                {
                    "owner_oid": owner_oid,
                },
            )

            assert owned_relation_count == 0

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_preauth_resolver_runtime_is_exact_and_fail_closed() -> None:
    engine = create_async_engine(
        migration_database_url(),
        pool_pre_ping=True,
        hide_parameters=True,
    )

    tenant_a = uuid4()
    tenant_b = uuid4()

    domain_a = uuid4()
    domain_b = uuid4()

    provider_a = uuid4()
    provider_b = uuid4()

    suffix_a = tenant_a.hex[:12]
    suffix_b = tenant_b.hex[:12]

    slug_a = f"preauth-ci-{suffix_a}"
    slug_b = f"preauth-ci-{suffix_b}"

    hostname_a = (
        f"preauth-{suffix_a}.example.test"
    )
    hostname_b = (
        f"preauth-{suffix_b}.example.test"
    )

    issuer_a = (
        f"https://idp-{suffix_a}.example.test"
    )
    issuer_b = (
        f"https://idp-{suffix_b}.example.test"
    )

    expected_keys = {
        "tenant_id",
        "tenant_slug",
        "provider_id",
        "provider_key",
        "protocol",
        "provider_display_name",
        "issuer",
        "client_id",
        "audiences",
        "scopes",
        "allowed_algorithms",
    }

    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()

            try:
                await connection.execute(
                    text(
                        """
                        INSERT INTO public.tenants (
                            id,
                            slug,
                            display_name,
                            status
                        )
                        VALUES (
                            :tenant_id,
                            :slug,
                            :display_name,
                            'active'
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_a,
                        "slug": slug_a,
                        "display_name":
                            "Preauth CI Tenant A",
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO public.tenants (
                            id,
                            slug,
                            display_name,
                            status
                        )
                        VALUES (
                            :tenant_id,
                            :slug,
                            :display_name,
                            'active'
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_b,
                        "slug": slug_b,
                        "display_name":
                            "Preauth CI Tenant B",
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO public.tenant_domains (
                            id,
                            tenant_id,
                            hostname,
                            is_primary,
                            verified_at
                        )
                        VALUES (
                            :domain_id,
                            :tenant_id,
                            :hostname,
                            true,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "domain_id": domain_a,
                        "tenant_id": tenant_a,
                        "hostname": hostname_a,
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO public.tenant_domains (
                            id,
                            tenant_id,
                            hostname,
                            is_primary,
                            verified_at
                        )
                        VALUES (
                            :domain_id,
                            :tenant_id,
                            :hostname,
                            true,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "domain_id": domain_b,
                        "tenant_id": tenant_b,
                        "hostname": hostname_b,
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO public.identity_providers (
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
                            :display_name,
                            'active'
                        )
                        """
                    ),
                    {
                        "provider_id": provider_a,
                        "tenant_id": tenant_a,
                        "provider_key": "preauth-a",
                        "display_name": "Preauth A",
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO public.identity_providers (
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
                            :display_name,
                            'active'
                        )
                        """
                    ),
                    {
                        "provider_id": provider_b,
                        "tenant_id": tenant_b,
                        "provider_key": "preauth-b",
                        "display_name": "Preauth B",
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO public.oidc_provider_configs (
                            provider_id,
                            tenant_id,
                            issuer,
                            client_id,
                            audiences,
                            scopes,
                            allowed_algorithms,
                            token_endpoint_auth_method,
                            credential_ref
                        )
                        VALUES (
                            :provider_id,
                            :tenant_id,
                            :issuer,
                            'preauth-client-a',
                            ARRAY['preauth-client-a']::text[],
                            ARRAY['openid','profile']::text[],
                            ARRAY['RS256']::text[],
                            'client_secret_basic',
                            'CI-CANARY-MUST-NOT-LEAK'
                        )
                        """
                    ),
                    {
                        "provider_id": provider_a,
                        "tenant_id": tenant_a,
                        "issuer": issuer_a,
                    },
                )

                await connection.execute(
                    text(
                        """
                        INSERT INTO public.oidc_provider_configs (
                            provider_id,
                            tenant_id,
                            issuer,
                            client_id,
                            audiences,
                            scopes,
                            allowed_algorithms,
                            token_endpoint_auth_method,
                            credential_ref
                        )
                        VALUES (
                            :provider_id,
                            :tenant_id,
                            :issuer,
                            'preauth-client-b',
                            ARRAY['preauth-client-b']::text[],
                            ARRAY['openid']::text[],
                            ARRAY['ES256']::text[],
                            'none',
                            NULL
                        )
                        """
                    ),
                    {
                        "provider_id": provider_b,
                        "tenant_id": tenant_b,
                        "issuer": issuer_b,
                    },
                )

                # No tenant context exists. Direct runtime SELECT
                # must therefore remain blocked by forced RLS.
                await connection.execute(
                    text(
                        "SET LOCAL ROLE opex_runtime"
                    )
                )

                direct_count = await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM public.tenant_domains
                        WHERE hostname = :hostname
                        """
                    ),
                    {
                        "hostname": hostname_a,
                    },
                )

                assert direct_count == 0

                result = (
                    await connection.execute(
                        text(
                            """
                            SELECT *
                            FROM public.resolve_preauth_oidc_providers(
                                :hostname
                            )
                            """
                        ),
                        {
                            "hostname": hostname_a,
                        },
                    )
                ).mappings().all()

                assert len(result) == 1

                payload = dict(result[0])

                assert set(payload) == expected_keys
                assert payload["tenant_id"] == tenant_a
                assert payload["tenant_slug"] == slug_a
                assert payload["provider_id"] == provider_a
                assert payload["provider_key"] == "preauth-a"
                assert payload["protocol"] == "oidc"
                assert payload["issuer"] == issuer_a

                serialized = repr(payload)

                assert (
                    "CI-CANARY-MUST-NOT-LEAK"
                    not in serialized
                )
                assert "credential_ref" not in payload
                assert (
                    "token_endpoint_auth_method"
                    not in payload
                )
                assert "email" not in payload
                assert "subject" not in payload
                assert "roles" not in payload
                assert "permissions" not in payload

                # Exact host B must resolve only tenant B.
                result_b = (
                    await connection.execute(
                        text(
                            """
                            SELECT *
                            FROM public.resolve_preauth_oidc_providers(
                                :hostname
                            )
                            """
                        ),
                        {
                            "hostname": hostname_b,
                        },
                    )
                ).mappings().all()

                assert len(result_b) == 1
                assert result_b[0]["tenant_id"] == tenant_b
                assert result_b[0]["provider_id"] == provider_b

                for hostile_hostname in (
                    "unknown.example.test",
                    hostname_a.upper(),
                    f"{hostname_a}.",
                    f" {hostname_a}",
                    "preauth-a..example.test",
                    "x' OR '1'='1",
                ):
                    hostile_count = await connection.scalar(
                        text(
                            """
                            SELECT count(*)
                            FROM public.resolve_preauth_oidc_providers(
                                :hostname
                            )
                            """
                        ),
                        {
                            "hostname":
                                hostile_hostname,
                        },
                    )

                    assert hostile_count == 0

                await connection.execute(
                    text("RESET ROLE")
                )

                # Unverified domain must disappear.
                await connection.execute(
                    text(
                        """
                        UPDATE public.tenant_domains
                        SET verified_at = NULL
                        WHERE id = :domain_id
                        """
                    ),
                    {
                        "domain_id": domain_a,
                    },
                )

                await connection.execute(
                    text(
                        "SET LOCAL ROLE opex_runtime"
                    )
                )

                count = await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM public.resolve_preauth_oidc_providers(
                            :hostname
                        )
                        """
                    ),
                    {
                        "hostname": hostname_a,
                    },
                )

                assert count == 0

                await connection.execute(
                    text("RESET ROLE")
                )

                # Suspended tenant must disappear.
                await connection.execute(
                    text(
                        """
                        UPDATE public.tenant_domains
                        SET verified_at = CURRENT_TIMESTAMP
                        WHERE id = :domain_id
                        """
                    ),
                    {
                        "domain_id": domain_a,
                    },
                )

                await connection.execute(
                    text(
                        """
                        UPDATE public.tenants
                        SET status = 'suspended'
                        WHERE id = :tenant_id
                        """
                    ),
                    {
                        "tenant_id": tenant_a,
                    },
                )

                await connection.execute(
                    text(
                        "SET LOCAL ROLE opex_runtime"
                    )
                )

                count = await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM public.resolve_preauth_oidc_providers(
                            :hostname
                        )
                        """
                    ),
                    {
                        "hostname": hostname_a,
                    },
                )

                assert count == 0

                await connection.execute(
                    text("RESET ROLE")
                )

                # Disabled provider must disappear.
                await connection.execute(
                    text(
                        """
                        UPDATE public.tenants
                        SET status = 'active'
                        WHERE id = :tenant_id
                        """
                    ),
                    {
                        "tenant_id": tenant_a,
                    },
                )

                await connection.execute(
                    text(
                        """
                        UPDATE public.identity_providers
                        SET status = 'disabled'
                        WHERE id = :provider_id
                        """
                    ),
                    {
                        "provider_id": provider_a,
                    },
                )

                await connection.execute(
                    text(
                        "SET LOCAL ROLE opex_runtime"
                    )
                )

                count = await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM public.resolve_preauth_oidc_providers(
                            :hostname
                        )
                        """
                    ),
                    {
                        "hostname": hostname_a,
                    },
                )

                assert count == 0

            finally:
                await transaction.rollback()

    finally:
        await engine.dispose()
