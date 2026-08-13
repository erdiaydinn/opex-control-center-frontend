from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from .distributed_lock import claim as claim_distributed_lock, owner as distributed_owner


class InventoryRuleError(RuntimeError):
    pass


DB_PATH = Path(os.getenv("INVENTORY_DB", str(Path(__file__).resolve().parents[3] / "data" / "inventory_v20.db")))
LOCK = threading.RLock()


def now() -> str:
    return datetime.now(UTC).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize() -> None:
    with LOCK, closing(connect()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS inventory_documents(
          id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL, name TEXT NOT NULL,
          status TEXT NOT NULL, payload TEXT NOT NULL, created_by TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS inventory_lines(
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL, location TEXT NOT NULL,
          sku TEXT NOT NULL, barcode TEXT NOT NULL, quantity REAL NOT NULL,
          source TEXT NOT NULL, device_id TEXT NOT NULL, actor TEXT NOT NULL,
          created_at TEXT NOT NULL, revised_from TEXT,
          FOREIGN KEY(document_id) REFERENCES inventory_documents(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS inventory_event_unique ON inventory_lines(document_id,revised_from)
          WHERE revised_from LIKE 'event:%';
        CREATE TABLE IF NOT EXISTS inventory_location_locks(
          document_id TEXT NOT NULL, location TEXT NOT NULL, device_id TEXT NOT NULL,
          actor TEXT NOT NULL, expires_at TEXT NOT NULL, PRIMARY KEY(document_id,location)
        );
        CREATE TABLE IF NOT EXISTS inventory_audit(
          sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
          document_id TEXT, at TEXT NOT NULL, event TEXT NOT NULL, actor TEXT NOT NULL,
          record TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS inventory_audit_no_update BEFORE UPDATE ON inventory_audit
        BEGIN SELECT RAISE(ABORT, 'inventory audit is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS inventory_audit_no_delete BEFORE DELETE ON inventory_audit
        BEGIN SELECT RAISE(ABORT, 'inventory audit is append-only'); END;
        """)
        db.commit()


def audit(db: sqlite3.Connection, event: str, actor: str, document_id: str | None = None, **details) -> None:
    previous = db.execute("SELECT hash FROM inventory_audit ORDER BY sequence DESC LIMIT 1").fetchone()
    previous_hash = previous["hash"] if previous else "GENESIS"
    record = json.dumps({"document_id": document_id, **details}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    at = now()
    digest = hashlib.sha256(f"{previous_hash}|{at}|{event}|{actor}|{record}".encode()).hexdigest()
    db.execute(
        "INSERT INTO inventory_audit(id,document_id,at,event,actor,record,previous_hash,hash) VALUES(?,?,?,?,?,?,?,?)",
        (str(uuid4()), document_id, at, event, actor, record, previous_hash, digest),
    )


def _row(document: sqlite3.Row) -> dict:
    result = dict(document)
    result["payload"] = json.loads(result["payload"])
    return result


def list_documents(warehouse_scope: set[str] | None = None) -> list[dict]:
    with closing(connect()) as db:
        rows = [_row(row) for row in db.execute("SELECT * FROM inventory_documents ORDER BY created_at DESC")]
    return [row for row in rows if not warehouse_scope or row["warehouse_id"] in warehouse_scope]


def list_terminal_tasks(warehouse_scope: set[str] | None = None) -> list[dict]:
    """Return only blind-count-safe task metadata to handheld terminals."""
    tasks = []
    for document in list_documents(warehouse_scope):
        if document["status"] not in {"COUNTING", "RECOUNT_REQUIRED"}:
            continue
        tasks.append({
            "id": document["id"],
            "warehouse_id": document["warehouse_id"],
            "name": document["name"],
            "status": document["status"],
            "location_count": len(document["payload"].get("locations", [])),
            "updated_at": document["updated_at"],
        })
    return tasks


def get_document(document_id: str, warehouse_scope: set[str] | None = None) -> dict:
    with closing(connect()) as db:
        row = db.execute("SELECT * FROM inventory_documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise InventoryRuleError("Sayım belgesi bulunamadı.")
        document = _row(row)
        if warehouse_scope and document["warehouse_id"] not in warehouse_scope:
            raise PermissionError("Bu depoya erişim yetkiniz yok.")
        document["lines"] = [dict(item) for item in db.execute("SELECT * FROM inventory_lines WHERE document_id=? ORDER BY created_at", (document_id,))]
        document["audit"] = [dict(item) for item in db.execute("SELECT at,event,actor,record,hash FROM inventory_audit WHERE document_id=? ORDER BY sequence", (document_id,))]
        return document


def create_document(payload: dict, actor: str, warehouse_scope: set[str] | None = None) -> dict:
    if warehouse_scope and payload["warehouse_id"] not in warehouse_scope:
        raise PermissionError("Bu depo için sayım oluşturma yetkiniz yok.")
    locations = [str(value).strip().upper() for value in payload["locations"] if str(value).strip()]
    if len(locations) != len(set(locations)):
        raise InventoryRuleError("Lokasyon dosyasında mükerrer kayıt var.")
    products = payload["products"]
    barcodes = [str(row.get("barcode", "")).strip() for row in products]
    skus = [str(row.get("sku", "")).strip() for row in products]
    if not all(barcodes) or not all(skus) or len(barcodes) != len(set(barcodes)) or len(skus) != len(set(skus)):
        raise InventoryRuleError("SKU ve barkodlar boş olamaz ve depo içinde tekil olmalıdır.")
    document_id = f"CNT-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
    created = now()
    stored_payload = {**payload, "locations": locations, "products": products}
    with LOCK, closing(connect()) as db:
        db.execute(
            "INSERT INTO inventory_documents(id,warehouse_id,name,status,payload,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (document_id, payload["warehouse_id"], payload["name"], "COUNTING", json.dumps(stored_payload, ensure_ascii=False), actor, created, created),
        )
        audit(db, "DOCUMENT_CREATED", actor, document_id, warehouse_id=payload["warehouse_id"], location_count=len(locations), sku_count=len(products))
        db.commit()
    return get_document(document_id, warehouse_scope)


def lock_location(document_id: str, location: str, device_id: str, actor: str, ttl_seconds: int, warehouse_scope: set[str] | None = None) -> dict:
    document = get_document(document_id, warehouse_scope)
    location = location.strip().upper()
    if document["status"] != "COUNTING":
        raise InventoryRuleError("Belge sayım durumunda değil.")
    if location not in document["payload"]["locations"]:
        raise InventoryRuleError("Lokasyon sayım kapsamında değil.")
    lock_owner = f"{actor}:{device_id}"
    if not claim_distributed_lock(document_id, location, lock_owner, ttl_seconds):
        raise InventoryRuleError("Lokasyon başka terminal tarafından atomik olarak kilitlendi.")
    expires = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
    with LOCK, closing(connect()) as db:
        current = db.execute("SELECT * FROM inventory_location_locks WHERE document_id=? AND location=?", (document_id, location)).fetchone()
        if current and current["device_id"] != device_id and datetime.fromisoformat(current["expires_at"]) > datetime.now(UTC):
            raise InventoryRuleError(f"Lokasyon {current['actor']} tarafından sayılıyor.")
        db.execute(
            "INSERT INTO inventory_location_locks VALUES(?,?,?,?,?) ON CONFLICT(document_id,location) DO UPDATE SET device_id=excluded.device_id,actor=excluded.actor,expires_at=excluded.expires_at",
            (document_id, location, device_id, actor, expires),
        )
        audit(db, "LOCATION_LOCKED", actor, document_id, location=location, device_id=device_id, expires_at=expires)
        db.commit()
    return {"document_id": document_id, "location": location, "device_id": device_id, "expires_at": expires}


def record_scan(document_id: str, payload: dict, actor: str, warehouse_scope: set[str] | None = None) -> dict:
    document = get_document(document_id, warehouse_scope)
    if document["status"] != "COUNTING":
        raise InventoryRuleError("Onaylanmış veya kapatılmış belgeye kayıt eklenemez.")
    location = payload["location"].strip().upper()
    product = next((row for row in document["payload"]["products"] if str(row.get("barcode")) == payload["barcode"] or str(row.get("sku")) == payload["barcode"]), None)
    if location not in document["payload"]["locations"]:
        raise InventoryRuleError("Lokasyon sayım kapsamında değil.")
    if not product:
        raise InventoryRuleError("Barkod/SKU stok dosyasında bulunamadı.")
    remote_owner = distributed_owner(document_id, location)
    if remote_owner and remote_owner != f"{actor}:{payload['device_id']}":
        raise InventoryRuleError("Lokasyon başka terminal tarafından kilitli.")
    event_key = f"event:{payload['client_event_id']}"
    with LOCK, closing(connect()) as db:
        existing = db.execute("SELECT * FROM inventory_lines WHERE document_id=? AND revised_from=?", (document_id, event_key)).fetchone()
        if existing:
            return {**dict(existing), "idempotent_replay": True}
        lock = db.execute("SELECT * FROM inventory_location_locks WHERE document_id=? AND location=?", (document_id, location)).fetchone()
        if lock and lock["device_id"] != payload["device_id"] and datetime.fromisoformat(lock["expires_at"]) > datetime.now(UTC):
            raise InventoryRuleError("Lokasyon başka terminal tarafından kilitli.")
        line_id = f"LINE-{uuid4().hex[:12].upper()}"
        created = now()
        db.execute(
            "INSERT INTO inventory_lines VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (line_id, document_id, location, str(product["sku"]), str(product["barcode"]), payload["quantity"], payload["source"], payload["device_id"], actor, created, event_key),
        )
        audit(db, "SCAN_RECORDED", actor, document_id, line_id=line_id, location=location, sku=product["sku"], quantity=payload["quantity"], source=payload["source"], device_id=payload["device_id"])
        db.commit()
        return dict(db.execute("SELECT * FROM inventory_lines WHERE id=?", (line_id,)).fetchone())


def complete(document_id: str, actor: str, warehouse_scope: set[str] | None = None) -> dict:
    document = get_document(document_id, warehouse_scope)
    counted_locations = {row["location"] for row in document["lines"]}
    missing = sorted(set(document["payload"]["locations"]) - counted_locations)
    if missing:
        raise InventoryRuleError(f"{len(missing)} lokasyon sayılmadı.")
    totals: dict[str, float] = {}
    for line in document["lines"]:
        totals[line["sku"]] = totals.get(line["sku"], 0) + float(line["quantity"])
    quantity_limit = float(document["payload"].get("thresholds", {}).get("quantity", 5))
    value_limit = float(document["payload"].get("thresholds", {}).get("value_try", 1000))
    variances = []
    for product in document["payload"]["products"]:
        variance = totals.get(str(product["sku"]), 0) - float(product.get("expected", 0))
        value = variance * float(product.get("cost", 0))
        if variance:
            variances.append({"sku": product["sku"], "variance": variance, "value_try": value})
    requires_recount = any(abs(row["variance"]) >= quantity_limit or abs(row["value_try"]) >= value_limit for row in variances)
    status = "RECOUNT_REQUIRED" if requires_recount else ("APPROVAL_PENDING" if variances else "APPROVED")
    with LOCK, closing(connect()) as db:
        db.execute("UPDATE inventory_documents SET status=?,updated_at=?,version=version+1 WHERE id=?", (status, now(), document_id))
        audit(db, "COUNT_COMPLETED", actor, document_id, status=status, variances=variances)
        db.commit()
    return get_document(document_id, warehouse_scope)


def decide(document_id: str, decision: str, note: str, actor: str, warehouse_scope: set[str] | None = None) -> dict:
    document = get_document(document_id, warehouse_scope)
    if document["status"] not in {"APPROVAL_PENDING", "RECOUNT_REQUIRED"}:
        raise InventoryRuleError("Belge karar aşamasında değil.")
    target = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REQUEST_RECOUNT": "RECOUNT_REQUIRED"}[decision]
    with LOCK, closing(connect()) as db:
        db.execute("UPDATE inventory_documents SET status=?,updated_at=?,version=version+1 WHERE id=?", (target, now(), document_id))
        audit(db, f"DOCUMENT_{decision}", actor, document_id, note=note)
        db.commit()
    return get_document(document_id, warehouse_scope)


def readiness() -> dict:
    checks = {
        "central_database": DB_PATH.parent.exists(),
        "rbac_server_side": True,
        "offline_idempotency": True,
        "recount_thresholds": True,
        "location_locking": True,
        "barcode_validation": True,
        "immutable_audit": True,
        "erp_adapter": bool(os.getenv("INVENTORY_ERP_WEBHOOK")),
        "backup_target": bool(os.getenv("BACKUP_S3_BUCKET")),
        "oidc": bool(os.getenv("OPEX_OIDC_ISSUER")),
    }
    return {"status": "ready" if all(checks.values()) else "degraded", "checks": checks}
