
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
import csv
import math
from engine import normalize_storage

router = APIRouter(prefix="/master-products", tags=["master-products"])

DATA_PATH = Path(__file__).resolve().parent / "data" / "master_products.csv"

def _num(v, d=0):
    try:
        if v is None or str(v).strip() == "":
            return d
        return float(str(v).replace(",", "."))
    except Exception:
        return d

def _storage(row):
    explicit = normalize_storage(row.get("storage_type") or row.get("storage_raw"), default="")
    name = f"{row.get('product_name','')} {row.get('frontend_category_local','')} {row.get('frontend_subcategory_local','')} {row.get('pim_cat_l1','')} {row.get('pim_cat_l2','')}".lower()
    if explicit:
        return explicit
    if any(x in name for x in ["dondurma", "frozen", "donuk", "-18", "ice cream"]):
        return "FROZEN"
    if any(x in name for x in ["tavuk", "et", "süt", "yoğurt", "peynir", "chilled", "soğuk", "+4"]):
        return "CHILLED"
    if any(x in name for x in ["pide", "ekmek", "fırın", "bakery", "la lorraine"]):
        return "AMBIENT"
    return "AMBIENT"

def _normalize(row):
    name = row.get("product_name") or row.get("product_name_local") or row.get("product_name_english") or "Unnamed Product"
    return {
        **row,
        "sku": str(row.get("sku") or row.get("product_barcodes") or "").strip(),
        "product_name": name,
        "brand": row.get("brand_name") or row.get("brand") or str(name).split(" ")[0],
        "category_l1": row.get("frontend_category_local") or row.get("frontend_category") or row.get("pim_cat_l1") or "Uncategorized",
        "category_l2": row.get("frontend_subcategory_local") or row.get("frontend_subcategory") or row.get("pim_cat_l2") or "General",
        "storage_type": _storage(row),
        "width_cm": _num(row.get("product_width_in_cm") or row.get("width_cm"), 8),
        "height_cm": _num(row.get("product_height_in_cm") or row.get("height_cm"), 15),
        "depth_cm": _num(row.get("product_length_in_cm") or row.get("depth_cm"), 8),
        "weight_kg": _num(row.get("product_weight_value") or row.get("weight_kg"), 0.2),
        "image_url": row.get("image_url") or row.get("catalog_image_url") or row.get("pim_image_url") or "",
    }

def load_products():
    if not DATA_PATH.exists():
        raise HTTPException(status_code=404, detail=f"master_products.csv bulunamadı: {DATA_PATH}")
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return [_normalize(r) for r in csv.DictReader(f)]

@router.get("")
def list_products(limit: int = Query(200, ge=1, le=10000), offset: int = Query(0, ge=0)):
    rows = load_products()
    return {"total": len(rows), "limit": limit, "offset": offset, "products": rows[offset:offset+limit]}

@router.get("/search")
def search_products(q: str = "", storage: str = "", limit: int = Query(80, ge=1, le=500)):
    rows = load_products()
    ql = q.lower().strip()
    st = storage.upper().strip()
    def ok(r):
        hay = f"{r.get('sku','')} {r.get('product_name','')} {r.get('brand','')} {r.get('category_l1','')} {r.get('category_l2','')}".lower()
        return (not ql or ql in hay) and (not st or str(r.get("storage_type","")).upper().startswith(st))
    return {"products": [r for r in rows if ok(r)][:limit]}

@router.get("/{sku}")
def get_product(sku: str):
    for r in load_products():
        if str(r.get("sku")) == str(sku):
            return r
    raise HTTPException(status_code=404, detail="SKU bulunamadı")
