from collections import Counter, defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/planogram-diagnostics", tags=["planogram-diagnostics"])

class DiagnosticsRequest(BaseModel):
    products: List[Dict[str, Any]] = []
    planogram: Dict[str, Any] = {}
    unplaced_products: List[Dict[str, Any]] = []


def norm_storage(p: Dict[str, Any]) -> str:
    text = " ".join(str(p.get(k, "")) for k in ["storage_type", "product_name", "category_l1", "category_l2", "frontend_category_local", "frontend_subcategory_local", "brand", "brand_name"]).lower()
    if any(x in text for x in ["frozen", "donuk", "-18", "dondurma", "algida"]):
        return "FROZEN"
    if any(x in text for x in ["chilled", "cold", "soğuk", "soguk", "+4", "süt", "sut", "yoğurt", "yogurt", "peynir", "tavuk"]):
        return "CHILLED"
    return "AMBIENT"


def num(v: Any, d: float = 0) -> float:
    try:
        if v in [None, ""]:
            return d
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except Exception:
        return d


def sku_of(p: Dict[str, Any]) -> str:
    return str(p.get("sku") or p.get("SKU") or p.get("barcode") or p.get("product_barcodes") or p.get("product_name") or "").strip()


def collect_shelves(planogram: Dict[str, Any]) -> List[Dict[str, Any]]:
    shelves = []
    for aisle in planogram.get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            module_type = str(module.get("module_type") or module.get("type") or "regular_shelf")
            product_allowed = not any(x in module_type.lower() for x in ["room", "zone", "dispatch", "receiving", "column", "wall"])
            for shelf in module.get("shelves", []) or []:
                width = num(shelf.get("shelf_width_cm"), num(module.get("module_width_cm"), 100))
                used = num(shelf.get("used_width_cm"), 0)
                shelves.append({
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                    "storage": str(shelf.get("allowed_storage_type") or module.get("allowed_storage_type") or "AMBIENT").upper(),
                    "width_cm": width,
                    "height_cm": num(shelf.get("shelf_height_cm"), 35),
                    "depth_cm": num(shelf.get("shelf_depth_cm"), num(module.get("module_depth_cm"), 50)),
                    "used_width_cm": used,
                    "remaining_width_cm": max(0, width - used),
                    "product_allowed": product_allowed,
                })
    return shelves


@router.post("")
def planogram_diagnostics(req: DiagnosticsRequest):
    shelves = collect_shelves(req.planogram)
    placed_skus = set()
    for aisle in req.planogram.get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            for shelf in module.get("shelves", []) or []:
                for p in shelf.get("products", []) or []:
                    placed_skus.add(sku_of(p))

    by_sku = {sku_of(p): p for p in req.products if sku_of(p)}
    reason_counts = Counter()
    storage_counts = Counter()
    rows = []

    candidates = list(req.unplaced_products or [])
    returned = {sku_of(p) for p in candidates if sku_of(p)}
    for sku, p in by_sku.items():
        if sku not in placed_skus and sku not in returned:
            candidates.append({**p, "reason": "not_returned_by_engine_but_not_placed"})

    for u in candidates:
        sku = sku_of(u)
        p = {**by_sku.get(sku, {}), **u}
        storage = norm_storage(p)
        w = num(p.get("width_cm") or p.get("product_width_in_cm"), 0)
        h = num(p.get("height_cm") or p.get("product_height_in_cm"), 0)
        d = num(p.get("depth_cm") or p.get("product_depth_in_cm") or p.get("product_length_in_cm"), 0)
        if w <= 0 or h <= 0 or d <= 0:
            code = "missing_dimensions"
        elif not [s for s in shelves if s["product_allowed"]]:
            code = "no_product_fixture"
        elif not [s for s in shelves if s["product_allowed"] and s["storage"] == storage]:
            code = "no_matching_storage_shelf"
        elif not [s for s in shelves if s["product_allowed"] and s["storage"] == storage and h <= s["height_cm"]]:
            code = "product_too_tall"
        elif not [s for s in shelves if s["product_allowed"] and s["storage"] == storage and h <= s["height_cm"] and d <= s["depth_cm"]]:
            code = "product_too_deep"
        else:
            code = "insufficient_capacity"
        reason_counts[code] += 1
        storage_counts[storage] += 1
        rows.append({"sku": sku, "product_name": p.get("product_name"), "storage_type": storage, "reason_code": code, "reason": p.get("reason")})

    capacity = defaultdict(lambda: {"shelves": 0, "capacity": 0, "used": 0, "remaining": 0})
    for s in shelves:
        x = capacity[s["storage"]]
        x["shelves"] += 1
        x["capacity"] += s["width_cm"]
        x["used"] += s["used_width_cm"]
        x["remaining"] += s["remaining_width_cm"]

    return {
        "summary": {
            "total_products": len(by_sku),
            "placed_unique_skus": len(placed_skus),
            "unplaced_count": len(rows),
            "placement_rate_pct": round(len(placed_skus) / max(len(by_sku), 1) * 100, 2),
            "total_shelves": len(shelves),
            "product_allowed_shelves": len([s for s in shelves if s["product_allowed"]]),
        },
        "reason_counts": dict(reason_counts),
        "storage_counts": dict(storage_counts),
        "capacity_by_storage": dict(capacity),
        "unplaced": rows[:1000],
    }
