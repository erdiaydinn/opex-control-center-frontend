"""Expand Academy locale storage and constraints.

Revision ID: 0011_academy_locale_expansion
Revises: 0010_academy_audit_idempotency
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_academy_locale_expansion"
down_revision: str | None = "0010_academy_audit_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPPORTED_LOCALES = (
    "tr",
    "en",
    "de",
    "ar",
    "fr",
    "es",
    "it",
    "nl",
    "pl",
    "pt-BR",
    "fa",
    "ru",
    "ro",
    "bs-Latn",
    "sq",
    "ka",
    "ku-Latn",
    "ckb",
    "bg",
    "hy",
    "zh-Hans",
    "sr-Latn",
    "mk",
    "id",
    "hu",
    "az",
    "uk",
    "el",
    "ms",
    "uz-Latn",
    "hi",
    "ur",
    "pt-PT",
    "ja",
    "ko",
    "cs",
    "sk",
    "sv",
    "da",
    "no",
    "fi",
    "he",
    "th",
    "vi",
    "bn",
    "ps",
)


def _locale_check_sql(column: str = "locale") -> str:
    values = ", ".join(f"'{locale}'" for locale in SUPPORTED_LOCALES)
    return f"{column} IN ({values})"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE academy_content_versions "
        "DROP CONSTRAINT ck_academy_content_version_locale"
    )
    op.execute(
        "ALTER TABLE academy_content_versions "
        "ALTER COLUMN locale TYPE varchar(16)"
    )
    op.execute(
        "ALTER TABLE academy_content_versions "
        "ADD CONSTRAINT ck_academy_content_version_locale "
        f"CHECK ({_locale_check_sql()})"
    )

    op.execute(
        "ALTER TABLE academy_document_chunks "
        "DROP CONSTRAINT ck_academy_chunk_locale"
    )
    op.execute(
        "ALTER TABLE academy_document_chunks "
        "ALTER COLUMN locale TYPE varchar(16)"
    )
    op.execute(
        "ALTER TABLE academy_document_chunks "
        "ADD CONSTRAINT ck_academy_chunk_locale "
        f"CHECK ({_locale_check_sql()})"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $guard$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM academy_content_versions
                WHERE locale NOT IN ('tr', 'en', 'de', 'ar')
            ) OR EXISTS (
                SELECT 1 FROM academy_document_chunks
                WHERE locale NOT IN ('tr', 'en', 'de', 'ar')
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade Academy locale expansion while expanded locales exist';
            END IF;
        END
        $guard$
        """
    )

    op.execute(
        "ALTER TABLE academy_document_chunks "
        "DROP CONSTRAINT ck_academy_chunk_locale"
    )
    op.execute(
        "ALTER TABLE academy_document_chunks "
        "ALTER COLUMN locale TYPE varchar(5)"
    )
    op.execute(
        "ALTER TABLE academy_document_chunks "
        "ADD CONSTRAINT ck_academy_chunk_locale "
        "CHECK (locale IN ('tr', 'en', 'de', 'ar'))"
    )

    op.execute(
        "ALTER TABLE academy_content_versions "
        "DROP CONSTRAINT ck_academy_content_version_locale"
    )
    op.execute(
        "ALTER TABLE academy_content_versions "
        "ALTER COLUMN locale TYPE varchar(5)"
    )
    op.execute(
        "ALTER TABLE academy_content_versions "
        "ADD CONSTRAINT ck_academy_content_version_locale "
        "CHECK (locale IN ('tr', 'en', 'de', 'ar'))"
    )
