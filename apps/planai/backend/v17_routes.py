from __future__ import annotations

from io import StringIO, BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import csv
import pandas as pd
from fastapi import APIRouter, Body, File, UploadFile
from fastapi.responses import StreamingResponse

from db import add_audit, connect, dumps, init_db, loads, now_iso, row_to_dict
from services.abc_service import abc_service
from services.catalog_service import catalog_service
from services.merge_service import merge_service
from services.store_dna_service import store_dna_service
from services.planogram_engine import planogram_engine
from services.fixture_catalog import list_fixture_catalog
from services.fixture_pool_builder import summarize_pools

router = APIRouter(tags=["plonagram-v17"])


CATALOG_FILE_CANDIDATES = [
    "catalog_export.csv", "master_products.csv", "backend_master_products.csv",
    "catalog.csv", "product_catalog.csv", "products_master.csv"
]

def _catalog_count_for(conn, store_code: str) -> int:
    return int(conn.execute("SELECT COUNT(*) AS c FROM catalog_products WHERE store_code=?", (store_code,)).fetchone()["c"])

def _find_embedded_catalog_file() -> Optional[Path]:
    base = Path(__file__).resolve().parent
    search_dirs = [base / "data", base.parent / "data", Path.cwd() / "data"]
    for d in search_dirs:
        for name in CATALOG_FILE_CANDIDATES:
            p = d / name
            if p.exists() and p.is_file():
                return p
    return None

def _persist_catalog_products(conn, store_code: str, products: List[Dict[str, Any]]):
    for p in products:
        sku = str(p.get("sku") or p.get("barcode") or "").strip()
        if not sku:
            continue
        conn.execute(
            """
            INSERT INTO catalog_products(store_code, sku, barcode, product_name, brand, category_l1, category_l2, storage_type, width_cm, height_cm, depth_cm, weight_kg, image_url, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(store_code, sku) DO UPDATE SET
                barcode=excluded.barcode, product_name=excluded.product_name, brand=excluded.brand,
                category_l1=excluded.category_l1, category_l2=excluded.category_l2, storage_type=excluded.storage_type,
                width_cm=excluded.width_cm, height_cm=excluded.height_cm, depth_cm=excluded.depth_cm,
                weight_kg=excluded.weight_kg, image_url=excluded.image_url, payload=excluded.payload, updated_at=excluded.updated_at
            """,
            (store_code, sku, p.get("barcode"), p.get("product_name"), p.get("brand"), p.get("category_l1"), p.get("category_l2"), p.get("storage_type"), p.get("width_cm"), p.get("height_cm"), p.get("depth_cm"), p.get("weight_kg"), p.get("image_url"), dumps(p), now_iso(), now_iso()),
        )

def ensure_embedded_catalog(store_code: str) -> Dict[str, Any]:
    """Load the bundled/global catalog automatically. Stores never need to upload catalog manually."""
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        if _catalog_count_for(conn, store_code) > 0:
            return {"loaded": False, "reason": "already_loaded", "total": _catalog_count_for(conn, store_code)}

    catalog_path = _find_embedded_catalog_file()
    if not catalog_path:
        return {"loaded": False, "reason": "embedded_catalog_file_not_found", "total": 0}

    result = catalog_service.import_from_file(catalog_path.read_bytes(), catalog_path.name, store_code)
    quality = catalog_service.validate_catalog_quality(result.get("products", []))
    with connect() as conn:
        _persist_catalog_products(conn, store_code, result.get("products", []))
        add_audit(conn, store_code, "catalog", store_code, "AUTOLOAD_EMBEDDED", "system", None, {"file": catalog_path.name, "products": len(result.get("products", [])), "quality_score": quality.get("quality_score")})
        total = _catalog_count_for(conn, store_code)
    return {"loaded": True, "file": catalog_path.name, "total": total, "quality": quality}


@router.get("/fixture-catalog")
def fixture_catalog():
    return {"status": "success", "fixtures": list_fixture_catalog()}


def clean_store(store_code: str) -> str:
    return str(store_code or "AUTO").strip().upper()


def _version(prefix: str, store_code: str) -> str:
    return f"{prefix}_{clean_store(store_code)}_{now_iso().replace(':','-').replace('.','_')}"


def _json(row, field="payload", default=None):
    if not row:
        return default
    return loads(row[field], default)


def _get_latest_abc_items(conn, store_code: str):
    report = conn.execute("SELECT * FROM abc_reports WHERE store_code=? ORDER BY id DESC LIMIT 1", (store_code,)).fetchone()
    if not report:
        return None, []
    rows = conn.execute("SELECT payload FROM abc_items WHERE report_id=? ORDER BY rank ASC, id ASC", (report["id"],)).fetchall()
    return report, [loads(r["payload"], {}) for r in rows]


def _get_catalog_products(conn, store_code: str):
    rows = conn.execute("SELECT payload FROM catalog_products WHERE store_code=? ORDER BY product_name COLLATE NOCASE", (store_code,)).fetchall()
    return [loads(r["payload"], {}) for r in rows]


@router.get("/stores/{store_code}/readiness")
def store_readiness(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    catalog_bootstrap = ensure_embedded_catalog(store_code)
    with connect() as conn:
        dna = conn.execute("SELECT store_code FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
        abc = conn.execute("SELECT id,total_items FROM abc_reports WHERE store_code=? ORDER BY id DESC LIMIT 1", (store_code,)).fetchone()
        catalog_count = conn.execute("SELECT COUNT(*) AS c FROM catalog_products WHERE store_code=?", (store_code,)).fetchone()["c"]
        merged_count = conn.execute("SELECT COUNT(*) AS c FROM merged_products WHERE store_code=?", (store_code,)).fetchone()["c"]
    missing = []
    if not dna:
        missing.append("store_dna")
    if not abc:
        missing.append("abc_report")
    if catalog_count == 0:
        missing.append("catalog")
    if merged_count == 0 and abc and catalog_count:
        missing.append("abc_catalog_merge")
    return {
        "status": "success",
        "store_code": store_code,
        "ready_for_planogram": len(missing) == 0,
        "missing": missing,
        "dna_exists": bool(dna),
        "abc_items": int(abc["total_items"]) if abc else 0,
        "catalog_products": catalog_count,
        "catalog_bootstrap": catalog_bootstrap,
        "merged_products": merged_count,
    }


@router.post("/stores/{store_code}/dna/generate-easy")
def generate_dna_easy(store_code: str, payload: Dict[str, Any] = Body(...)):
    """Generate and persist Store DNA from the easier wizard flow."""
    store_code = clean_store(store_code)
    payload = {**payload, "store_code": store_code, "store_name": payload.get("store_name") or store_code}
    dna = store_dna_service.build_from_wizard_easy(payload)
    is_valid, errors = store_dna_service.validate_dna(dna)
    if not is_valid:
        return {"status": "error", "message": "Store DNA doğrulaması başarısız.", "errors": errors}
    init_db()
    with connect() as conn:
        before = conn.execute("SELECT payload FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
        conn.execute(
            """
            INSERT INTO store_dna(store_code, payload, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(store_code) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at, updated_by=excluded.updated_by
            """,
            (store_code, dumps(dna), now_iso(), payload.get("updated_by") or "store_dna_wizard"),
        )
        add_audit(conn, store_code, "store_dna", store_code, "GENERATE_EASY", payload.get("updated_by") or "store_dna_wizard", loads(before["payload"], {}) if before else None, dna)
    return {"status": "success", "store_code": store_code, "dna": dna, "message": "Store DNA kolay kurulum ile oluşturuldu ve kaydedildi."}


@router.post("/stores/{store_code}/dna/generate-template")
def generate_dna_template(store_code: str, payload: Dict[str, Any] = Body(...)):
    store_code = clean_store(store_code)
    template_id = payload.get("template_id") or "retail_warehouse"
    store_name = payload.get("store_name") or store_code
    dna = store_dna_service.build_from_template(template_id, store_code, store_name, payload.get("overrides") or {})
    is_valid, errors = store_dna_service.validate_dna(dna)
    if not is_valid:
        return {"status": "error", "message": "Store DNA doğrulaması başarısız.", "errors": errors}
    init_db()
    with connect() as conn:
        before = conn.execute("SELECT payload FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
        conn.execute(
            """
            INSERT INTO store_dna(store_code, payload, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(store_code) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at, updated_by=excluded.updated_by
            """,
            (store_code, dumps(dna), now_iso(), payload.get("updated_by") or "template_wizard"),
        )
        add_audit(conn, store_code, "store_dna", store_code, "GENERATE_TEMPLATE", payload.get("updated_by") or "template_wizard", loads(before["payload"], {}) if before else None, dna)
    return {"status": "success", "store_code": store_code, "dna": dna, "message": f"{template_id} şablonu uygulandı ve kaydedildi."}


@router.get("/stores/{store_code}/dna/fixture-pools")
def get_fixture_pools(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT payload FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
    if not row:
        return {"status": "error", "message": "Store DNA bulunamadı.", "fixture_pools": {}}
    dna = loads(row["payload"], {})
    pools = store_dna_service.get_fixture_pools_from_dna(dna)
    return {"status": "success", "store_code": store_code, "fixture_pools": pools, "summary": summarize_pools(pools)}


@router.post("/abc/upload")
async def upload_abc(file: UploadFile = File(...), store_code: str = "AUTO"):
    store_code = clean_store(store_code)
    content = await file.read()
    result = abc_service.import_from_file(content, file.filename or "abc.csv", store_code)
    version = _version("ABC", store_code)
    init_db()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO abc_reports(store_code, report_version, uploaded_at, total_items, payload) VALUES (?, ?, ?, ?, ?)",
            (store_code, version, now_iso(), result.get("total_count", len(result.get("items", []))), dumps(result)),
        )
        report_id = cur.lastrowid
        for item in result.get("items", []):
            conn.execute(
                """
                INSERT INTO abc_items(report_id, store_code, sku, product_name, sales_qty_7d, percent_orders, percent_stops, abc_class, rank, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, store_code, item.get("sku"), item.get("product_name"), item.get("sales_qty_7d"), item.get("percent_orders"), item.get("percent_stops"), item.get("abc_class"), item.get("rank"), dumps(item)),
            )
        add_audit(conn, store_code, "abc_report", str(report_id), "UPLOAD", "frontend", None, {"version": version, "total": result.get("total_count")})
    return {"status": "success", "store_code": store_code, "report_id": report_id, "version": version, "summary": result.get("summary", {}), "errors": result.get("errors", [])[:20], "total_errors": len(result.get("errors", []))}


@router.get("/abc/{store_code}/latest")
def latest_abc(store_code: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        report, items = _get_latest_abc_items(conn, store_code)
    if not report:
        return {"status": "empty", "store_code": store_code, "items": []}
    d = row_to_dict(report)
    d["payload"] = loads(d.get("payload"), {})
    return {"status": "success", "store_code": store_code, "report": d, "items": items[:1000], "total_items": len(items)}


@router.post("/catalog/upload")
async def upload_catalog(file: UploadFile = File(...), store_code: str = "AUTO"):
    store_code = clean_store(store_code)
    content = await file.read()
    result = catalog_service.import_from_file(content, file.filename or "catalog.csv", store_code)
    quality = catalog_service.validate_catalog_quality(result.get("products", []))
    init_db()
    with connect() as conn:
        _persist_catalog_products(conn, store_code, result.get("products", []))
        add_audit(conn, store_code, "catalog", store_code, "UPLOAD", "frontend", None, {"products": len(result.get("products", [])), "quality_score": quality.get("quality_score")})
    return {"status": "success", "store_code": store_code, "summary": result.get("summary", {}), "quality": quality, "errors": result.get("errors", [])[:20], "total_errors": len(result.get("errors", []))}


@router.get("/catalog/status")
def catalog_status(store_code: str = "AUTO"):
    store_code = clean_store(store_code)
    init_db()
    catalog_bootstrap = ensure_embedded_catalog(store_code)
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM catalog_products WHERE store_code=?", (store_code,)).fetchone()["c"]
        with_image = conn.execute("SELECT COUNT(*) AS c FROM catalog_products WHERE store_code=? AND image_url IS NOT NULL AND image_url != ''", (store_code,)).fetchone()["c"]
        with_dims = conn.execute("SELECT COUNT(*) AS c FROM catalog_products WHERE store_code=? AND width_cm IS NOT NULL AND height_cm IS NOT NULL AND depth_cm IS NOT NULL", (store_code,)).fetchone()["c"]
    return {"status": "success", "store_code": store_code, "total": total, "with_image": with_image, "with_dimensions": with_dims, "catalog_bootstrap": catalog_bootstrap}


@router.get("/catalog/search")
def catalog_search(store_code: str = "AUTO", q: str = "", limit: int = 100):
    store_code = clean_store(store_code)
    like = f"%{q.strip()}%"
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM catalog_products
            WHERE store_code=? AND (?='' OR sku LIKE ? OR product_name LIKE ? OR brand LIKE ? OR category_l2 LIKE ?)
            ORDER BY product_name COLLATE NOCASE LIMIT ?
            """,
            (store_code, q.strip(), like, like, like, like, max(1, min(limit, 500))),
        ).fetchall()
    return {"status": "success", "store_code": store_code, "products": [loads(r["payload"], {}) for r in rows]}


@router.post("/products/merge")
def merge_products(payload: Dict[str, Any] = Body(...)):
    store_code = clean_store(payload.get("store_code") or "AUTO")
    init_db()
    ensure_embedded_catalog(store_code)
    with connect() as conn:
        report, abc_items = _get_latest_abc_items(conn, store_code)
        catalog_items = _get_catalog_products(conn, store_code)
    if not report:
        return {"status": "error", "message": "ABC raporu bulunamadı."}
    if not catalog_items:
        return {"status": "error", "message": "Catalog data bulunamadı."}
    result = merge_service.merge_abc_catalog(abc_items, catalog_items)
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM merged_products WHERE store_code=?", (store_code,))
        for p in result.get("merged_products", []):
            conn.execute(
                """
                INSERT INTO merged_products(store_code, sku, match_method, match_confidence, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(store_code, sku) DO UPDATE SET match_method=excluded.match_method, match_confidence=excluded.match_confidence, payload=excluded.payload, updated_at=excluded.updated_at
                """,
                (store_code, p.get("sku"), p.get("_match_method"), p.get("_match_confidence"), dumps(p), now_iso(), now_iso()),
            )
        add_audit(conn, store_code, "merged_products", store_code, "MERGE", "frontend", None, result.get("summary"))
    return {"status": "success", "store_code": store_code, **result}


@router.get("/products/merged/{store_code}")
def get_merged_products(store_code: str, limit: int = 20000):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM merged_products WHERE store_code=? ORDER BY match_confidence DESC LIMIT ?", (store_code, max(1, min(limit, 50000)))).fetchall()
    products = [loads(r["payload"], {}) for r in rows]
    return {"status": "success", "store_code": store_code, "products": products, "total": len(products)}


@router.post("/planograms/{store_code}/generate-fixture-first")
def generate_fixture_first_planogram(store_code: str, payload: Dict[str, Any] = Body(default_factory=dict)):
    """Generate a fixture-first planogram from Store DNA + merged ABC/Catalog products."""
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        dna_row = conn.execute("SELECT payload FROM store_dna WHERE store_code=?", (store_code,)).fetchone()
        if not dna_row:
            return {"status": "error", "message": "Store DNA bulunamadı. Planogram üretmeden önce Depo Kurulumu yapılmalı."}
        product_rows = conn.execute("SELECT payload FROM merged_products WHERE store_code=? ORDER BY match_confidence DESC", (store_code,)).fetchall()
        if not product_rows:
            return {"status": "error", "message": "Merged ürün bulunamadı. Önce ABC + Catalog merge çalıştırılmalı."}
        dna = loads(dna_row["payload"], {})
        products = [loads(r["payload"], {}) for r in product_rows]

    fixture_pools = store_dna_service.get_fixture_pools_from_dna(dna)
    result = planogram_engine.generate_planogram(products, fixture_pools)
    version = _version("FIXTURE_FIRST", store_code)
    result_payload = {
        "version": version,
        "store_code": store_code,
        "engine": "physics_first_v1_7_4",
        "placements": result.get("placements", []),
        "unplaced": result.get("unplaced", []),
        "summary": result.get("summary", {}),
        "utilization": result.get("utilization", {}),
    }
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO planogram_versions(store_code, version, payload, summary, unplaced_count, placed_count, created_at, created_by, note, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                store_code,
                version,
                dumps(result_payload),
                dumps(result.get("summary", {})),
                int(result.get("summary", {}).get("unplaced", len(result.get("unplaced", [])))),
                int(result.get("summary", {}).get("placed", len(result.get("placements", [])))),
                now_iso(),
                payload.get("actor") or "fixture_first_engine",
                payload.get("note") or "Fixture-first planogram generated",
            ),
        )
        planogram_id = cur.lastrowid
        for item in result.get("unplaced", []):
            conn.execute(
                """
                INSERT INTO unplaced_products(store_code, planogram_version_id, version, sku, product_name, reason, suggested_action, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    store_code,
                    planogram_id,
                    version,
                    item.get("sku"),
                    item.get("product_name"),
                    item.get("_unplaced_reason") or item.get("reason"),
                    item.get("suggested_action"),
                    dumps(item),
                    now_iso(),
                ),
            )
        add_audit(conn, store_code, "planogram", str(planogram_id), "GENERATE_FIXTURE_FIRST", payload.get("actor") or "fixture_first_engine", None, result.get("summary"))
    return {"status": "success", "store_code": store_code, "version": version, "planogram_id": planogram_id, **result_payload}


def _unplaced_from_planogram(conn, store_code: str, version_or_id: str) -> List[Dict[str, Any]]:
    row = None
    if str(version_or_id).isdigit():
        row = conn.execute("SELECT payload FROM planogram_versions WHERE store_code=? AND id=?", (store_code, int(version_or_id))).fetchone()
    if not row:
        row = conn.execute("SELECT payload FROM planogram_versions WHERE store_code=? AND version=?", (store_code, version_or_id)).fetchone()
    if not row:
        row = conn.execute("SELECT payload FROM planogram_versions WHERE store_code=? ORDER BY id DESC LIMIT 1", (store_code,)).fetchone()
    payload = loads(row["payload"], {}) if row else {}
    return payload.get("unplacedProducts") or payload.get("unplaced_products") or payload.get("unplaced") or []


@router.get("/unplaced/{store_code}/{version_id}")
def get_unplaced(store_code: str, version_id: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        items = _unplaced_from_planogram(conn, store_code, version_id)
    return {"status": "success", "store_code": store_code, "version_id": version_id, "unplaced": items, "total": len(items)}


@router.get("/unplaced/{store_code}/{version_id}/csv")
def export_unplaced_csv(store_code: str, version_id: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        items = _unplaced_from_planogram(conn, store_code, version_id)
    out = StringIO()
    fields = ["sku", "product_name", "brand", "category_l1", "category_l2", "storage_class", "merch_group", "reason_code", "reason", "human_action", "suggested_action", "required_width_cm", "available_width_cm", "missing_fixture_type"]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow(item)
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=unplaced_{store_code}_{version_id}.csv"})


@router.get("/unplaced/{store_code}/{version_id}/xlsx")
def export_unplaced_xlsx(store_code: str, version_id: str):
    store_code = clean_store(store_code)
    init_db()
    with connect() as conn:
        items = _unplaced_from_planogram(conn, store_code, version_id)
    df = pd.DataFrame(items)
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Unplaced")
    bio.seek(0)
    return StreamingResponse(bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=unplaced_{store_code}_{version_id}.xlsx"})
