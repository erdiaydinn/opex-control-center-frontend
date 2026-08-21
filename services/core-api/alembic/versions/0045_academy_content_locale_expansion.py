"""Expand Academy content/evidence locale persistence.

Revision ID: 0045_academy_content_locale_expansion
Revises: 0044_external_acceptance_evidence
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045_academy_content_locale_expansion"
down_revision: str | None = "0044_external_acceptance_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONTENT_LOCALES = (
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


def _locale_check(column: str = "locale") -> str:
    values = ", ".join(f"'{locale}'" for locale in CONTENT_LOCALES)
    return f"{column} IN ({values})"


def upgrade() -> None:
    # Keep every DDL command separate: asyncpg prepared statements must never
    # receive multiple SQL commands in one Alembic op.execute().
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
        f"CHECK ({_locale_check()})"
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
        f"CHECK ({_locale_check()})"
    )


def downgrade() -> None:
    # A downgrade must never truncate/corrupt a locale value. Refuse while any
    # row uses the expanded content contract.
    op.execute(
        """
        DO $guard$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM academy_content_versions
                WHERE locale NOT IN ('tr', 'en', 'de', 'ar')
            ) OR EXISTS (
                SELECT 1
                FROM academy_document_chunks
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
