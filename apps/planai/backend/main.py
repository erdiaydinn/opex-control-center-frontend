from fastapi import FastAPI, UploadFile, File, Body, Query, HTTPException, Response, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import pandas as pd
import io
import copy
import csv
import json
import time
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Core V1 router imports are optional-safe: backend can boot even if a module is missing during local setup.
try:
    from auth_routes import router as auth_router
except Exception:
    auth_router = None

try:
    from routers.store_master_routes import router as store_master_router
    from routers.depot_dna_routes import router as depot_dna_router
    from routers.layout_routes import router as layout_router
    from routers.object_library_routes import router as object_library_router
    from routers.intelligence_routes import router as intelligence_router
except Exception:
    store_master_router = None
    depot_dna_router = None
    layout_router = None
    object_library_router = None
    intelligence_router = None

from engine import (
    load_master,
    generate_default_layout,
    generate_planogram,
    run_engine,
    enrich_product,
    validate_planogram,
    optimize_picking_route,
    add_product_to_shelf as engine_add_product_to_shelf,
    update_facing as engine_update_facing,
    rotate_product as engine_rotate_product,
    move_product as engine_move_product,
    remove_product_from_plan,
    recalc_plan,
    apply_module_rule as engine_apply_module_rule,
    apply_shelf_rule as engine_apply_shelf_rule,
    suggest_empty_space as engine_suggest_empty_space,
    commit_block_studio as engine_commit_block_studio,
    optimize_shelf as engine_optimize_shelf,
    optimize_module as engine_optimize_module,
    find_product,
    find_shelf,
    make_shelves,
    DEFAULT_SCORING_CONFIG,
)

from audit_store import init_audit_db, list_audit_logs, write_audit
from change_request_store import (
    create_change_request,
    get_change_request,
    init_change_db,
    list_change_requests,
    review_change_request,
)
from security import authenticate_authorization, ensure_store_access, get_current_user, require_action, require_roles
from equipment_library import EQUIPMENT, equipment_to_layout_object, get_equipment, list_equipment
from rule_catalog import RULE_CATALOG, scoring_config_with_defaults, validate_rule_payload

try:
    from dxf_parser_smart import parse_dxf_to_layout_smart
except Exception:
    parse_dxf_to_layout_smart = None

app = FastAPI(title="Plonagram Premium Backend")

init_audit_db()
init_change_db()

# =====================================================
# ROUTERS / MODULAR CORE
# =====================================================
# Auth
if auth_router:
    app.include_router(auth_router)

# Core V1 platform routers
for _router in [
    store_master_router,
    depot_dna_router,
    layout_router,
    object_library_router,
    intelligence_router,
]:
    if _router:
        app.include_router(_router)

try:
    from master_products_api import router as master_products_router
    app.include_router(master_products_router)
except Exception:
    pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "PLONAGRAM_ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    public_paths = {
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/default-layout",
        "/rules/catalog",
    }
    public_prefixes = (
        "/auth/login",
        "/auth/register",
        "/auth/forgot-password",
        "/auth/stores",
        "/auth/opex-dev-exchange",
    )
    if request.method != "OPTIONS" and request.url.path not in public_paths and not request.url.path.startswith(public_prefixes):
        request.state.user = authenticate_authorization(request.headers.get("Authorization"))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

MAX_UPLOAD_BYTES = int(os.getenv("PLONAGRAM_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


def _actor(value: Any = None) -> str:
    if isinstance(value, dict):
        return str(value.get("actor") or value.get("username") or value.get("requested_by") or "system")
    return str(value or "system")


def _audit(action: str, *, actor: Any = None, store_code: Any = None, entity_type: str = "", entity_id: Any = None, request_id: Any = None, before: Any = None, after: Any = None, metadata: Any = None) -> None:
    """Write a compact, queryable audit event for every state-changing action."""
    try:
        write_audit(
            action,
            actor=_actor(actor),
            store_code=str(store_code) if store_code else None,
            entity_type=entity_type or None,
            entity_id=entity_id,
            request_id=str(request_id) if request_id else None,
            before=before,
            after=after,
            metadata=metadata,
        )
    except Exception as exc:
        print(f"[AUDIT_WARNING] {action}: {exc}")


def _plan_snapshot(plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep audit rows useful without copying thousands of SKU objects."""
    if not isinstance(plan, dict):
        return {"present": False}
    aisles = plan.get("aisles", []) or []
    shelves = [s for a in aisles for m in a.get("modules", []) for s in m.get("shelves", [])]
    products = [p for s in shelves for p in s.get("products", [])]
    return {
        "present": True,
        "store_code": plan.get("store_code"),
        "aisle_count": len(aisles),
        "shelf_count": len(shelves),
        "placed_sku_count": len(products),
        "sku_sample": [str(p.get("sku")) for p in products[:10]],
    }


# =====================================================
# MODELS
# =====================================================

class GenerateRequest(BaseModel):
    products: List[Dict[str, Any]]
    layout: Optional[Dict[str, Any]] = None
    mode: Optional[str] = "HYBRID"
    brand_side_rules: Optional[Dict[str, str]] = None
    scoring_config: Optional[Dict[str, float]] = None
    allow_ai_dimensions: Optional[bool] = True
    actor: Optional[str] = "system"
    store_code: Optional[str] = None
    request_id: Optional[str] = None


class PlanRequest(BaseModel):
    planogram: Dict[str, Any]


class RouteRequest(BaseModel):
    planogram: Dict[str, Any]
    order_skus: List[str]


class MoveRequest(BaseModel):
    planogram: Dict[str, Any]
    sku: str
    target_aisle_id: str
    target_module_id: int
    target_shelf_no: int
    force: Optional[bool] = False


class FacingRequest(BaseModel):
    planogram: Dict[str, Any]
    sku: str
    delta: int


class RotateRequest(BaseModel):
    planogram: Dict[str, Any]
    sku: str


class RemoveProductRequest(BaseModel):
    planogram: Dict[str, Any]
    sku: str


class AddProductToShelfRequest(BaseModel):
    planogram: Dict[str, Any]
    product: Dict[str, Any]
    target_aisle_id: str
    target_module_id: int
    target_shelf_no: int
    force: Optional[bool] = False


class RuleRequest(BaseModel):
    layout: Dict[str, Any]
    aisle_id: str
    module_id: Optional[int] = None
    shelf_no: Optional[int] = None
    rule: Dict[str, Any]


class SuggestRequest(BaseModel):
    planogram: Dict[str, Any]
    products: List[Dict[str, Any]]
    aisle_id: str
    module_id: int
    shelf_no: int
    limit: Optional[int] = 30


class BlockStudioCommitRequest(BaseModel):
    planogram: Dict[str, Any]
    aisle_id: str
    module_id: int
    shelf_no: int
    blocks: List[Dict[str, Any]]


class ReorderShelfRequest(BaseModel):
    planogram: Dict[str, Any]
    aisle_id: str
    module_id: int
    shelf_no: int
    sku_order: List[str]


class SelectedModulesRequest(BaseModel):
    products: List[Dict[str, Any]]
    layout: Dict[str, Any]
    selected_modules: List[Dict[str, Any]]
    mode: Optional[str] = "HYBRID"
    brand_side_rules: Optional[Dict[str, str]] = None
    scoring_config: Optional[Dict[str, float]] = None
    allow_ai_dimensions: Optional[bool] = True


class DimensionChangeRequest(BaseModel):
    sku: str
    product_name: Optional[str] = None
    old: Dict[str, Any]
    new: Dict[str, Any]
    requested_by: Optional[str] = "user"
    reason: Optional[str] = ""


class ApproveDimensionRequest(BaseModel):
    request_id: int
    approve: bool
    planogram: Optional[Dict[str, Any]] = None


class RuleValidationRequest(BaseModel):
    rule: Dict[str, Any] = {}


class ScoringConfigRequest(BaseModel):
    scoring_config: Dict[str, Any] = {}


class EquipmentObjectRequest(BaseModel):
    equipment_id: str
    object_id: Optional[str] = None
    x: Optional[float] = 0
    y: Optional[float] = 0


def _layout_has_module(layout: Dict[str, Any], aisle_id: str, module_id: int) -> bool:
    for aisle in (layout or {}).get("aisles", []):
        if str(aisle.get("aisle_id")) != str(aisle_id):
            continue
        for module in aisle.get("modules", []):
            try:
                if int(module.get("module_id", -1)) == int(module_id):
                    return True
            except (TypeError, ValueError):
                continue
        return False
    return False


def _layout_has_shelf(layout: Dict[str, Any], aisle_id: str, module_id: int, shelf_no: int) -> bool:
    return find_shelf(layout or {}, aisle_id, module_id, shelf_no)[2] is not None


# =====================================================
# HEALTH / MASTER / LAYOUT
# =====================================================

@app.get("/")
def health():
    master = load_master()
    return {
        "status": "ok",
        "service": "Plonagram Premium Backend",
        "engine_version": "deterministic-best-fit-v4.2",
        "single_source_of_truth": "/generate-planogram",
        "compat_fast_path": "/generate-planogram-fast",
        "master_loaded": master["loaded"],
        "master_rows": len(master["rows"]),
        "audit_log": True,
        "equipment_library": True,
    }


@app.get("/default-layout")
def default_layout():
    return generate_default_layout()


# =====================================================
# RULE CATALOG / EQUIPMENT / AUDIT CONTRACTS
# =====================================================

@app.get("/rules/catalog")
def rules_catalog():
    return {
        "status": "success",
        "catalog": RULE_CATALOG,
        "default_scoring_config": DEFAULT_SCORING_CONFIG,
    }


@app.post("/rules/validate")
def rules_validate(req: RuleValidationRequest):
    return {"status": "success", **validate_rule_payload(req.rule)}


@app.post("/rules/normalize-scoring")
def rules_normalize_scoring(req: ScoringConfigRequest, current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER", "REGIONAL_MANAGER"))):
    normalized = scoring_config_with_defaults(req.scoring_config)
    _audit("scoring_config_updated", actor=current_user, entity_type="rule_config", after=normalized)
    return {"status": "success", "scoring_config": normalized}


@app.get("/equipment-library")
def equipment_library(query: str = "", storage_type: str = "", limit: int = Query(200, ge=1, le=500)):
    rows = list_equipment(query=query, storage_type=storage_type)[:limit]
    return {
        "status": "success",
        "total": len(rows),
        "equipment": rows,
        "downloads": {
            "json": "/equipment-library/download?format=json",
            "csv": "/equipment-library/download?format=csv",
        },
    }


@app.post("/equipment-library/object")
def equipment_object(req: EquipmentObjectRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    item = get_equipment(req.equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ekipman bulunamadı.")
    object_id = req.object_id or f"{req.equipment_id}-object"
    result = equipment_to_layout_object(item, object_id=object_id, x=req.x or 0, y=req.y or 0)
    _audit("equipment_object_created", actor=current_user, entity_type="layout_object", entity_id=object_id, after=result, metadata={"equipment_id": req.equipment_id})
    return {"status": "success", "object": result}


@app.get("/equipment-library/download")
def equipment_download(format: str = Query("json", pattern="^(json|csv)$"), current_user: Dict[str, Any] = Depends(get_current_user)):
    rows = list_equipment()
    if format == "csv":
        buffer = io.StringIO()
        fields = ["equipment_id", "name", "name_en", "type", "storage_type", "module_width_cm", "module_depth_cm", "module_height_cm", "shelf_count", "shelf_height_cm", "max_weight_kg", "supported_depots"]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                field: ", ".join(row.get(field, [])) if field == "supported_depots" else row.get(field, "")
                for field in fields
            })
        body = buffer.getvalue().encode("utf-8-sig")
        media_type = "text/csv; charset=utf-8"
        filename = "plonagram-equipment-library.csv"
    else:
        body = json.dumps({"version": "1.0", "equipment": rows}, ensure_ascii=False, indent=2).encode("utf-8")
        media_type = "application/json"
        filename = "plonagram-equipment-library.json"
    _audit("equipment_library_downloaded", actor=current_user, entity_type="equipment_library", metadata={"format": format, "count": len(rows)})
    return Response(content=body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/equipment-library/{equipment_id}")
def equipment_item(equipment_id: str):
    item = get_equipment(equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ekipman bulunamadı.")
    return {"status": "success", "equipment": item}


@app.get("/audit-logs")
def audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: str = "",
    actor: str = "",
    store_code: str = "",
    entity_type: str = "",
    request_id: str = "",
    created_from: str = "",
    created_to: str = "",
    current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER", "REGIONAL_MANAGER")),
):
    return {"status": "success", **list_audit_logs(
        limit=limit,
        offset=offset,
        action=action,
        actor=actor,
        store_code=store_code,
        entity_type=entity_type,
        request_id=request_id,
        created_from=created_from,
        created_to=created_to,
    )}


@app.get("/audit-log")
def audit_log_alias(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER", "REGIONAL_MANAGER")),
):
    return {"status": "success", **list_audit_logs(limit=limit, offset=offset)}


@app.post("/reload-master")
def reload_master(current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER"))):
    master = load_master(force=True)
    result = {
        "status": "ok",
        "rows": len(master["rows"]),
        "by_sku": len(master["by_sku"]),
        "by_barcode": len(master["by_barcode"]),
        "by_catalog": len(master["by_catalog"]),
        "by_pim": len(master["by_pim"]),
        "by_key": len(master["by_key"]),
    }
    _audit("master_reloaded", actor=current_user, entity_type="master_products", after=result)
    return result


# =====================================================
# UPLOAD / PRODUCT ENRICHMENT
# =====================================================

@app.post("/upload-products-csv")
async def upload_products_csv(
    file: UploadFile = File(...),
    allow_ai_dimensions: bool = True,
    current_user: Dict[str, Any] = Depends(require_action("create")),
):
    filename = (file.filename or "").lower()
    if not filename.endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=415, detail="Yalnızca CSV/XLSX ürün dosyası kabul edilir.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Ürün dosyası {MAX_UPLOAD_BYTES // (1024 * 1024)} MB sınırını aşamaz.")

    if filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    else:
        try:
            df = pd.read_csv(io.BytesIO(content))
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")

    df = df.where(pd.notnull(df), None)
    rows = df.to_dict(orient="records")

    products = [
        enrich_product(r, allow_ai_dimensions=allow_ai_dimensions)
        for r in rows
    ]

    result = {
        "status": "success",
        "file_name": file.filename,
        "row_count": len(products),
        "columns": list(df.columns),
        "products": products,
        "master_matches": sum(1 for p in products if p.get("dimension_source") == "master"),
        "file_dimensions": sum(1 for p in products if p.get("dimension_source") == "file"),
        "ai_estimated": sum(1 for p in products if p.get("dimension_source") == "ai_estimated"),
        "missing_dimensions": sum(1 for p in products if p.get("dimension_source") == "missing"),
        "with_image": sum(1 for p in products if p.get("image_url")),
    }
    _audit("products_uploaded", actor=current_user, entity_type="product_catalog", entity_id=file.filename, after={k: result[k] for k in ("row_count", "master_matches", "file_dimensions", "ai_estimated", "missing_dimensions", "with_image")})
    return result


@app.post("/enrich-products")
def enrich_products(payload: Dict[str, Any] = Body(...)):
    products = payload.get("products", [])
    allow_ai_dimensions = payload.get("allow_ai_dimensions", True)

    enriched = [
        enrich_product(p, allow_ai_dimensions=allow_ai_dimensions)
        for p in products
    ]

    return {
        "status": "success",
        "count": len(enriched),
        "products": enriched,
    }


# =====================================================
# PLANOGRAM GENERATION
# =====================================================

@app.post("/generate-planogram")
def generate(req: GenerateRequest, current_user: Dict[str, Any] = Depends(require_action("create"))):
    ensure_store_access(current_user, req.store_code)
    started = time.perf_counter()
    result = generate_planogram(
        products=req.products,
        layout=req.layout or generate_default_layout(),
        mode=req.mode or "HYBRID",
        brand_side_rules=req.brand_side_rules,
        scoring_config=scoring_config_with_defaults(req.scoring_config),
        allow_ai_dimensions=req.allow_ai_dimensions,
    )
    result.setdefault("summary", {})["runtime_sec"] = round(time.perf_counter() - started, 3)
    _audit(
        "plan_generated",
        actor=current_user,
        store_code=req.store_code,
        entity_type="planogram",
        entity_id=req.store_code or "current",
        request_id=req.request_id,
        after=result.get("summary"),
        metadata={"mode": req.mode or "HYBRID", "product_count": len(req.products or []), "request_id": req.request_id},
    )
    return result


@app.post("/generate-planogram-fast")
def generate_fast(req: GenerateRequest, current_user: Dict[str, Any] = Depends(require_action("create"))):
    ensure_store_access(current_user, req.store_code)
    started = time.perf_counter()
    result = run_engine(
        products=req.products,
        layout=req.layout or generate_default_layout(),
        mode=req.mode or "HYBRID",
        brand_side_rules=req.brand_side_rules,
        scoring_config=scoring_config_with_defaults(req.scoring_config),
        allow_ai_dimensions=req.allow_ai_dimensions,
    )
    result.setdefault("summary", {})["runtime_sec"] = round(time.perf_counter() - started, 3)
    result.setdefault("summary", {})["execution_path"] = "deterministic_engine"
    _audit(
        "plan_generated_fast",
        actor=current_user,
        store_code=req.store_code,
        entity_type="planogram",
        entity_id=req.store_code or "current",
        request_id=req.request_id,
        after=result.get("summary"),
        metadata={"mode": req.mode or "HYBRID", "product_count": len(req.products or []), "request_id": req.request_id},
    )
    return result


@app.post("/generate-plan")
@app.post("/generate-planogram-one-click")
def generate_one_click(req: GenerateRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Short aliases for the primary action in the command center."""
    return generate(req, current_user)


@app.post("/score-planogram")
def score_planogram(req: PlanRequest):
    plan = copy.deepcopy(req.planogram)
    recalc_plan(plan)
    diagnostics = validate_planogram(plan)

    return {
        "status": "success",
        "diagnostics": diagnostics,
        "planogram": plan,
    }


@app.post("/planogram-diagnostics")
def planogram_diagnostics(req: PlanRequest):
    plan = copy.deepcopy(req.planogram)
    recalc_plan(plan)
    diagnostics = validate_planogram(plan)

    return {
        "status": "success",
        **diagnostics,
    }


@app.post("/validate-strict-rules")
def validate_strict_rules(req: PlanRequest):
    plan = copy.deepcopy(req.planogram)
    recalc_plan(plan)
    diagnostics = validate_planogram(plan)
    violations = diagnostics.get("strict_rule_violations", [])

    return {
        "status": "success",
        "violation_count": len(violations),
        "violations": violations,
        "diagnostics": diagnostics,
    }


# =====================================================
# PRODUCT ACTIONS
# =====================================================

@app.post("/update-facing")
def update_facing(req: FacingRequest, current_user: Dict[str, Any] = Depends(require_action("edit"))):
    result = engine_update_facing(
        plan=req.planogram,
        target_sku=req.sku,
        delta=req.delta,
    )
    _audit("facing_updated", actor=current_user, entity_type="sku", entity_id=req.sku, before=_plan_snapshot(req.planogram), after=_plan_snapshot(result.get("planogram")), metadata={"delta": req.delta})
    return result


@app.post("/rotate-product")
def rotate_product(req: RotateRequest, current_user: Dict[str, Any] = Depends(require_action("edit"))):
    result = engine_rotate_product(
        plan=req.planogram,
        target_sku=req.sku,
    )
    _audit("product_rotated", actor=current_user, entity_type="sku", entity_id=req.sku, before=_plan_snapshot(req.planogram), after=_plan_snapshot(result.get("planogram")))
    return result


@app.post("/move-product")
def move_product(req: MoveRequest, current_user: Dict[str, Any] = Depends(require_action("edit"))):
    result = engine_move_product(
        plan=req.planogram,
        target_sku=req.sku,
        aisle_id=req.target_aisle_id,
        module_id=req.target_module_id,
        shelf_no=req.target_shelf_no,
        force=req.force,
    )
    _audit("product_moved", actor=current_user, entity_type="sku", entity_id=req.sku, before=_plan_snapshot(req.planogram), after=_plan_snapshot(result.get("planogram")), metadata={"target_aisle_id": req.target_aisle_id, "target_module_id": req.target_module_id, "target_shelf_no": req.target_shelf_no, "force": req.force})
    return result


@app.post("/remove-product")
def remove_product(req: RemoveProductRequest, current_user: Dict[str, Any] = Depends(require_action("edit"))):
    plan = copy.deepcopy(req.planogram)
    removed = remove_product_from_plan(plan, req.sku)

    if not removed:
        return {
            "status": "error",
            "message": "SKU bulunamadı.",
            "planogram": plan,
        }

    recalc_plan(plan)

    result = {
        "status": "success",
        "removed_product": removed,
        "planogram": plan,
        "message": "Ürün raftan kaldırıldı.",
    }
    _audit("product_removed", actor=current_user, entity_type="sku", entity_id=req.sku, before=_plan_snapshot(req.planogram), after=_plan_snapshot(plan))
    return result


@app.post("/add-product-to-shelf")
def add_product_to_shelf(req: AddProductToShelfRequest, current_user: Dict[str, Any] = Depends(require_action("edit"))):
    result = engine_add_product_to_shelf(
        plan=req.planogram,
        product=req.product,
        aisle_id=req.target_aisle_id,
        module_id=req.target_module_id,
        shelf_no=req.target_shelf_no,
        force=req.force,
    )
    _audit("product_added_to_shelf", actor=current_user, entity_type="sku", entity_id=req.product.get("sku"), before=_plan_snapshot(req.planogram), after=_plan_snapshot(result.get("planogram")), metadata={"target_aisle_id": req.target_aisle_id, "target_module_id": req.target_module_id, "target_shelf_no": req.target_shelf_no, "force": req.force})
    return result


@app.post("/reorder-shelf")
def reorder_shelf(req: ReorderShelfRequest, current_user: Dict[str, Any] = Depends(require_action("edit"))):
    plan = copy.deepcopy(req.planogram)
    aisle, module, shelf = find_shelf(
        plan,
        req.aisle_id,
        req.module_id,
        req.shelf_no,
    )

    if not shelf:
        return {
            "status": "error",
            "message": "Raf bulunamadı.",
            "planogram": plan,
        }

    products = shelf.get("products", [])
    by_sku = {p.get("sku"): p for p in products}

    ordered = []
    used = set()

    for s in req.sku_order:
        if s in by_sku:
            ordered.append(by_sku[s])
            used.add(s)

    for p in products:
        if p.get("sku") not in used:
            ordered.append(p)

    for idx, p in enumerate(ordered):
        p["position_order"] = idx + 1

    shelf["products"] = ordered
    recalc_plan(plan)

    result = {
        "status": "success",
        "planogram": plan,
        "shelf": shelf,
    }
    _audit("shelf_reordered", actor=current_user, entity_type="shelf", entity_id=f"{req.aisle_id}:{req.module_id}:{req.shelf_no}", after=_plan_snapshot(plan), metadata={"sku_order": req.sku_order})
    return result

# =====================================================
# DJX KURULUM
# =====================================================
from fastapi import UploadFile, File
import tempfile
import os
import math
try:
    import ezdxf
except Exception:
    ezdxf = None


def make_shelves(count, storage_type="AMBIENT", width=100, height=35, depth=50):
    shelves = []
    for i in range(1, count + 1):
        shelves.append({
            "shelf_no": i,
            "shelf_width_cm": width,
            "shelf_height_cm": height,
            "shelf_depth_cm": depth,
            "max_weight_kg": 45,
            "zone_type": "bottom" if i == 1 else "top" if i == count else "eye",
            "allowed_storage_type": storage_type,
            "products": []
        })
    return shelves


def parse_dxf_to_layout(file_path, store_code="AUTO"):
    if ezdxf is None:
        raise RuntimeError("DXF desteği için ezdxf paketi kurulu değil.")
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    rectangles = []

    for e in msp:
        try:
            dxftype = e.dxftype()

            if dxftype == "LWPOLYLINE":
                points = [(float(p[0]), float(p[1])) for p in e.get_points()]
                if len(points) < 4:
                    continue

                xs = [p[0] for p in points]
                ys = [p[1] for p in points]

                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                w = abs(max_x - min_x)
                h = abs(max_y - min_y)

                if w <= 0 or h <= 0:
                    continue

                # Çok küçük çizimleri ele
                if w < 20 or h < 20:
                    continue

                rectangles.append({
                    "x": min_x,
                    "y": min_y,
                    "w": w,
                    "h": h,
                    "cx": (min_x + max_x) / 2,
                    "cy": (min_y + max_y) / 2,
                    "layer": str(e.dxf.layer or "")
                })

            elif dxftype == "INSERT":
                name = str(e.dxf.name or "").upper()
                x = float(e.dxf.insert.x)
                y = float(e.dxf.insert.y)

                rectangles.append({
                    "x": x,
                    "y": y,
                    "w": 100,
                    "h": 50,
                    "cx": x,
                    "cy": y,
                    "layer": name
                })

        except Exception:
            continue

    if not rectangles:
        return {
            "store_code": store_code,
            "route_strategy": "DXF_EMPTY_FALLBACK",
            "aisles": []
        }

    # Y koordinatına göre koridor gruplama
    rectangles = sorted(rectangles, key=lambda r: (round(r["cy"] / 300), r["cx"]))

    rows = []
    row_tolerance = 250

    for rect in rectangles:
        placed = False
        for row in rows:
            avg_y = sum(r["cy"] for r in row) / len(row)
            if abs(rect["cy"] - avg_y) <= row_tolerance:
                row.append(rect)
                placed = True
                break
        if not placed:
            rows.append([rect])

    rows = sorted(rows, key=lambda row: sum(r["cy"] for r in row) / len(row))

    aisles = []
    aisle_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    for row_idx, row in enumerate(rows):
        row = sorted(row, key=lambda r: r["cx"])

        # Aşırı fazla rectangle varsa 10'luk modül bloklarına böl
        chunk_size = 10
        chunks = [row[i:i + chunk_size] for i in range(0, len(row), chunk_size)]

        for chunk_idx, chunk in enumerate(chunks):
            aisle_index = len(aisles)
            aisle_id = aisle_letters[aisle_index] if aisle_index < len(aisle_letters) else f"A{aisle_index + 1}"

            modules = []
            for i, rect in enumerate(chunk):
                layer_upper = rect["layer"].upper()

                if "COLD" in layer_upper or "+4" in layer_upper or "FRIDGE" in layer_upper or "CHILL" in layer_upper:
                    storage = "CHILLED"
                    module_type = "fridge"
                    shelves = 5
                    depth = 55
                elif "FROZEN" in layer_upper or "-18" in layer_upper or "FREEZER" in layer_upper:
                    storage = "FROZEN"
                    module_type = "freezer"
                    shelves = 4
                    depth = 60
                else:
                    storage = "AMBIENT"
                    module_type = "regular_shelf"
                    shelves = 6
                    depth = 50

                module_width_cm = max(60, min(200, round(rect["w"] / 10)))

                modules.append({
                    "module_id": i + 1,
                    "side": "L" if i % 2 == 0 else "R",
                    "module_type": module_type,
                    "module_width_cm": module_width_cm,
                    "module_depth_cm": depth,
                    "module_height_cm": 200,
                    "source_layer": rect["layer"],
                    "cad_x": rect["x"],
                    "cad_y": rect["y"],
                    "shelves": make_shelves(
                        shelves,
                        storage_type=storage,
                        width=module_width_cm,
                        height=35,
                        depth=depth
                    )
                })

            aisles.append({
                "aisle_id": aisle_id,
                "row": row_idx + 1,
                "position": chunk_idx + 1,
                "direction": "LTR" if row_idx % 2 == 0 else "RTL",
                "aisle_type": "dxf_detected",
                "modules": modules
            })

    return {
        "store_code": store_code,
        "route_strategy": "DXF_AUTO_PARSED",
        "source": "DXF",
        "detected_rectangles": len(rectangles),
        "aisles": aisles
    }


@app.post("/parse-layout-file")
async def parse_layout_file(file: UploadFile = File(...), store_code: str = "AUTO"):
    filename = file.filename.lower()

    if not filename.endswith(".dxf"):
        return {
            "success": False,
            "message": "Şimdilik aktif parser sadece DXF destekliyor. DWG/PDF için önce DXF'e çevir.",
            "layout": None
        }

    suffix = os.path.splitext(filename)[1]

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Layout dosyası {MAX_UPLOAD_BYTES // (1024 * 1024)} MB sınırını aşamaz.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if parse_dxf_to_layout_smart is not None:
            layout = parse_dxf_to_layout_smart(tmp_path, store_code)
        else:
            layout = parse_dxf_to_layout(tmp_path, store_code)
        return {
            "success": True,
            "message": f"DXF okundu: {len(layout.get('aisles', []))} koridor üretildi.",
            "layout": layout
        }
    except Exception as err:
        return {
            "success": False,
            "message": f"DXF parse hatası: {str(err)}",
            "layout": None
        }
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

# =====================================================
# RULES / BLOCK STUDIO / OPTIMIZATION
# =====================================================

@app.post("/apply-module-rule")
def apply_module_rule(req: RuleRequest, current_user: Dict[str, Any] = Depends(require_roles("STORE_MANAGER", "REGIONAL_MANAGER", "ADMIN", "SUPER_USER"))):
    if req.module_id is None:
        return {
            "status": "error",
            "message": "module_id gerekli.",
        }

    rule_check = validate_rule_payload(req.rule)
    if not rule_check["valid"]:
        return {"status": "error", "message": "Kural geçersiz.", **rule_check}
    if not _layout_has_module(req.layout, req.aisle_id, req.module_id):
        return {"status": "error", "message": "Modül bulunamadı.", "layout": req.layout}

    layout = engine_apply_module_rule(
        layout=req.layout,
        aisle_id=req.aisle_id,
        module_id=req.module_id,
        rule=req.rule,
    )

    _audit("module_rule_applied", actor=current_user, entity_type="module", entity_id=f"{req.aisle_id}:{req.module_id}", before=_plan_snapshot(req.layout), after=_plan_snapshot(layout), metadata={"rule": req.rule})

    return {
        "status": "success",
        "layout": layout,
    }


@app.post("/apply-shelf-rule")
def apply_shelf_rule(req: RuleRequest, current_user: Dict[str, Any] = Depends(require_roles("STORE_MANAGER", "REGIONAL_MANAGER", "ADMIN", "SUPER_USER"))):
    if req.module_id is None or req.shelf_no is None:
        return {
            "status": "error",
            "message": "module_id ve shelf_no gerekli.",
        }

    rule_check = validate_rule_payload(req.rule)
    if not rule_check["valid"]:
        return {"status": "error", "message": "Kural geçersiz.", **rule_check}
    if not _layout_has_shelf(req.layout, req.aisle_id, req.module_id, req.shelf_no):
        return {"status": "error", "message": "Raf bulunamadı.", "layout": req.layout}

    layout = engine_apply_shelf_rule(
        layout=req.layout,
        aisle_id=req.aisle_id,
        module_id=req.module_id,
        shelf_no=req.shelf_no,
        rule=req.rule,
    )

    _audit("shelf_rule_applied", actor=current_user, entity_type="shelf", entity_id=f"{req.aisle_id}:{req.module_id}:{req.shelf_no}", before=_plan_snapshot(req.layout), after=_plan_snapshot(layout), metadata={"rule": req.rule})

    return {
        "status": "success",
        "layout": layout,
    }


@app.post("/suggest-empty-space")
def suggest_empty_space(req: SuggestRequest):
    return engine_suggest_empty_space(
        plan=req.planogram,
        products=req.products,
        aisle_id=req.aisle_id,
        module_id=req.module_id,
        shelf_no=req.shelf_no,
        limit=req.limit or 30,
    )


@app.post("/commit-block-studio")
def commit_block_studio(req: BlockStudioCommitRequest, current_user: Dict[str, Any] = Depends(require_roles("STORE_MANAGER", "REGIONAL_MANAGER", "ADMIN", "SUPER_USER"))):
    result = engine_commit_block_studio(
        plan=req.planogram,
        aisle_id=req.aisle_id,
        module_id=req.module_id,
        shelf_no=req.shelf_no,
        blocks=req.blocks,
    )
    _audit("block_studio_committed", actor=current_user, entity_type="shelf", entity_id=f"{req.aisle_id}:{req.module_id}:{req.shelf_no}", before=_plan_snapshot(req.planogram), after=_plan_snapshot(result.get("planogram")), metadata={"committed": result.get("committed", result.get("status") == "success"), "rejected_count": len(result.get("rejected", []))})
    return result


@app.post("/optimize-shelf")
def optimize_shelf(payload: Dict[str, Any] = Body(...)):
    return engine_optimize_shelf(
        plan=payload.get("planogram"),
        products=payload.get("products", []),
        aisle_id=payload.get("aisle_id"),
        module_id=payload.get("module_id"),
        shelf_no=payload.get("shelf_no"),
    )


@app.post("/optimize-module")
def optimize_module(payload: Dict[str, Any] = Body(...)):
    return engine_optimize_module(
        plan=payload.get("planogram"),
        products=payload.get("products", []),
        aisle_id=payload.get("aisle_id"),
        module_id=payload.get("module_id"),
    )


@app.post("/optimize-selected-modules")
def optimize_selected_modules(req: SelectedModulesRequest):
    layout = copy.deepcopy(req.layout)

    selected = {
        (
            str(x.get("aisle_id") or x.get("aisleId")),
            int(x.get("module_id") or x.get("moduleId")),
        )
        for x in req.selected_modules
    }

    selected_layout = copy.deepcopy(layout)

    for aisle in selected_layout.get("aisles", []):
        aisle["modules"] = [
            module for module in aisle.get("modules", [])
            if (str(aisle.get("aisle_id")), int(module.get("module_id"))) in selected
        ]

    selected_layout["aisles"] = [a for a in selected_layout.get("aisles", []) if a.get("modules")]
    if not selected_layout["aisles"]:
        return {"status": "error", "message": "En az bir modül seçmelisiniz.", "selected_modules": list(selected)}

    result = generate_planogram(
        products=req.products,
        layout=selected_layout,
        mode=req.mode or "HYBRID",
        brand_side_rules=req.brand_side_rules,
        scoring_config=scoring_config_with_defaults(req.scoring_config),
        allow_ai_dimensions=req.allow_ai_dimensions,
    )

    return {
        "status": "success",
        "selected_modules": list(selected),
        **result,
    }


# =====================================================
# LAYOUT EDITING
# =====================================================

@app.post("/add-module")
def add_module(payload: Dict[str, Any] = Body(...), current_user: Dict[str, Any] = Depends(require_roles("STORE_MANAGER", "REGIONAL_MANAGER", "ADMIN", "SUPER_USER"))):
    layout = copy.deepcopy(payload.get("layout") or generate_default_layout())

    aisle_id = str(payload.get("aisle_id") or "")
    module_type = payload.get("module_type") or "regular_shelf"
    storage = payload.get("storage_type") or "AMBIENT"
    shelf_count = int(payload.get("shelf_count") or 6)

    width = float(payload.get("module_width_cm") or 100)
    depth = float(payload.get("module_depth_cm") or 50)
    height = float(payload.get("module_height_cm") or 200)
    max_weight = float(payload.get("max_weight_kg") or 45)

    for aisle in layout.get("aisles", []):
        if str(aisle.get("aisle_id")) == aisle_id:
            module_id = len(aisle.get("modules", [])) + 1

            aisle.setdefault("modules", []).append({
                "module_id": module_id,
                "side": payload.get("side") or "L",
                "module_type": module_type,
                "module_width_cm": width,
                "module_depth_cm": depth,
                "module_height_cm": height,
                "distance_to_dispatch": module_id,
                "assignment_rule": None,
                "shelves": make_shelves(
                    shelf_count,
                    storage,
                    width,
                    height / max(shelf_count, 1),
                    depth,
                    max_weight,
                ),
            })

            result = {
                "status": "success",
                "layout": layout,
            }
            _audit("module_added", actor=current_user, store_code=payload.get("store_code"), entity_type="module", entity_id=f"{aisle_id}:{module_id}", after=_plan_snapshot(layout), metadata={"module_type": module_type, "storage_type": storage})
            return result

    return {
        "status": "error",
        "message": "Koridor bulunamadı.",
        "layout": layout,
    }


@app.post("/add-shelf")
def add_shelf(payload: Dict[str, Any] = Body(...), current_user: Dict[str, Any] = Depends(require_roles("STORE_MANAGER", "REGIONAL_MANAGER", "ADMIN", "SUPER_USER"))):
    layout = copy.deepcopy(payload.get("layout") or generate_default_layout())

    aisle_id = payload.get("aisle_id")
    module_id = int(payload.get("module_id"))

    aisle, module, _ = find_shelf(layout, aisle_id, module_id, 1)

    if not module:
        return {
            "status": "error",
            "message": "Modül bulunamadı.",
            "layout": layout,
        }

    module.setdefault("shelves", []).append({
        "shelf_no": len(module.get("shelves", [])) + 1,
        "shelf_width_cm": float(payload.get("shelf_width_cm") or 100),
        "shelf_height_cm": float(payload.get("shelf_height_cm") or 35),
        "shelf_depth_cm": float(payload.get("shelf_depth_cm") or 50),
        "max_weight_kg": float(payload.get("max_weight_kg") or 45),
        "zone_type": payload.get("zone_type") or "mid",
        "allowed_storage_type": payload.get("allowed_storage_type") or "AMBIENT",
        "allowed_categories": [],
        "blocked_categories": [],
        "assignment_rule": None,
        "products": [],
        "used_width_cm": 0,
        "used_weight_kg": 0,
        "used": 0,
    })

    result = {
        "status": "success",
        "layout": layout,
    }
    _audit("shelf_added", actor=current_user, store_code=payload.get("store_code"), entity_type="shelf", entity_id=f"{aisle_id}:{module_id}:{module['shelves'][-1]['shelf_no']}", after=_plan_snapshot(layout))
    return result


@app.post("/update-shelf-size")
def update_shelf_size(payload: Dict[str, Any] = Body(...), current_user: Dict[str, Any] = Depends(require_roles("STORE_MANAGER", "REGIONAL_MANAGER", "ADMIN", "SUPER_USER"))):
    layout = copy.deepcopy(payload.get("layout") or payload.get("planogram"))
    aisle_id = payload.get("aisle_id")
    module_id = int(payload.get("module_id"))
    shelf_no = int(payload.get("shelf_no"))

    aisle, module, shelf = find_shelf(layout, aisle_id, module_id, shelf_no)

    if not shelf:
        return {
            "status": "error",
            "message": "Raf bulunamadı.",
            "layout": layout,
        }

    if "shelf_width_cm" in payload:
        shelf["shelf_width_cm"] = float(payload["shelf_width_cm"])
    if "shelf_height_cm" in payload:
        shelf["shelf_height_cm"] = float(payload["shelf_height_cm"])
    if "shelf_depth_cm" in payload:
        shelf["shelf_depth_cm"] = float(payload["shelf_depth_cm"])
    if "max_weight_kg" in payload:
        shelf["max_weight_kg"] = float(payload["max_weight_kg"])
    if "allowed_storage_type" in payload:
        shelf["allowed_storage_type"] = payload["allowed_storage_type"]

    recalc_plan(layout)

    result = {
        "status": "success",
        "layout": layout,
    }
    _audit("shelf_size_updated", actor=current_user, store_code=payload.get("store_code"), entity_type="shelf", entity_id=f"{aisle_id}:{module_id}:{shelf_no}", after=_plan_snapshot(layout), metadata={"width_cm": shelf.get("shelf_width_cm"), "height_cm": shelf.get("shelf_height_cm"), "depth_cm": shelf.get("shelf_depth_cm"), "max_weight_kg": shelf.get("max_weight_kg")})
    return result


# =====================================================
# DIMENSION APPROVAL FLOW
# =====================================================

@app.post("/request-dimension-change")
def request_dimension_change(req: DimensionChangeRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    item = create_change_request(
        sku=req.sku,
        product_name=req.product_name,
        old=req.old,
        new=req.new,
        requested_by=str(current_user.get("username") or req.requested_by or "user"),
        reason=req.reason or "",
    )

    _audit(
        "dimension_change_requested",
        actor=current_user,
        entity_type="sku",
        entity_id=req.sku,
        after=item,
    )

    return {
        "status": "success",
        "request": item,
        "message": "Ölçü değişikliği onaya gönderildi.",
    }


@app.get("/pending-dimension-changes")
def pending_dimension_changes(current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER", "REGIONAL_MANAGER"))):
    all_requests = list_change_requests()
    return {
        "status": "success",
        "pending": [x for x in all_requests if x["status"] == "PENDING"],
        "all": all_requests,
    }


@app.post("/approve-dimension-change")
def approve_dimension_change(req: ApproveDimensionRequest, current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER"))):
    target = get_change_request(req.request_id)

    if not target:
        return {
            "status": "error",
            "message": "Request bulunamadı.",
        }

    if target.get("status") != "PENDING":
        return {"status": "error", "message": "Bu request daha önce sonuçlandırılmış."}

    target = review_change_request(
        req.request_id,
        approve=req.approve,
        reviewed_by=str(current_user.get("username") or "admin"),
    )

    _audit(
        "dimension_change_reviewed",
        entity_type="sku",
        entity_id=target["sku"],
        actor=current_user,
        after=target,
        metadata={"approve": req.approve, "request_id": req.request_id},
    )

    if not req.approve or not req.planogram:
        return {
            "status": "success",
            "request": target,
            "planogram": req.planogram,
        }

    plan = copy.deepcopy(req.planogram)
    product = find_product(plan, target["sku"])

    if product:
        if "width_cm" in target["new"]:
            product["width_cm"] = float(target["new"]["width_cm"])
        if "height_cm" in target["new"]:
            product["height_cm"] = float(target["new"]["height_cm"])
        if "depth_cm" in target["new"]:
            product["depth_cm"] = float(target["new"]["depth_cm"])
        if "is_rotated" in target["new"]:
            product["is_rotated"] = bool(target["new"]["is_rotated"])

        product["dimension_source"] = "approved_user_override"
        product["dimension_confidence"] = 1

    recalc_plan(plan)

    return {
        "status": "success",
        "request": target,
        "planogram": plan,
    }


# =====================================================
# PICKING ROUTE
# =====================================================

@app.post("/picking-route")
def picking_route(req: RouteRequest):
    return optimize_picking_route(
        order_skus=req.order_skus,
        plan=req.planogram,
    )


@app.post("/generate-planogram-lite")
def generate_planogram_lite(req: GenerateRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Compatibility endpoint backed by the same deterministic engine.

    There must not be a second allocator that silently ignores rules or caps
    the catalog at 500 rows. The response shape remains compatible with the
    legacy frontend while the placement result is now identical in semantics
    to /generate-planogram-fast.
    """
    started = time.perf_counter()
    result = run_engine(
        products=req.products,
        layout=req.layout or generate_default_layout(),
        mode=req.mode or "HYBRID",
        brand_side_rules=req.brand_side_rules,
        scoring_config=scoring_config_with_defaults(req.scoring_config),
        allow_ai_dimensions=req.allow_ai_dimensions,
    )
    result.setdefault("summary", {})["runtime_sec"] = round(time.perf_counter() - started, 3)
    result.setdefault("summary", {})["mode"] = "FAST_DETERMINISTIC_COMPAT"
    result["unplaced_products"] = result.get("unplaced", [])
    _audit(
        "plan_generated_compat",
        actor=current_user,
        store_code=req.store_code,
        entity_type="planogram",
        entity_id=req.store_code or "current",
        request_id=req.request_id,
        after=result.get("summary"),
        metadata={"endpoint": "generate-planogram-lite", "product_count": len(req.products or [])},
    )
    return result
