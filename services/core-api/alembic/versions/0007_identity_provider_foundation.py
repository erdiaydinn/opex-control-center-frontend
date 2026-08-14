"""Create provider-neutral enterprise identity foundation.

Revision ID: 0007_identity_foundation
Revises: 0006_system_role_integrity
Create Date: 2026-08-09

EXPAND migration.

Existing memberships.external_subject remains intact.
Authentication traffic is not moved by this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_identity_foundation"
down_revision: str | None = "0006_system_role_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UUID = postgresql.UUID(as_uuid=True)
TEXT_ARRAY = postgresql.ARRAY(sa.Text())

RUNTIME_ROLE = "opex_runtime"
BACKUP_ROLE = "opex_backup"

IDENTITY_TABLES = (
    "identity_providers",
    "oidc_provider_configs",
    "external_identities",
)


def _tenant_policy(table_name: str) -> None:
    op.execute(
        f'ALTER TABLE "{table_name}" '
        "ENABLE ROW LEVEL SECURITY"
    )

    op.execute(
        f'ALTER TABLE "{table_name}" '
        "FORCE ROW LEVEL SECURITY"
    )

    op.execute(
        f"""
        CREATE POLICY "{table_name}_tenant_isolation"
        ON "{table_name}"
        USING (
            tenant_id =
            NULLIF(
                current_setting(
                    'app.tenant_id',
                    true
                ),
                ''
            )::uuid
        )
        WITH CHECK (
            tenant_id =
            NULLIF(
                current_setting(
                    'app.tenant_id',
                    true
                ),
                ''
            )::uuid
        )
        """
    )


def upgrade() -> None:

    # ============================================================
    # Provider-neutral root
    # ============================================================

    op.create_table(
        "identity_providers",

        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=sa.text(
                "gen_random_uuid()"
            ),
        ),

        sa.Column(
            "tenant_id",
            UUID,
            sa.ForeignKey(
                "tenants.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),

        sa.Column(
            "provider_key",
            sa.String(length=80),
            nullable=False,
        ),

        sa.Column(
            "protocol",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "display_name",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="disabled",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
        ),

        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_identity_providers_tenant_id_id",
        ),

        sa.UniqueConstraint(
            "tenant_id",
            "provider_key",
            name="uq_identity_providers_tenant_key",
        ),

        sa.CheckConstraint(
            "protocol IN ('oidc')",
            name="ck_identity_providers_protocol",
        ),

        sa.CheckConstraint(
            "status IN ('disabled', 'active')",
            name="ck_identity_providers_status",
        ),

        sa.CheckConstraint(
            "provider_key ~ "
            "'^[a-z0-9][a-z0-9._-]{0,79}$'",
            name="ck_identity_providers_key_format",
        ),

        sa.CheckConstraint(
            "length(trim(display_name)) > 0",
            name="ck_identity_providers_display_name",
        ),
    )

    op.create_index(
        "ix_identity_providers_tenant_id",
        "identity_providers",
        ["tenant_id"],
    )


    # ============================================================
    # OIDC protocol configuration
    #
    # Secret material is never stored here.
    # credential_ref is only a reference into secret management.
    # ============================================================

    op.create_table(
        "oidc_provider_configs",

        sa.Column(
            "provider_id",
            UUID,
            primary_key=True,
        ),

        sa.Column(
            "tenant_id",
            UUID,
            nullable=False,
        ),

        sa.Column(
            "issuer",
            sa.String(length=2048),
            nullable=False,
        ),

        sa.Column(
            "client_id",
            sa.String(length=512),
            nullable=False,
        ),

        sa.Column(
            "audiences",
            TEXT_ARRAY,
            nullable=False,
        ),

        sa.Column(
            "scopes",
            TEXT_ARRAY,
            nullable=False,
            server_default=sa.text(
                "ARRAY['openid']::text[]"
            ),
        ),

        sa.Column(
            "allowed_algorithms",
            TEXT_ARRAY,
            nullable=False,
            server_default=sa.text(
                "ARRAY['RS256']::text[]"
            ),
        ),

        sa.Column(
            "token_endpoint_auth_method",
            sa.String(length=40),
            nullable=False,
            server_default="none",
        ),

        sa.Column(
            "credential_ref",
            sa.String(length=512),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
        ),

        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "provider_id",
            ],
            [
                "identity_providers.tenant_id",
                "identity_providers.id",
            ],
            ondelete="CASCADE",
            name=(
                "fk_oidc_provider_configs_"
                "provider_tenant"
            ),
        ),

        sa.UniqueConstraint(
            "tenant_id",
            "issuer",
            name=(
                "uq_oidc_provider_configs_"
                "tenant_issuer"
            ),
        ),

        # Commercial identity providers must use TLS.
        # Query strings and fragments are invalid as durable
        # issuer identifiers.
        sa.CheckConstraint(
            "issuer ~ '^https://[^?#]+$'",
            name="ck_oidc_provider_configs_https_issuer",
        ),

        sa.CheckConstraint(
            "length(trim(client_id)) > 0",
            name="ck_oidc_provider_configs_client_id",
        ),

        sa.CheckConstraint(
            "cardinality(audiences) > 0 "
            "AND array_position(audiences, '') IS NULL",
            name="ck_oidc_provider_configs_audiences",
        ),

        sa.CheckConstraint(
            "cardinality(scopes) > 0 "
            "AND 'openid' = ANY(scopes) "
            "AND array_position(scopes, '') IS NULL",
            name="ck_oidc_provider_configs_scopes",
        ),

        sa.CheckConstraint(
            "cardinality(allowed_algorithms) > 0 "
            "AND allowed_algorithms "
            "<@ ARRAY['RS256','ES256']::text[]",
            name=(
                "ck_oidc_provider_configs_"
                "algorithms"
            ),
        ),

        sa.CheckConstraint(
            "token_endpoint_auth_method IN ("
            "'none',"
            "'client_secret_basic',"
            "'private_key_jwt'"
            ")",
            name=(
                "ck_oidc_provider_configs_"
                "client_auth_method"
            ),
        ),

        sa.CheckConstraint(
            "("
            "token_endpoint_auth_method = 'none' "
            "AND credential_ref IS NULL"
            ") OR ("
            "token_endpoint_auth_method IN ("
            "'client_secret_basic',"
            "'private_key_jwt'"
            ") "
            "AND credential_ref IS NOT NULL "
            "AND length(trim(credential_ref)) > 0"
            ")",
            name=(
                "ck_oidc_provider_configs_"
                "credential_reference"
            ),
        ),
    )

    op.create_index(
        "ix_oidc_provider_configs_tenant_id",
        "oidc_provider_configs",
        ["tenant_id"],
    )


    # ============================================================
    # External identity -> internal membership mapping
    #
    # Stable identity is provider_id + subject.
    # Authorization consumes membership_id.
    # ============================================================

    op.create_table(
        "external_identities",

        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=sa.text(
                "gen_random_uuid()"
            ),
        ),

        sa.Column(
            "tenant_id",
            UUID,
            nullable=False,
        ),

        sa.Column(
            "provider_id",
            UUID,
            nullable=False,
        ),

        sa.Column(
            "membership_id",
            UUID,
            nullable=False,
        ),

        sa.Column(
            "subject",
            sa.String(length=512),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(
                "CURRENT_TIMESTAMP"
            ),
        ),

        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "provider_id",
            ],
            [
                "identity_providers.tenant_id",
                "identity_providers.id",
            ],
            ondelete="CASCADE",
            name=(
                "fk_external_identities_"
                "provider_tenant"
            ),
        ),

        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "membership_id",
            ],
            [
                "memberships.tenant_id",
                "memberships.id",
            ],
            ondelete="CASCADE",
            name=(
                "fk_external_identities_"
                "membership_tenant"
            ),
        ),

        # A verified subject from one provider maps to exactly
        # one OPEX membership.
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "subject",
            name=(
                "uq_external_identities_"
                "provider_subject"
            ),
        ),

        # Prevent silent account merging/re-linking.
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "membership_id",
            name=(
                "uq_external_identities_"
                "provider_membership"
            ),
        ),

        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=(
                "uq_external_identities_"
                "tenant_id_id"
            ),
        ),

        sa.CheckConstraint(
            "length(trim(subject)) > 0",
            name=(
                "ck_external_identities_"
                "subject_nonempty"
            ),
        ),

        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name=(
                "ck_external_identities_status"
            ),
        ),
    )

    op.create_index(
        "ix_external_identities_tenant_id",
        "external_identities",
        ["tenant_id"],
    )

    op.create_index(
        "ix_external_identities_membership",
        "external_identities",
        [
            "tenant_id",
            "membership_id",
        ],
    )


    # ============================================================
    # Tenant isolation
    # ============================================================

    for table_name in IDENTITY_TABLES:
        _tenant_policy(table_name)


    # ============================================================
    # Least privilege
    # ============================================================

    # Runtime may resolve identity, but cannot manage providers
    # or identity mappings yet.
    op.execute(
        "GRANT SELECT ON TABLE "
        + ", ".join(IDENTITY_TABLES)
        + f" TO {RUNTIME_ROLE}"
    )

    # Backup role is read-only and intentionally captures the
    # complete identity mapping/configuration metadata.
    op.execute(
        "GRANT SELECT ON TABLE "
        + ", ".join(IDENTITY_TABLES)
        + f" TO {BACKUP_ROLE}"
    )


def downgrade() -> None:

    op.execute(
        "REVOKE ALL PRIVILEGES ON TABLE "
        + ", ".join(IDENTITY_TABLES)
        + f" FROM {RUNTIME_ROLE}"
    )

    op.execute(
        "REVOKE ALL PRIVILEGES ON TABLE "
        + ", ".join(IDENTITY_TABLES)
        + f" FROM {BACKUP_ROLE}"
    )

    op.drop_index(
        "ix_external_identities_membership",
        table_name="external_identities",
    )

    op.drop_index(
        "ix_external_identities_tenant_id",
        table_name="external_identities",
    )

    op.drop_table(
        "external_identities"
    )

    op.drop_index(
        "ix_oidc_provider_configs_tenant_id",
        table_name="oidc_provider_configs",
    )

    op.drop_table(
        "oidc_provider_configs"
    )

    op.drop_index(
        "ix_identity_providers_tenant_id",
        table_name="identity_providers",
    )

    op.drop_table(
        "identity_providers"
    )
