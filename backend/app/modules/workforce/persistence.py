"""Tenant-scoped PostgreSQL persistence and durable Workforce outbox.

The in-memory adapter exists only for tests and local demos. PostgreSQL writes
use a versioned, compare-and-swap snapshot so two application instances cannot
silently overwrite each other's Workforce state. Domain state and its audit
record commit in the same transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Lock
from typing import Iterator


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MIGRATION_DATABASE_URL = os.getenv("WORKFORCE_MIGRATION_DATABASE_URL", "").strip()
ENVIRONMENT = os.getenv("DOCKOS_ENV", "development").strip().lower()
TENANT_ID = os.getenv("WORKFORCE_TENANT_ID", "eay" if ENVIRONMENT != "production" else "").strip()
ENABLED = bool(DATABASE_URL)
SCHEMA_VERSION = 42
_MIGRATION_PATHS = (
    Path(__file__).resolve().parents[3] / "migrations" / "002_workforce_v29.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "003_workforce_v30_acceptance.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "004_workforce_v31_lifecycle_acceptance.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "005_workforce_v32_identity_revocation.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "010_workforce_v33_demand_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "011_workforce_v34_capacity_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "012_workforce_v35_dpi_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "013_workforce_v36_optimizer_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "014_workforce_v37_replan_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "015_workforce_v38_override_learning.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "023_recruitment_candidate_upload_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "024_recruitment_production_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "025_recruitment_request_evidence_scan_authority.sql",
    Path(__file__).resolve().parents[3] / "migrations" / "026_recruitment_evidence_release_authority.sql",
)
_LOCK = Lock()
_MEMORY: dict[str, list[dict]] = {}
_EXPECTED_REVISIONS: dict[str, int] = {}


class ConcurrentWriteError(RuntimeError):
    """Raised instead of losing a write when another instance changed state."""


def _tenant_id() -> str:
    if not TENANT_ID:
        raise RuntimeError("WORKFORCE_TENANT_ID production ortamında zorunludur")
    return TENANT_ID


def tenant_id() -> str:
    """Return the configured tenant without exposing role-binding internals."""
    return _tenant_id()


def _connect(database_url: str | None = None):
    import psycopg

    return psycopg.connect(database_url or DATABASE_URL, autocommit=False)


@contextmanager
def connection(database_url: str | None = None) -> Iterator[object]:
    if not ENABLED:
        raise RuntimeError("PostgreSQL persistence is not configured")
    with _connect(database_url) as database:
        yield database


def _set_tenant(cursor) -> None:
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (_tenant_id(),))


def _schema_exists(cursor) -> bool:
    cursor.execute("SELECT to_regclass('public.workforce_collection_versions') IS NOT NULL")
    return bool(cursor.fetchone()[0])


def initialize() -> None:
    if not ENABLED:
        return
    auto_migrate = os.getenv(
        "WORKFORCE_AUTO_MIGRATE", "false" if ENVIRONMENT == "production" else "true"
    ).lower() == "true"
    migration_url = MIGRATION_DATABASE_URL or DATABASE_URL
    with connection(migration_url if auto_migrate else DATABASE_URL) as database, database.cursor() as cursor:
        _set_tenant(cursor)
        if auto_migrate:
            for migration_path in _MIGRATION_PATHS:
                cursor.execute(migration_path.read_text(encoding="utf-8"))
            database.commit()
        else:
            if not _schema_exists(cursor):
                raise RuntimeError(
                    "Workforce V32 şeması eksik; uygulamadan önce versioned migrations uygulanmalı"
                )
            cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
            version = cursor.fetchone()[0]
            if version is None or int(version) < SCHEMA_VERSION:
                raise RuntimeError(
                    f"Workforce şema sürümü {version or 0}; uygulama V{SCHEMA_VERSION} gerektiriyor"
                )


def schema_version() -> int | None:
    if not ENABLED:
        return None
    try:
        with connection() as database, database.cursor() as cursor:
            _set_tenant(cursor)
            cursor.execute("SELECT max(version) FROM workforce_schema_migrations")
            value = cursor.fetchone()[0]
            return int(value) if value is not None else 0
    except Exception:
        return 0


def has_snapshot() -> bool:
    if not ENABLED:
        return bool(_MEMORY)
    with connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM workforce_collection_versions WHERE tenant_id=%s)",
            (_tenant_id(),),
        )
        return bool(cursor.fetchone()[0])


def _serializable(rows: list[dict]) -> list[dict]:
    return json.loads(json.dumps(rows, ensure_ascii=False, default=str))


def load_snapshot(kinds: list[str]) -> dict[str, list[dict]]:
    unique_kinds = list(dict.fromkeys(str(kind) for kind in kinds))
    if not ENABLED:
        return {kind: deepcopy(_MEMORY.get(kind, [])) for kind in unique_kinds}
    tenant_id = _tenant_id()
    result = {kind: [] for kind in unique_kinds}
    with connection() as database, database.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        _set_tenant(cursor)
        cursor.execute(
            "SELECT kind, version FROM workforce_collection_versions WHERE tenant_id=%s AND kind=ANY(%s)",
            (tenant_id, unique_kinds),
        )
        revisions = {kind: int(version) for kind, version in cursor.fetchall()}
        cursor.execute(
            """SELECT kind, payload FROM workforce_entities
               WHERE tenant_id=%s AND kind=ANY(%s)
               ORDER BY kind, created_at, entity_id""",
            (tenant_id, unique_kinds),
        )
        for kind, payload in cursor.fetchall():
            result[kind].append(payload)
    with _LOCK:
        for kind in unique_kinds:
            _EXPECTED_REVISIONS[kind] = revisions.get(kind, 0)
    return result


def load_collection(kind: str) -> list[dict]:
    return load_snapshot([kind])[kind]


def load_document(kind: str, default: dict) -> dict:
    rows = load_collection(kind)
    return deepcopy(rows[0]) if rows else deepcopy(default)


def _entity_id(row: dict, index: int) -> str:
    return str(row.get("id") or row.get("person_id") or row.get("engine_key") or index)


def _build_audit_record(cursor, event: str, actor: str, details: dict) -> dict:
    tenant_id = _tenant_id()
    cursor.execute(
        # Callers already hold the tenant-wide advisory transaction lock. A
        # row lock here would additionally require UPDATE privilege on the
        # append-only audit table, widening the runtime role for no benefit.
        "SELECT hash FROM workforce_audit WHERE tenant_id=%s ORDER BY sequence DESC LIMIT 1",
        (tenant_id,),
    )
    previous = cursor.fetchone()
    previous_hash = previous[0] if previous else "GENESIS"
    now = datetime.now(UTC)
    record = {
        "id": f"AUD-{now.strftime('%Y%m%d%H%M%S%f')}",
        "tenant_id": tenant_id,
        "at": now.isoformat(),
        "event": event,
        "actor": actor,
        "previous_hash": previous_hash,
        **details,
    }
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    record["hash"] = sha256(f"{previous_hash}|{canonical}".encode()).hexdigest()
    cursor.execute(
        """INSERT INTO workforce_audit
           (tenant_id,id,at,event,actor,record,previous_hash,hash)
           VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
        (
            tenant_id,
            record["id"],
            now,
            event,
            actor,
            json.dumps(record, ensure_ascii=False, default=str),
            previous_hash,
            record["hash"],
        ),
    )
    return record


def persist_snapshot_with_audit(
    collections: dict[str, list[dict]], event: str, actor: str,
    related_recruitment_request: dict | None = None,
    expected_recruitment_revision: int | None = None,
    cancel_notification_person_ids: list[str] | None = None,
    cancel_notification_ids: list[str] | None = None,
    identity_revocations: list[dict] | None = None,
    **details: object,
) -> dict | None:
    """Atomically persist state and audit, rejecting stale process snapshots."""
    serializable = {kind: _serializable(rows) for kind, rows in collections.items()}
    if not ENABLED:
        for kind, rows in serializable.items():
            _MEMORY[kind] = deepcopy(rows)
        return None
    tenant_id = _tenant_id()
    kinds = sorted(serializable)
    with _LOCK:
        expected = {kind: _EXPECTED_REVISIONS.get(kind, 0) for kind in kinds}
        with connection() as database, database.cursor() as cursor:
            _set_tenant(cursor)
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"workforce:{tenant_id}",))
            cursor.executemany(
                """INSERT INTO workforce_collection_versions(tenant_id,kind,version)
                   VALUES (%s,%s,0) ON CONFLICT (tenant_id,kind) DO NOTHING""",
                [(tenant_id, kind) for kind in kinds],
            )
            cursor.execute(
                """SELECT kind, version FROM workforce_collection_versions
                   WHERE tenant_id=%s AND kind=ANY(%s) ORDER BY kind FOR UPDATE""",
                (tenant_id, kinds),
            )
            actual = {kind: int(version) for kind, version in cursor.fetchall()}
            stale = {
                kind: {"expected": expected[kind], "actual": actual.get(kind, 0)}
                for kind in kinds
                if expected[kind] != actual.get(kind, 0)
            }
            if stale:
                database.rollback()
                raise ConcurrentWriteError(f"Workforce snapshot stale: {stale}")
            for kind in kinds:
                cursor.execute(
                    "DELETE FROM workforce_entities WHERE tenant_id=%s AND kind=%s",
                    (tenant_id, kind),
                )
                values = [
                    (tenant_id, kind, _entity_id(row, index), json.dumps(row, ensure_ascii=False))
                    for index, row in enumerate(serializable[kind])
                ]
                if values:
                    cursor.executemany(
                        """INSERT INTO workforce_entities(tenant_id,kind,entity_id,payload)
                           VALUES (%s,%s,%s,%s::jsonb)""",
                        values,
                    )
                cursor.execute(
                    """UPDATE workforce_collection_versions
                       SET version=version+1, updated_at=now()
                       WHERE tenant_id=%s AND kind=%s RETURNING version""",
                    (tenant_id, kind),
                )
                actual[kind] = int(cursor.fetchone()[0])
            # Notifications generated by the same domain mutation enter the
            # durable outbox in this transaction. A stale/failed state write
            # therefore cannot leak a push for an operation that never committed.
            for notification in serializable.get("notifications", []):
                scheduled_at = notification.get("scheduled_at") or datetime.now(UTC).isoformat()
                cursor.execute(
                    """INSERT INTO workforce_notification_outbox
                       (tenant_id,id,person_id,platform,push_token,notification_type,scheduled_at,payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT (tenant_id,id) DO NOTHING""",
                    (
                        tenant_id, notification["id"], notification["person_id"], notification.get("platform"),
                        notification.get("push_token"), notification.get("type", "GENERAL"), scheduled_at,
                        json.dumps(notification, ensure_ascii=False, default=str),
                    ),
                )
            if cancel_notification_person_ids:
                cursor.execute(
                    """UPDATE workforce_notification_outbox
                       SET status='CANCELLED',locked_at=NULL,last_error='EMPLOYMENT_ENDED'
                       WHERE tenant_id=%s AND person_id=ANY(%s) AND status IN ('PENDING','SENDING')""",
                    (tenant_id, list(dict.fromkeys(cancel_notification_person_ids))),
                )
            if cancel_notification_ids:
                cursor.execute(
                    """UPDATE workforce_notification_outbox
                       SET status='CANCELLED',locked_at=NULL,last_error='SHIFT_CANCELLED_BY_EMPLOYMENT_END'
                       WHERE tenant_id=%s AND id=ANY(%s) AND status IN ('PENDING','SENDING')""",
                    (tenant_id, list(dict.fromkeys(cancel_notification_ids))),
                )
            for revocation in identity_revocations or []:
                cursor.execute(
                    """INSERT INTO workforce_identity_revocation_outbox
                       (tenant_id,id,employee_id,provider,status,created_at,payload)
                       VALUES (%s,%s,%s,%s,'PENDING',now(),%s::jsonb)
                       ON CONFLICT (tenant_id,id) DO NOTHING""",
                    (
                        tenant_id, revocation["id"], revocation["employee_id"],
                        revocation.get("provider", "CORPORATE_OIDC"),
                        json.dumps(revocation, ensure_ascii=False, default=str),
                    ),
                )
            if related_recruitment_request is not None:
                if expected_recruitment_revision is None:
                    raise ValueError("expected_recruitment_revision is required for atomic hire activation")
                request_record = _serializable([related_recruitment_request])[0]
                next_revision = expected_recruitment_revision + 1
                request_record["revision"] = next_revision
                cursor.execute(
                    """UPDATE recruitment_requests
                       SET status=%s, warehouse_id=%s, revision=%s, payload=%s::jsonb
                       WHERE tenant_id=%s AND id=%s AND revision=%s
                       RETURNING revision""",
                    (
                        request_record["status"], request_record["warehouse_id"], next_revision,
                        json.dumps(request_record, ensure_ascii=False, default=str), tenant_id,
                        request_record["id"], expected_recruitment_revision,
                    ),
                )
                if cursor.fetchone() is None:
                    database.rollback()
                    raise ConcurrentWriteError(
                        f"Recruitment request stale: id={request_record['id']} expected={expected_recruitment_revision}"
                    )
            record = _build_audit_record(cursor, event, actor, dict(details))
            database.commit()
            if related_recruitment_request is not None:
                related_recruitment_request["revision"] = expected_recruitment_revision + 1
        _EXPECTED_REVISIONS.update(actual)
    return record


def replace_collection(kind: str, rows: list[dict]) -> None:
    persist_snapshot_with_audit({kind: rows}, "COLLECTION_REPLACED", "system", kind=kind)


def save_document(kind: str, value: dict) -> None:
    replace_collection(kind, [{"id": kind, **value}])


def append_audit(event: str, actor: str, **details: object) -> dict | None:
    if not ENABLED:
        return None
    with _LOCK, connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"workforce:{_tenant_id()}",))
        record = _build_audit_record(cursor, event, actor, dict(details))
        database.commit()
        return record


def list_audit(limit: int) -> list[dict] | None:
    if not ENABLED:
        return None
    with connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute(
            "SELECT record FROM workforce_audit WHERE tenant_id=%s ORDER BY sequence DESC LIMIT %s",
            (_tenant_id(), limit),
        )
        return [row[0] for row in cursor.fetchall()]


def enqueue_notification(notification: dict) -> None:
    if not ENABLED:
        return
    scheduled_at = notification.get("scheduled_at") or datetime.now(UTC).isoformat()
    with connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute(
            """INSERT INTO workforce_notification_outbox
               (tenant_id,id,person_id,platform,push_token,notification_type,scheduled_at,payload)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (tenant_id,id) DO NOTHING""",
            (
                _tenant_id(), notification["id"], notification["person_id"], notification.get("platform"),
                notification.get("push_token"), notification.get("type", "GENERAL"), scheduled_at,
                json.dumps(notification, ensure_ascii=False, default=str),
            ),
        )
        database.commit()


def claim_due_notifications(batch_size: int = 50) -> list[dict]:
    if not ENABLED:
        return []
    with connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute(
            """WITH due AS (
                 SELECT tenant_id,id FROM workforce_notification_outbox
                 WHERE tenant_id=%s AND (
                   (status='PENDING' AND scheduled_at <= now()) OR
                   (status='SENDING' AND locked_at < now() - make_interval(secs => %s))
                 )
                 ORDER BY scheduled_at FOR UPDATE SKIP LOCKED LIMIT %s
               )
               UPDATE workforce_notification_outbox o
               SET status='SENDING', locked_at=now(), attempts=attempts+1
               FROM due WHERE o.tenant_id=due.tenant_id AND o.id=due.id
               RETURNING o.id,o.person_id,o.platform,o.push_token,o.notification_type,o.payload,o.attempts""",
            (_tenant_id(), max(30, int(os.getenv("WORKFORCE_PUSH_VISIBILITY_TIMEOUT_SECONDS", "300"))), batch_size),
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
    with connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute(
            "SELECT attempts FROM workforce_notification_outbox WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (_tenant_id(), notification_id),
        )
        row = cursor.fetchone()
        if row is None:
            return
        attempts = int(row[0])
        maximum_attempts = max(1, int(os.getenv("WORKFORCE_PUSH_MAX_ATTEMPTS", "8")))
        if error is None:
            status, retry_delay = "DELIVERED", 0
        elif attempts >= maximum_attempts:
            status, retry_delay = "DEAD_LETTER", 0
        else:
            status = "PENDING"
            retry_delay = min(3600, max(5, int(os.getenv("WORKFORCE_PUSH_RETRY_BASE_SECONDS", "30"))) * (2 ** max(0, attempts - 1)))
        cursor.execute(
            """UPDATE workforce_notification_outbox SET status=%s,
               delivered_at=CASE WHEN %s IS NULL THEN now() ELSE delivered_at END,
               dead_lettered_at=CASE WHEN %s='DEAD_LETTER' THEN now() ELSE dead_lettered_at END,
               scheduled_at=CASE WHEN %s='PENDING' THEN now() + make_interval(secs => %s) ELSE scheduled_at END,
               last_error=%s, locked_at=NULL WHERE tenant_id=%s AND id=%s""",
            (status, error, status, status, retry_delay, error[:2000] if error else None, _tenant_id(), notification_id),
        )
        database.commit()


def claim_identity_revocations(batch_size: int = 50) -> list[dict]:
    if not ENABLED:
        return []
    with connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute(
            """WITH due AS (
                 SELECT tenant_id,id FROM workforce_identity_revocation_outbox
                 WHERE tenant_id=%s AND (
                   (status='PENDING' AND (next_attempt_at IS NULL OR next_attempt_at <= now())) OR
                   (status='SENDING' AND next_attempt_at < now())
                 )
                 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT %s
               )
               UPDATE workforce_identity_revocation_outbox o
               SET status='SENDING',attempts=attempts+1,
                   next_attempt_at=now() + interval '5 minutes'
               FROM due WHERE o.tenant_id=due.tenant_id AND o.id=due.id
               RETURNING o.id,o.employee_id,o.provider,o.payload,o.attempts""",
            (_tenant_id(), batch_size),
        )
        rows = cursor.fetchall()
        database.commit()
    return [
        {"id": row[0], "employee_id": row[1], "provider": row[2], "payload": row[3], "attempts": row[4]}
        for row in rows
    ]


def finish_identity_revocation(revocation_id: str, error: str | None = None) -> None:
    if not ENABLED:
        return
    with connection() as database, database.cursor() as cursor:
        _set_tenant(cursor)
        cursor.execute(
            "SELECT attempts FROM workforce_identity_revocation_outbox WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (_tenant_id(), revocation_id),
        )
        row = cursor.fetchone()
        if row is None:
            return
        attempts = int(row[0])
        maximum_attempts = max(1, int(os.getenv("WORKFORCE_IDENTITY_REVOKE_MAX_ATTEMPTS", "8")))
        if error is None:
            status, retry_delay = "DELIVERED", 0
        elif attempts >= maximum_attempts:
            status, retry_delay = "DEAD_LETTER", 0
        else:
            status = "PENDING"
            retry_delay = min(3600, 30 * (2 ** max(0, attempts - 1)))
        cursor.execute(
            """UPDATE workforce_identity_revocation_outbox SET status=%s,last_error=%s,
               delivered_at=CASE WHEN %s IS NULL THEN now() ELSE delivered_at END,
               next_attempt_at=CASE WHEN %s='PENDING' THEN now() + make_interval(secs => %s) ELSE NULL END
               WHERE tenant_id=%s AND id=%s""",
            (status, error[:2000] if error else None, error, status, retry_delay, _tenant_id(), revocation_id),
        )
        database.commit()


def ready() -> bool:
    if not ENABLED:
        return ENVIRONMENT != "production"
    if not TENANT_ID:
        return False
    try:
        with connection() as database, database.cursor() as cursor:
            _set_tenant(cursor)
            cursor.execute("SELECT 1, workforce_current_tenant()")
            one, mapped_tenant = cursor.fetchone()
            database_ok = one == 1 and mapped_tenant == TENANT_ID
        return database_ok and schema_version() >= SCHEMA_VERSION
    except Exception:
        return False
