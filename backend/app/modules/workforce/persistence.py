"""PostgreSQL persistence and durable notification outbox for Workforce.

The service deliberately keeps its domain objects as JSONB documents so the
existing API contract can evolve without destructive migrations. PostgreSQL is
still the source of truth: every collection is stored transactionally and
indexed by kind/id. Tests may opt into the in-memory adapter by leaving
DATABASE_URL empty.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from threading import Lock
from typing import Iterator


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ENABLED = bool(DATABASE_URL)
_LOCK = Lock()
_MEMORY: dict[str, list[dict]] = {}


def _connect():
    import psycopg

    return psycopg.connect(DATABASE_URL, autocommit=False)


@contextmanager
def connection() -> Iterator[object]:
    if not ENABLED:
        raise RuntimeError("PostgreSQL persistence is not configured")
    with _connect() as database:
        yield database


def initialize() -> None:
    if not ENABLED:
        return
    with connection() as database, database.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workforce_entities (
              kind text NOT NULL,
              entity_id text NOT NULL,
              payload jsonb NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(),
              PRIMARY KEY (kind, entity_id)
            );
            CREATE INDEX IF NOT EXISTS workforce_entities_kind_idx
              ON workforce_entities (kind, updated_at DESC);

            CREATE TABLE IF NOT EXISTS workforce_audit (
              sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              id text NOT NULL UNIQUE,
              at timestamptz NOT NULL,
              event text NOT NULL,
              actor text NOT NULL,
              record jsonb NOT NULL,
              previous_hash text NOT NULL,
              hash text NOT NULL UNIQUE
            );

            CREATE OR REPLACE FUNCTION workforce_audit_immutable()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'workforce_audit is append-only';
            END $$;
            DROP TRIGGER IF EXISTS workforce_audit_no_update ON workforce_audit;
            CREATE TRIGGER workforce_audit_no_update
              BEFORE UPDATE OR DELETE ON workforce_audit
              FOR EACH ROW EXECUTE FUNCTION workforce_audit_immutable();

            CREATE TABLE IF NOT EXISTS workforce_notification_outbox (
              id text PRIMARY KEY,
              person_id text NOT NULL,
              platform text,
              push_token text,
              notification_type text NOT NULL,
              scheduled_at timestamptz NOT NULL,
              payload jsonb NOT NULL,
              status text NOT NULL DEFAULT 'PENDING',
              attempts integer NOT NULL DEFAULT 0,
              locked_at timestamptz,
              delivered_at timestamptz,
              last_error text,
              created_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS workforce_outbox_due_idx
              ON workforce_notification_outbox(status, scheduled_at);
            """
        )
        database.commit()


def load_collection(kind: str) -> list[dict]:
    if not ENABLED:
        return deepcopy(_MEMORY.get(kind, []))
    with connection() as database, database.cursor() as cursor:
        cursor.execute(
            "SELECT payload FROM workforce_entities WHERE kind=%s ORDER BY created_at, entity_id",
            (kind,),
        )
        return [row[0] for row in cursor.fetchall()]


def replace_collection(kind: str, rows: list[dict]) -> None:
    serializable = [json.loads(json.dumps(row, ensure_ascii=False, default=str)) for row in rows]
    if not ENABLED:
        _MEMORY[kind] = deepcopy(serializable)
        return
    with _LOCK, connection() as database, database.cursor() as cursor:
        cursor.execute("DELETE FROM workforce_entities WHERE kind=%s", (kind,))
        for index, row in enumerate(serializable):
            entity_id = str(row.get("id") or row.get("person_id") or row.get("engine_key") or index)
            cursor.execute(
                "INSERT INTO workforce_entities(kind, entity_id, payload) VALUES (%s,%s,%s::jsonb)",
                (kind, entity_id, json.dumps(row, ensure_ascii=False)),
            )
        database.commit()


def load_document(kind: str, default: dict) -> dict:
    rows = load_collection(kind)
    return deepcopy(rows[0]) if rows else deepcopy(default)


def save_document(kind: str, value: dict) -> None:
    replace_collection(kind, [{"id": kind, **value}])


def append_audit(event: str, actor: str, **details: object) -> dict | None:
    if not ENABLED:
        return None
    with _LOCK, connection() as database, database.cursor() as cursor:
        cursor.execute("SELECT hash FROM workforce_audit ORDER BY sequence DESC LIMIT 1 FOR UPDATE")
        previous = cursor.fetchone()
        previous_hash = previous[0] if previous else "GENESIS"
        now = datetime.now(UTC)
        record = {
            "id": f"AUD-{now.strftime('%Y%m%d%H%M%S%f')}",
            "at": now.isoformat(),
            "event": event,
            "actor": actor,
            "previous_hash": previous_hash,
            **details,
        }
        canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        record["hash"] = sha256(f"{previous_hash}|{canonical}".encode()).hexdigest()
        cursor.execute(
            """INSERT INTO workforce_audit(id,at,event,actor,record,previous_hash,hash)
               VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)""",
            (record["id"], now, event, actor, json.dumps(record, ensure_ascii=False, default=str), previous_hash, record["hash"]),
        )
        database.commit()
        return record


def list_audit(limit: int) -> list[dict] | None:
    if not ENABLED:
        return None
    with connection() as database, database.cursor() as cursor:
        cursor.execute("SELECT record FROM workforce_audit ORDER BY sequence DESC LIMIT %s", (limit,))
        return [row[0] for row in cursor.fetchall()]


def enqueue_notification(notification: dict) -> None:
    if not ENABLED:
        return
    scheduled_at = notification.get("scheduled_at") or datetime.now(UTC).isoformat()
    with connection() as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO workforce_notification_outbox
               (id, person_id, platform, push_token, notification_type, scheduled_at, payload)
               VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (id) DO NOTHING""",
            (
                notification["id"], notification["person_id"], notification.get("platform"),
                notification.get("push_token"), notification.get("type", "GENERAL"), scheduled_at,
                json.dumps(notification, ensure_ascii=False, default=str),
            ),
        )
        database.commit()


def claim_due_notifications(batch_size: int = 50) -> list[dict]:
    if not ENABLED:
        return []
    with connection() as database, database.cursor() as cursor:
        cursor.execute(
            """WITH due AS (
                 SELECT id FROM workforce_notification_outbox
                 WHERE status='PENDING' AND scheduled_at <= now()
                 ORDER BY scheduled_at
                 FOR UPDATE SKIP LOCKED LIMIT %s
               )
               UPDATE workforce_notification_outbox o
               SET status='SENDING', locked_at=now(), attempts=attempts+1
               FROM due WHERE o.id=due.id
               RETURNING o.id,o.person_id,o.platform,o.push_token,o.notification_type,o.payload,o.attempts""",
            (batch_size,),
        )
        rows = cursor.fetchall()
        database.commit()
    return [
        {"id": row[0], "person_id": row[1], "platform": row[2], "push_token": row[3], "type": row[4], "payload": row[5], "attempts": row[6]}
        for row in rows
    ]


def finish_notification(notification_id: str, error: str | None = None) -> None:
    if not ENABLED:
        return
    status = "DELIVERED" if error is None else "PENDING"
    with connection() as database, database.cursor() as cursor:
        cursor.execute(
            """UPDATE workforce_notification_outbox SET status=%s,
               delivered_at=CASE WHEN %s IS NULL THEN now() ELSE delivered_at END,
               last_error=%s, locked_at=NULL WHERE id=%s""",
            (status, error, error[:2000] if error else None, notification_id),
        )
        database.commit()


def ready() -> bool:
    if not ENABLED:
        return True
    try:
        with connection() as database, database.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1
    except Exception:
        return False
