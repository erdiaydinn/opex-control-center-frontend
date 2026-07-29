from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATABASE_DIR / "plonagram.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: Optional[str], default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS store_dna (
                store_code TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            );

            CREATE TABLE IF NOT EXISTS layout_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                version TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT,
                note TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_layout_versions_store ON layout_versions(store_code, id DESC);

            CREATE TABLE IF NOT EXISTS planogram_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                version TEXT NOT NULL,
                payload TEXT NOT NULL,
                summary TEXT,
                unplaced_count INTEGER NOT NULL DEFAULT 0,
                placed_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                created_by TEXT,
                note TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_planogram_versions_store ON planogram_versions(store_code, id DESC);

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT,
                store_code TEXT,
                title TEXT NOT NULL,
                owner TEXT,
                priority TEXT,
                deadline TEXT,
                status TEXT NOT NULL DEFAULT 'Open',
                payload TEXT,
                response TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_store ON tasks(store_code, id DESC);

            CREATE TABLE IF NOT EXISTS photo_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                planogram_version TEXT,
                corridor TEXT,
                module TEXT,
                shelf TEXT,
                uploader TEXT,
                description TEXT,
                file_name TEXT,
                file_path TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_store ON photo_evidence(store_code, id DESC);


            CREATE TABLE IF NOT EXISTS abc_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                report_version TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                total_items INTEGER NOT NULL DEFAULT 0,
                payload TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_abc_reports_store ON abc_reports(store_code, id DESC);

            CREATE TABLE IF NOT EXISTS abc_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                store_code TEXT,
                sku TEXT,
                product_name TEXT,
                sales_qty_7d REAL,
                percent_orders REAL,
                percent_stops REAL,
                abc_class TEXT,
                rank INTEGER,
                payload TEXT,
                FOREIGN KEY(report_id) REFERENCES abc_reports(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_abc_items_report ON abc_items(report_id);
            CREATE INDEX IF NOT EXISTS idx_abc_items_sku ON abc_items(store_code, sku);

            CREATE TABLE IF NOT EXISTS catalog_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                sku TEXT NOT NULL,
                barcode TEXT,
                product_name TEXT,
                brand TEXT,
                category_l1 TEXT,
                category_l2 TEXT,
                storage_type TEXT,
                width_cm REAL,
                height_cm REAL,
                depth_cm REAL,
                weight_kg REAL,
                image_url TEXT,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                UNIQUE(store_code, sku)
            );
            CREATE INDEX IF NOT EXISTS idx_catalog_products_store ON catalog_products(store_code);
            CREATE INDEX IF NOT EXISTS idx_catalog_products_sku ON catalog_products(store_code, sku);

            CREATE TABLE IF NOT EXISTS merged_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                sku TEXT NOT NULL,
                match_method TEXT,
                match_confidence REAL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                UNIQUE(store_code, sku)
            );
            CREATE INDEX IF NOT EXISTS idx_merged_products_store ON merged_products(store_code);

            CREATE TABLE IF NOT EXISTS import_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT,
                import_type TEXT NOT NULL,
                status TEXT NOT NULL,
                file_name TEXT,
                summary TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unplaced_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                planogram_version_id INTEGER,
                version TEXT,
                sku TEXT,
                product_name TEXT,
                reason TEXT,
                suggested_action TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_unplaced_products_store ON unplaced_products(store_code, planogram_version_id);

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                action TEXT NOT NULL,
                actor TEXT,
                before_payload TEXT,
                after_payload TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_store ON audit_log(store_code, id DESC);
            """
        )


def next_version(prefix: str, store_code: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{store_code.upper()}_{prefix}_{stamp}"


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def add_audit(conn: sqlite3.Connection, store_code: Optional[str], entity_type: str, entity_id: Optional[str], action: str, actor: Optional[str], before: Any = None, after: Any = None) -> None:
    conn.execute(
        """
        INSERT INTO audit_log(store_code, entity_type, entity_id, action, actor, before_payload, after_payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (store_code, entity_type, entity_id, action, actor, dumps(before) if before is not None else None, dumps(after) if after is not None else None, now_iso()),
    )
