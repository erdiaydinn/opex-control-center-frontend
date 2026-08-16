"""Persistent single-use guard for AI tenant-context assertions.

The guard deliberately shares the governed AI Core SQLite state path so replay
protection survives process restarts on the current single-instance runtime.
A future horizontally scaled deployment must replace this with shared durable
state before claiming multi-replica production acceptance.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


REPLAY_TOMBSTONE_SECONDS = 120


class TenantContextReplayDetected(ValueError):
    """A previously consumed tenant-context assertion was presented again."""


class TenantContextReplayUnavailable(RuntimeError):
    """Replay authority could not be reached safely."""


class TenantContextReplayGuard:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_context_replay_guard (
                        assertion_id TEXT PRIMARY KEY,
                        consumed_at INTEGER NOT NULL
                    )
                    """
                )
        except sqlite3.Error as exc:
            raise TenantContextReplayUnavailable(
                "tenant-context replay authority unavailable"
            ) from exc

    def consume(self, assertion_id: str) -> None:
        now = int(time.time())
        cutoff = now - REPLAY_TOMBSTONE_SECONDS
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "DELETE FROM tenant_context_replay_guard WHERE consumed_at < ?",
                    (cutoff,),
                )
                try:
                    connection.execute(
                        """
                        INSERT INTO tenant_context_replay_guard (
                            assertion_id,
                            consumed_at
                        ) VALUES (?, ?)
                        """,
                        (assertion_id, now),
                    )
                except sqlite3.IntegrityError as exc:
                    raise TenantContextReplayDetected(
                        "tenant-context assertion replayed"
                    ) from exc
        except TenantContextReplayDetected:
            raise
        except sqlite3.Error as exc:
            raise TenantContextReplayUnavailable(
                "tenant-context replay authority unavailable"
            ) from exc
