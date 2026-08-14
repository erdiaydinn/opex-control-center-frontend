"""Narrow pre-auth tenant/provider resolver.

This migration creates a dedicated NOLOGIN SECURITY DEFINER owner.

The owner has BYPASSRLS because tenant resolution happens before a
tenant context exists. Its table privileges are deliberately limited
to the four relations required for pre-auth routing.

The function returns only an explicit OIDC routing allowlist.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_preauth_provider_resolver"
down_revision: str | None = "0007_identity_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RUNTIME_ROLE = "opex_runtime"
MIGRATOR_ROLE = "opex_migrator"
OWNER_ROLE = "opex_preauth_resolver_owner"

FUNCTION_SIGNATURE = (
    "public.resolve_preauth_oidc_providers(text)"
)


def upgrade() -> None:
    # Fail closed if an unexpected role already exists.
    # A pre-existing role could carry unknown memberships or grants.
    op.execute(
        f"""
        DO $role$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_catalog.pg_roles
                WHERE rolname = '{OWNER_ROLE}'
            ) THEN
                RAISE EXCEPTION
                    'Pre-auth resolver owner role already exists';
            END IF;

            CREATE ROLE {OWNER_ROLE}
                NOLOGIN
                NOSUPERUSER
                NOCREATEDB
                NOCREATEROLE
                NOINHERIT
                BYPASSRLS;
        END
        $role$
        """
    )

    # Exact relation scope only.
    op.execute(
        f"""
        GRANT USAGE
        ON SCHEMA public
        TO {OWNER_ROLE}
        """
    )

    op.execute(
        f"""
        GRANT SELECT
        ON TABLE
            public.tenants,
            public.tenant_domains,
            public.identity_providers,
            public.oidc_provider_configs
        TO {OWNER_ROLE}
        """
    )

    # Temporary membership is used only to transfer function
    # ownership. It is revoked before the migration completes.
    op.execute(
        f"""
        GRANT {OWNER_ROLE}
        TO {MIGRATOR_ROLE}
        """
    )

    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION
        public.resolve_preauth_oidc_providers(
            p_hostname text
        )
        RETURNS TABLE (
            tenant_id uuid,
            tenant_slug text,
            provider_id uuid,
            provider_key text,
            protocol text,
            provider_display_name text,
            issuer text,
            client_id text,
            audiences text[],
            scopes text[],
            allowed_algorithms text[]
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
            SELECT
                t.id AS tenant_id,
                t.slug::text AS tenant_slug,
                ip.id AS provider_id,
                ip.provider_key::text AS provider_key,
                ip.protocol::text AS protocol,
                ip.display_name::text AS provider_display_name,
                opc.issuer::text AS issuer,
                opc.client_id::text AS client_id,
                opc.audiences,
                opc.scopes,
                opc.allowed_algorithms
            FROM public.tenant_domains AS td
            JOIN public.tenants AS t
              ON t.id = td.tenant_id
            JOIN public.identity_providers AS ip
              ON ip.tenant_id = t.id
            JOIN public.oidc_provider_configs AS opc
              ON opc.tenant_id = ip.tenant_id
             AND opc.provider_id = ip.id
            WHERE p_hostname IS NOT NULL
              AND length(p_hostname) BETWEEN 1 AND 253
              AND p_hostname = lower(p_hostname)
              AND p_hostname = btrim(p_hostname)
              AND p_hostname NOT LIKE '.%'
              AND p_hostname NOT LIKE '%.'
              AND p_hostname NOT LIKE '%..%'
              AND p_hostname ~ '^[a-z0-9.-]+$'
              AND td.hostname = p_hostname
              AND td.verified_at IS NOT NULL
              AND t.status = 'active'
              AND ip.status = 'active'
              AND ip.protocol = 'oidc'
            ORDER BY ip.provider_key ASC
        $function$
        """
    )

    op.execute(
        f"""
        ALTER FUNCTION {FUNCTION_SIGNATURE}
        OWNER TO {OWNER_ROLE}
        """
    )

    # Remove PostgreSQL's default PUBLIC function access.
    op.execute(
        f"""
        REVOKE ALL
        ON FUNCTION {FUNCTION_SIGNATURE}
        FROM PUBLIC
        """
    )

    op.execute(
        f"""
        GRANT EXECUTE
        ON FUNCTION {FUNCTION_SIGNATURE}
        TO {RUNTIME_ROLE}
        """
    )

    # Do not leave the migration identity able to SET ROLE into
    # the BYPASSRLS owner after migration completion.
    op.execute(
        f"""
        REVOKE {OWNER_ROLE}
        FROM {MIGRATOR_ROLE}
        """
    )


def downgrade() -> None:
    # Temporarily regain ownership-management capability.
    op.execute(
        f"""
        GRANT {OWNER_ROLE}
        TO {MIGRATOR_ROLE}
        """
    )

    op.execute(
        f"""
        REVOKE ALL
        ON FUNCTION {FUNCTION_SIGNATURE}
        FROM {RUNTIME_ROLE}
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
        public.resolve_preauth_oidc_providers(text)
        """
    )

    op.execute(
        f"""
        REVOKE SELECT
        ON TABLE
            public.tenants,
            public.tenant_domains,
            public.identity_providers,
            public.oidc_provider_configs
        FROM {OWNER_ROLE}
        """
    )

    op.execute(
        f"""
        REVOKE USAGE
        ON SCHEMA public
        FROM {OWNER_ROLE}
        """
    )

    op.execute(
        f"""
        REVOKE {OWNER_ROLE}
        FROM {MIGRATOR_ROLE}
        """
    )

    op.execute(
        f"""
        DROP ROLE {OWNER_ROLE}
        """
    )
