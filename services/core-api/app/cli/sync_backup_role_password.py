import asyncio
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

BACKUP_ROLE = "opex_backup"


def read_backup_password() -> str:
    environment = os.getenv(
        "OPEX_ENVIRONMENT",
        "development",
    ).strip().lower()

    direct_value = os.getenv(
        "OPEX_POSTGRES_BACKUP_PASSWORD",
        "",
    ).strip()

    secret_file = os.getenv(
        "OPEX_POSTGRES_BACKUP_PASSWORD_FILE",
        "",
    ).strip()

    if direct_value and secret_file:
        raise RuntimeError(
            "Backup database password and password file "
            "cannot both be configured"
        )

    if environment in {"staging", "production"} and direct_value:
        raise RuntimeError(
            "Backup database password must use a secret file "
            "in staging and production"
        )

    if secret_file:
        try:
            value = Path(secret_file).read_text(
                encoding="utf-8"
            ).strip()
        except OSError as exc:
            raise RuntimeError(
                "Backup database password secret file cannot be read"
            ) from exc

        if not value:
            raise RuntimeError(
                "Backup database password secret file is empty"
            )

        return value

    if not direct_value:
        raise RuntimeError(
            "Backup database password is not configured"
        )

    return direct_value


async def synchronize() -> None:
    password = read_backup_password()
    settings = get_settings()

    engine = create_async_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )

    try:
        async with engine.begin() as connection:
            role_exists = await connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_roles
                        WHERE rolname = :role_name
                    )
                    """
                ),
                {"role_name": BACKUP_ROLE},
            )

            if not role_exists:
                raise RuntimeError(
                    "Backup database role does not exist"
                )

            # Keep the credential out of SQL text and tracebacks.
            # The custom setting is transaction-local and disappears
            # when this transaction ends.
            await connection.execute(
                text(
                    """
                    SELECT set_config(
                        'opex.backup_password',
                        CAST(:password AS TEXT),
                        true
                    )
                    """
                ),
                {"password": password},
            )

            await connection.exec_driver_sql(
                """
                DO $$
                BEGIN
                    EXECUTE format(
                        'ALTER ROLE opex_backup PASSWORD %L',
                        current_setting('opex.backup_password')
                    );
                END
                $$;
                """
            )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(synchronize())
    print("Backup database role credential synchronized.")


if __name__ == "__main__":
    main()
