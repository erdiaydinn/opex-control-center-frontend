"""Small, dependency-free audit log for PlanAI actions.

SQLite is intentional here: it works for local development and single-backend
deployments, survives restarts, and can be moved to Postgres later without
changing the API contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional


BACKEND_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PLONAGRAM_DATA_DIR", str(BACKEND_ROOT / "data")))
DB_PATH = Path(os.getenv("PLONAGRAM_AUDIT_DB", str(DATA_DIR / "plonagram_audit.sqlite3")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_audit_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                store_code TEXT,
                entity_type TEXT,
                entity_id TEXT,
                request_id TEXT,
                before_json TEXT,
                after_json TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_store ON audit_log(store_code)")


def write_audit(
    action: str,
    *,
    actor: str = "system",
    store_code: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    request_id: Optional[str] = None,
    before: Any = None,
    after: Any = None,
    metadata: Any = None,
) -> Dict[str, Any]:
    init_audit_db()
    created_at = now_iso()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_log
            (created_at, actor, action, store_code, entity_type, entity_id,
             request_id, before_json, after_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                str(actor or "system"),
                str(action or "unknown"),
                store_code,
                entity_type,
                str(entity_id) if entity_id is not None else None,
                request_id,
                _json(before) if before is not None else None,
                _json(after) if after is not None else None,
                _json(metadata) if metadata is not None else None,
            ),
        )
        return {
            "id": cursor.lastrowid,
            "created_at": created_at,
            "actor": str(actor or "system"),
            "action": str(action or "unknown"),
            "store_code": store_code,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "request_id": request_id,
        }


def _decode(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    for field in ("before_json", "after_json", "metadata_json"):
        raw = item.pop(field, None)
        item[field[:-5]] = json.loads(raw) if raw else None
    return item


def list_audit_logs(
    *,
    limit: int = 100,
    offset: int = 0,
    action: str = "",
    actor: str = "",
    store_code: str = "",
    entity_type: str = "",
    request_id: str = "",
    created_from: str = "",
    created_to: str = "",
) -> Dict[str, Any]:
    init_audit_db()
    limit = max(1, min(int(limit or 100), 1000))
    offset = max(0, int(offset or 0))
    clauses = []
    params: List[Any] = []
    for field, value in ((
        ("action", action),
        ("actor", actor),
        ("store_code", store_code),
        ("entity_type", entity_type),
        ("request_id", request_id),
    )):
        if str(value or "").strip():
            clauses.append(f"{field} = ?")
            params.append(str(value).strip())

    if str(created_from or "").strip():
        value = str(created_from).strip()
        if len(value) == 10:
            value = f"{value}T00:00:00Z"
        clauses.append("created_at >= ?")
        params.append(value)
    if str(created_to or "").strip():
        value = str(created_to).strip()
        if len(value) == 10:
            value = f"{value}T23:59:59.999999Z"
        clauses.append("created_at <= ?")
        params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM audit_log {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {"total": int(total), "limit": limit, "offset": offset, "logs": [_decode(row) for row in rows]}
