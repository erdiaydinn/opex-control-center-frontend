"""Add tenant-scoped Academy localization policy.

Revision ID: 0012_academy_localization_policy
Revises: 0011_academy_locale_expansion
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_academy_localization_policy"
down_revision: str | None = "0011_academy_locale_expansion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"

SUPPORTED_LOCALES = (
    "tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR",
    "fa", "ru", "ro", "bs-Latn", "sq", "ka", "ku-Latn", "ckb", "bg",
    "hy", "zh-Hans", "sr-Latn", "mk", "id", "hu", "az", "uk", "el",
    "ms", "uz-Latn", "hi", "ur", "pt-PT", "ja", "ko", "cs", "sk", "sv",
    "da", "no", "fi", "he", "th", "vi", "bn", "ps",
)

CORE_RELEASE_LOCALES = ("tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR")


def _sql_array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar(16)[]"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE academy_localization_policies (
            tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            default_locale varchar(16) NOT NULL DEFAULT 'tr',
            enabled_locales varchar(16)[] NOT NULL DEFAULT {_sql_array(CORE_RELEASE_LOCALES)},
            revision bigint NOT NULL DEFAULT 1,
            updated_by varchar(255) NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_academy_localization_default_supported
                CHECK (default_locale = ANY ({_sql_array(SUPPORTED_LOCALES)})),
            CONSTRAINT ck_academy_localization_enabled_nonempty
                CHECK (cardinality(enabled_locales) > 0),
            CONSTRAINT ck_academy_localization_enabled_supported
                CHECK (enabled_locales <@ {_sql_array(SUPPORTED_LOCALES)}),
            CONSTRAINT ck_academy_localization_default_enabled
                CHECK (default_locale = ANY (enabled_locales)),
            CONSTRAINT ck_academy_localization_revision CHECK (revision > 0)
        )
        """
    )
    op.execute("ALTER TABLE academy_localization_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE academy_localization_policies FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY academy_localization_policies_tenant_isolation
        ON academy_localization_policies
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON TABLE academy_localization_policies TO {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS academy_localization_policies CASCADE")
