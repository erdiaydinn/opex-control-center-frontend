"""Serialized prestart for durable EAY platform module initialization.

A multi-worker ASGI server must not let every worker race to seed an empty durable
store. This entrypoint acquires a PostgreSQL session advisory lock, runs the same
idempotent durable initializers used by the application lifespan, and releases the
lock before Uvicorn forks workers. Multiple replicas can execute this prestart
concurrently: only one performs first-seed work at a time and later replicas load
the committed state.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from app.modules.identity.service import bootstrap_admin, initialize as initialize_identity
from app.modules.inventory.service import initialize as initialize_inventory
from app.modules.recruitment.service import initialize as initialize_recruitment
from app.modules.workforce.service import initialize_workforce


_LOCK_NAME = "eay:platform:durable-prestart:v1"


@contextmanager
def _durable_prestart_lock() -> Iterator[None]:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        # Local/in-memory development has no cross-process durable state to lock.
        yield
        return

    import psycopg

    with psycopg.connect(database_url, autocommit=True) as database:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
                (_LOCK_NAME,),
            )
            try:
                yield
            finally:
                cursor.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    (_LOCK_NAME,),
                )


def main() -> None:
    with _durable_prestart_lock():
        initialize_workforce()
        initialize_recruitment()
        initialize_inventory()
        initialize_identity()
        bootstrap_admin()

    print("EAY_PLATFORM_DURABLE_PRESTART=PASS")


if __name__ == "__main__":
    main()
