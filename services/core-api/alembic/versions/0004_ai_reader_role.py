"""Create fail-closed AI database capability role.

Revision ID: 0004_ai_reader_role
Revises: 0003_backup_role_grants
"""

from sqlalchemy import text

from alembic import op

revision = "0004_ai_reader_role"
down_revision = "0003_backup_role_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_roles
                    WHERE rolname = 'opex_ai_reader'
                ) THEN
                    CREATE ROLE opex_ai_reader
                        NOLOGIN
                        NOSUPERUSER
                        NOCREATEDB
                        NOCREATEROLE
                        NOINHERIT
                        NOBYPASSRLS;
                END IF;
            END
            $$;
            """
        )
    )

    connection.execute(
        text(
            """
            ALTER ROLE opex_ai_reader
                NOLOGIN
                NOSUPERUSER
                NOCREATEDB
                NOCREATEROLE
                NOINHERIT
                NOBYPASSRLS
            """
        )
    )

    # Explicitly fail closed.
    # No table privileges are granted here.
    connection.execute(
        text(
            """
            REVOKE ALL
            ON ALL TABLES IN SCHEMA public
            FROM opex_ai_reader
            """
        )
    )

    connection.execute(
        text(
            """
            REVOKE ALL
            ON ALL SEQUENCES IN SCHEMA public
            FROM opex_ai_reader
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        text(
            """
            DROP ROLE IF EXISTS opex_ai_reader
            """
        )
    )
