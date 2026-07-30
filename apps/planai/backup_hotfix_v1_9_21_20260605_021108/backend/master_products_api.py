from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from typing import Any, Dict, List
import csv

router = APIRouter(prefix="/master-products", tags=["master-products"])

DATA_PATH = Path(__file__).resolve().parent / "data" / "master_products.csv"


def _text(v: Any, d: str = "") -> str:
    if v is None:
        return d
    s = str(v).strip()
    return s if s else d


def _num(v: Any, d=0):
    try:
        if v is None or str(v).strip() == "":
            return d
        return float(str(v).replace(",", "."))
    except Exception:
        return d


def _upper(v: Any) -> str:
    return _text(v).upper()


def _storage(row: Dict[str, Any]) -> str:
    explicit = _upper(row.get("storage_type") or row.get("Storage Type") or row.get("storage"))
    if explicit in ("FROZEN", "CHILLED", "AMBIENT", "PALLET"):
        return explicit

    raw = _upper(row.get("storage_raw") or row.get("fixture_type") or "")
    name = _upper(" ".join(_text(row.get(k)) for k in [
        "product_name", "product_name_local", "frontend_category_local", "frontend_subcategory_local", "category_l1", "category_l2"
    ]))
    hay = f"{raw} {name}"
    if any(x in hay for x in ["FROZEN", "DONUK", "DONDUR", "-18", "FREEZER", "ALGIDA"]):
        return "FROZEN"
    if any(x in hay for x in ["CHILLED", "DOLAP", "SOĞUK", "SOGUK", "+4", "FRIDGE", "CHILL", "SÜT", "SUT", "YOĞURT", "YOGURT"]):
        return "CHILLED"
    return "AMBIENT"


def _fixture_kind(row: Dict[str, Any]) -> str:
    raw = _upper(row.get("storage_raw") or row.get("fixture_kind") or row.get("fixture_type") or "")
    st = _storage(row)
    if any(x in raw for x in ["DONUK", "DONDUR", "-18", "FREEZER", "FROZEN", "ALGIDA"]):
        return "FREEZER"
    if any(x in raw for x in ["DOLAP", "+4", "CHILL", "CHILLED", "FRIDGE", "SOĞUK", "SOGUK"]):
        return "FRIDGE"
    if any(x in raw for x in ["RAF", "SHELF", "GONDOLA"]):
        return "SHELF"
    if st == "FROZEN":
        return "FREEZER"
    if st == "CHILLED":
        return "FRIDGE"
    return "SHELF"


def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
    name = _text(row.get("product_name") or row.get("product_name_local") or row.get("product_name_english"), "Unnamed Product")
    brand = _text(row.get("brand_name") or row.get("brand"), name.split(" ")[0] if name else "UNKNOWN")
    category_l1 = _text(row.get("frontend_category_local") or row.get("category_l1") or row.get("frontend_category") or row.get("pim_cat_l1"), "Uncategorized")
    category_l2 = _text(row.get("frontend_subcategory_local") or row.get("category_l2") or row.get("frontend_subcategory") or row.get("pim_cat_l2"), "General")
    storage = _storage(row)
    fixture = _fixture_kind(row)

    return {
        **row,
        "sku": _text(row.get("sku") or row.get("SKU") or row.get("product_barcodes") or row.get("barcode")),
        "product_name": name,
        "brand": brand,
        "brand_name": brand,
        "barcode": _text(row.get("barcode") or row.get("product_barcodes")),
        "product_barcodes": _text(row.get("product_barcodes") or row.get("barcode")),
        "supplier_code": _text(row.get("supplier_code")),
        "supplier_name": _text(row.get("supplier_name")),
        "category_l1": category_l1,
        "category_l2": category_l2,
        "frontend_category_local": category_l1,
        "frontend_subcategory_local": category_l2,
        "storage_type": storage,
        "storage_raw": _text(row.get("storage_raw")),
        "fixture_kind": fixture,
        "required_fixture_kind": fixture,
        "width_cm": _num(row.get("width_cm") or row.get("product_width_in_cm"), 8),
        "height_cm": _num(row.get("height_cm") or row.get("product_height_in_cm"), 15),
        "depth_cm": _num(row.get("depth_cm") or row.get("product_length_in_cm"), 8),
        "weight_kg": _num(row.get("weight_kg") or row.get("product_weight_value"), 0.2),
        "case_pack_qty": _num(row.get("case_pack_qty"), 1),
        "image_url": _text(row.get("image_url") or row.get("catalog_image_url") or row.get("pim_image_url")),
        "data_quality_flags": _text(row.get("data_quality_flags")),
    }


def load_products() -> List[Dict[str, Any]]:
    if not DATA_PATH.exists():
        return []
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return [_normalize(r) for r in csv.DictReader(f)]


@router.get("")
def list_products(limit: int = Query(200, ge=1, le=10000), offset: int = Query(0, ge=0)):
    rows = load_products()
    return {"total": len(rows), "limit": limit, "offset": offset, "products": rows[offset:offset+limit]}


@router.get("/search")
def search_products(
    q: str = "",
    storage: str = "",
    fixture: str = "",
    brand: str = "",
    category: str = "",
    limit: int = Query(80, ge=1, le=500),
):
    rows = load_products()
    ql = q.lower().strip()
    st = storage.upper().strip()
    fx = fixture.upper().strip()
    br = brand.lower().strip()
    cat = category.lower().strip()

    def ok(r):
        hay = " ".join(str(r.get(k, "")) for k in [
            "sku", "barcode", "product_barcodes", "product_name", "brand", "brand_name", "category_l1", "category_l2", "supplier_name", "storage_raw"
        ]).lower()
        if ql and ql not in hay:
            return False
        if st and str(r.get("storage_type", "")).upper() != st:
            return False
        if fx and str(r.get("fixture_kind", "")).upper() != fx:
            return False
        if br and br not in str(r.get("brand", "")).lower():
            return False
        if cat and cat not in f"{r.get('category_l1','')} {r.get('category_l2','')}".lower():
            return False
        return True

    return {"products": [r for r in rows if ok(r)][:limit]}


@router.get("/schema")
def product_schema():
    rows = load_products()
    columns = sorted({k for r in rows[:100] for k in r.keys()}) if rows else []
    return {"path": str(DATA_PATH), "row_count": len(rows), "columns": columns}


@router.get("/{sku}")
def get_product(sku: str):
    s = str(sku).strip()
    for r in load_products():
        if str(r.get("sku")) == s or str(r.get("barcode")) == s or s in str(r.get("product_barcodes", "")):
            return r
    raise HTTPException(status_code=404, detail="SKU bulunamadı")
