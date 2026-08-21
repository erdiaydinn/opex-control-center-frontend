"""Add a least-privilege PostgreSQL backup role.

Revision ID: 0003_backup_role_grants
Revises: 0002_runtime_role_grants
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_backup_role_grants"
down_revision: str | None = "0002_runtime_role_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKUP_ROLE = "opex_backup"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_roles
                WHERE rolname = '{BACKUP_ROLE}'
            ) THEN
                CREATE ROLE {BACKUP_ROLE}
                    LOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOINHERIT
                    BYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    op.execute(
        f"""
        ALTER ROLE {BACKUP_ROLE}
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            BYPASSRLS
        """
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT CONNECT ON DATABASE %I TO {BACKUP_ROLE}',
                current_database()
            );
        END
        $$;
        """
    )

    op.execute(
        f"GRANT USAGE ON SCHEMA public TO {BACKUP_ROLE}"
    )
    op.execute(
        f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {BACKUP_ROLE}"
    )
    op.execute(
        f"GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {BACKUP_ROLE}"
    )

    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES
        FOR ROLE opex_migrator
        IN SCHEMA public
        GRANT SELECT ON TABLES TO {BACKUP_ROLE}
        """
    )

    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES
        FOR ROLE opex_migrator
        IN SCHEMA public
        GRANT SELECT ON SEQUENCES TO {BACKUP_ROLE}
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES
        FOR ROLE opex_migrator
        IN SCHEMA public
        REVOKE SELECT ON SEQUENCES FROM {BACKUP_ROLE}
        """
    )

    op.execute(
        f"""
        ALTER DEFAULT PRIVILEGES
        FOR ROLE opex_migrator
        IN SCHEMA public
        REVOKE SELECT ON TABLES FROM {BACKUP_ROLE}
        """
    )

    op.execute(
        f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {BACKUP_ROLE}"
    )
    op.execute(
        f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {BACKUP_ROLE}"
    )
    op.execute(
        f"REVOKE ALL PRIVILEGES ON SCHEMA public FROM {BACKUP_ROLE}"
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format(
                'REVOKE CONNECT ON DATABASE %I FROM {BACKUP_ROLE}',
                current_database()
            );
        END
        $$;
        """
    )

    op.execute(f"DROP ROLE IF EXISTS {BACKUP_ROLE}")
