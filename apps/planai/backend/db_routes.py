from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, File, UploadFile

from db import DB_PATH, add_audit, connect, dumps, init_db, loads, next_version, now_iso, row_to_dict

router = APIRouter(tags=["plonagram-db"])


def clean_store(store_code: str) -> str:
    return str(store_code or "AUTO").strip().upper()


def public_layout(row):
    if not row:
        return None
    d = row_to_dict(row)
    d["payload"] = loads(d.get("payload"), {})
    return d


def public_planogram(row):
    if not row:
        return None
    d = row_to_dict(row)
    d["payload"] = loads(d.get("payload"), {})
    d["summary"] = loads(d.get("summary"), {})
    return d


def public_task(row):
    if not row:
        return None
    d = row_to_dict(row)
    d["payload"] = loads(d.get("payload"), {})
    return d


@router.on_event("startup")
def _startup():
    init_db()


@router.get("/db/health")
def db_health():
    init_db()
    with connect() as conn:
        counts = {}
        for table in ["store_dna", "layout_versions", "planogram_versions", "tasks", "photo_evidence", "audit_log"]:
            counts[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
    return {"status": "ok", "db_path": str(DB_PATH), "counts": counts}


@router.get("/bootstrap/{store_code}")
def bootstrap(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        dna = conn.execute("SELECT * FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
        layout = conn.execute("SELECT * FROM layout_versions WHERE store_code=? ORDER BY id DESC LIMIT 1", (store_code,)).fetchone()
        plan = conn.execute("SELECT * FROM planogram_versions WHERE store_code=? ORDER BY id DESC LIMIT 1", (store_code,)).fetchone()
        tasks = conn.execute("SELECT * FROM tasks WHERE store_code IN (?, 'ALL') ORDER BY id DESC LIMIT 200", (store_code,)).fetchall()
    return {
        "status": "success",
        "store_code": store_code,
        "dna": loads(dna["payload"], {}) if dna else None,
        "layout": public_layout(layout),
        "planogram": public_planogram(plan),
        "tasks": [public_task(t) for t in tasks],
    }


@router.get("/stores/{store_code}/dna")
def get_store_dna(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
    if not row:
        return {"status": "empty", "store_code": store_code, "dna": None}
    return {"status": "success", "store_code": store_code, "dna": loads(row["payload"], {}), "updated_at": row["updated_at"], "updated_by": row["updated_by"]}


@router.post("/stores/{store_code}/dna")
def save_store_dna(store_code: str, payload: Dict[str, Any] = Body(...)):
    store_code = clean_store(store_code)
    actor = payload.get("updated_by") or payload.get("actor") or "system"
    dna = payload.get("dna") if isinstance(payload.get("dna"), dict) else payload
    init_db()
    with connect() as conn:
        before = conn.execute("SELECT payload FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
        conn.execute(
            """
            INSERT INTO store_dna(store_code, payload, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(store_code) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at, updated_by=excluded.updated_by
            """,
            (store_code, dumps(dna), now_iso(), actor),
        )
        add_audit(conn, store_code, "store_dna", store_code, "UPSERT", actor, loads(before["payload"], {}) if before else None, dna)
    return {"status": "success", "store_code": store_code, "dna": dna}


@router.post("/layouts/{store_code}/save")
def save_layout(store_code: str, payload: Dict[str, Any] = Body(...)):
    store_code = clean_store(store_code)
    actor = payload.get("created_by") or payload.get("actor") or "frontend"
    version = payload.get("version") or next_version("LAYOUT", store_code)
    layout_payload = payload.get("layout") or payload.get("payload") or payload
    note = payload.get("note") or "Layout saved from PLONAGRAM OS"
    init_db()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO layout_versions(store_code, version, payload, created_at, created_by, note, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (store_code, version, dumps(layout_payload), now_iso(), actor, note),
        )
        add_audit(conn, store_code, "layout", str(cur.lastrowid), "CREATE_VERSION", actor, None, {"version": version})
    return {"status": "success", "store_code": store_code, "version": version, "id": cur.lastrowid}


@router.get("/layouts/{store_code}/latest")
def get_latest_layout(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM layout_versions WHERE store_code=? ORDER BY id DESC LIMIT 1", (store_code,)).fetchone()
    return {"status": "success" if row else "empty", "store_code": store_code, "layout": public_layout(row)}


@router.get("/layouts/{store_code}/versions")
def list_layout_versions(store_code: str, limit: int = 50):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT id, store_code, version, created_at, created_by, note, is_active FROM layout_versions WHERE store_code=? ORDER BY id DESC LIMIT ?", (store_code, limit)).fetchall()
    return {"status": "success", "store_code": store_code, "versions": [row_to_dict(r) for r in rows]}


@router.post("/planograms/{store_code}/save")
def save_planogram(store_code: str, payload: Dict[str, Any] = Body(...)):
    store_code = clean_store(store_code)
    actor = payload.get("created_by") or payload.get("actor") or "frontend"
    version = payload.get("version") or next_version("PLAN", store_code)
    plan_payload = payload.get("planogram") or payload.get("payload") or payload
    summary = payload.get("summary") or plan_payload.get("summary") or {}
    products = plan_payload.get("products") or []
    unplaced = plan_payload.get("unplacedProducts") or plan_payload.get("unplaced_products") or []
    note = payload.get("note") or "Planogram saved from PLONAGRAM OS"
    init_db()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO planogram_versions(store_code, version, payload, summary, unplaced_count, placed_count, created_at, created_by, note, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (store_code, version, dumps(plan_payload), dumps(summary), len(unplaced), len(products), now_iso(), actor, note),
        )
        planogram_id = cur.lastrowid
        for item in unplaced:
            conn.execute(
                """
                INSERT INTO unplaced_products(store_code, planogram_version_id, version, sku, product_name, reason, suggested_action, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (store_code, planogram_id, version, item.get("sku"), item.get("product_name"), item.get("reason") or item.get("constraint_reason"), item.get("suggested_action"), dumps(item), now_iso()),
            )
        add_audit(conn, store_code, "planogram", str(planogram_id), "CREATE_VERSION", actor, None, {"version": version, "placed": len(products), "unplaced": len(unplaced)})
    return {"status": "success", "store_code": store_code, "version": version, "id": planogram_id, "placed_count": len(products), "unplaced_count": len(unplaced)}


@router.get("/planograms/{store_code}/latest")
def get_latest_planogram(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM planogram_versions WHERE store_code=? ORDER BY id DESC LIMIT 1", (store_code,)).fetchone()
    return {"status": "success" if row else "empty", "store_code": store_code, "planogram": public_planogram(row)}


@router.get("/planograms/{store_code}/versions")
def list_planogram_versions(store_code: str, limit: int = 50):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT id, store_code, version, placed_count, unplaced_count, created_at, created_by, note, is_active FROM planogram_versions WHERE store_code=? ORDER BY id DESC LIMIT ?", (store_code, limit)).fetchall()
    return {"status": "success", "store_code": store_code, "versions": [row_to_dict(r) for r in rows]}


@router.get("/tasks")
def list_tasks(store_code: Optional[str] = None, status: Optional[str] = None):
    init_db()
    params = []
    where = []
    if store_code:
        where.append("store_code IN (?, 'ALL')")
        params.append(clean_store(store_code))
    if status:
        where.append("status=?")
        params.append(status)
    sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT 500"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"status": "success", "tasks": [public_task(r) for r in rows]}


@router.post("/tasks")
def create_task(payload: Dict[str, Any] = Body(...)):
    store_code = clean_store(payload.get("store_code") or payload.get("store") or "ALL")
    title = payload.get("title") or "Yeni görev"
    init_db()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks(external_id, store_code, title, owner, priority, deadline, status, payload, response, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload.get("external_id") or payload.get("id"), store_code, title, payload.get("owner"), payload.get("priority"), payload.get("deadline"), payload.get("status") or "Open", dumps(payload), payload.get("response"), now_iso(), now_iso()),
        )
        add_audit(conn, store_code, "task", str(cur.lastrowid), "CREATE", payload.get("actor") or "frontend", None, payload)
    return {"status": "success", "id": cur.lastrowid}


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, payload: Dict[str, Any] = Body(...)):
    init_db()
    with connect() as conn:
        before = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not before:
            return {"status": "error", "message": "Görev bulunamadı."}
        merged_payload = {**loads(before["payload"], {}), **payload}
        conn.execute(
            """
            UPDATE tasks SET title=?, owner=?, priority=?, deadline=?, status=?, payload=?, response=?, updated_at=? WHERE id=?
            """,
            (
                payload.get("title", before["title"]),
                payload.get("owner", before["owner"]),
                payload.get("priority", before["priority"]),
                payload.get("deadline", before["deadline"]),
                payload.get("status", before["status"]),
                dumps(merged_payload),
                payload.get("response", before["response"]),
                now_iso(),
                task_id,
            ),
        )
        add_audit(conn, before["store_code"], "task", str(task_id), "UPDATE", payload.get("actor") or "frontend", public_task(before), merged_payload)
    return {"status": "success", "id": task_id}


@router.post("/evidence/upload")
async def upload_evidence(
    file: Optional[UploadFile] = File(None),
    store_code: str = "AUTO",
    planogram_version: str = "",
    corridor: str = "",
    module: str = "",
    shelf: str = "",
    uploader: str = "frontend",
    description: str = "",
):
    store_code = clean_store(store_code)
    file_name = None
    file_path = None
    if file:
        evidence_dir = Path(__file__).resolve().parent / "data" / "evidence" / store_code
        evidence_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{now_iso().replace(':','-')}_{file.filename}"
        target = evidence_dir / safe_name
        target.write_bytes(await file.read())
        file_name = file.filename
        file_path = str(target)
    payload = {"store_code": store_code, "planogram_version": planogram_version, "corridor": corridor, "module": module, "shelf": shelf, "uploader": uploader, "description": description, "file_name": file_name, "file_path": file_path}
    init_db()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO photo_evidence(store_code, planogram_version, corridor, module, shelf, uploader, description, file_name, file_path, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (store_code, planogram_version, corridor, module, shelf, uploader, description, file_name, file_path, dumps(payload), now_iso()),
        )
        add_audit(conn, store_code, "photo_evidence", str(cur.lastrowid), "UPLOAD", uploader, None, payload)
    return {"status": "success", "id": cur.lastrowid, **payload}


@router.get("/evidence/{store_code}")
def list_evidence(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM photo_evidence WHERE store_code=? ORDER BY id DESC LIMIT 300", (store_code,)).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["payload"] = loads(d.get("payload"), {})
        out.append(d)
    return {"status": "success", "store_code": store_code, "evidence": out}


@router.get("/audit/{store_code}")
def list_audit(store_code: str, limit: int = 200):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log WHERE store_code=? ORDER BY id DESC LIMIT ?", (store_code, limit)).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["before_payload"] = loads(d.get("before_payload"), None)
        d["after_payload"] = loads(d.get("after_payload"), None)
        out.append(d)
    return {"status": "success", "store_code": store_code, "audit": out}
