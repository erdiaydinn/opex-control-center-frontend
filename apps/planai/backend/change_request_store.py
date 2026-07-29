"""Durable change-request storage used by the approval endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterator, List, Optional


BACKEND_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PLONAGRAM_DATA_DIR", str(BACKEND_ROOT / "data")))
DB_PATH = Path(os.getenv("PLONAGRAM_CHANGE_REQUEST_DB", str(DATA_DIR / "plonagram_changes.sqlite3")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_change_db() -> None:
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS change_request (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sku TEXT,
                product_name TEXT,
                old_json TEXT,
                new_json TEXT,
                requested_by TEXT NOT NULL,
                reason TEXT,
                status TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_change_status ON change_request(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_change_sku ON change_request(sku)")


def _decode(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    for key in ("old_json", "new_json"):
        raw = item.pop(key, None)
        item[key[:-5]] = json.loads(raw) if raw else {}
    return item


def create_change_request(
    *,
    sku: str,
    product_name: Optional[str],
    old: Dict[str, Any],
    new: Dict[str, Any],
    requested_by: str,
    reason: str,
) -> Dict[str, Any]:
    init_change_db()
    created_at = now_iso()
    with _connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO change_request
            (created_at, updated_at, sku, product_name, old_json, new_json,
             requested_by, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (created_at, created_at, sku, product_name, json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False), requested_by, reason),
        )
        row = conn.execute("SELECT * FROM change_request WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _decode(row)


def get_change_request(request_id: int) -> Optional[Dict[str, Any]]:
    init_change_db()
    with _connection() as conn:
        row = conn.execute("SELECT * FROM change_request WHERE id = ?", (int(request_id),)).fetchone()
    return _decode(row) if row else None


def list_change_requests(status: str = "") -> List[Dict[str, Any]]:
    init_change_db()
    with _connection() as conn:
        if status:
            rows = conn.execute("SELECT * FROM change_request WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM change_request ORDER BY id DESC").fetchall()
    return [_decode(row) for row in rows]


def review_change_request(request_id: int, *, approve: bool, reviewed_by: str) -> Optional[Dict[str, Any]]:
    init_change_db()
    status = "APPROVED" if approve else "REJECTED"
    reviewed_at = now_iso()
    with _connection() as conn:
        conn.execute(
            "UPDATE change_request SET status = ?, updated_at = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
            (status, reviewed_at, reviewed_by, reviewed_at, int(request_id)),
        )
        row = conn.execute("SELECT * FROM change_request WHERE id = ?", (int(request_id),)).fetchone()
    return _decode(row) if row else None

