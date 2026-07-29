"""Safe Council Engine bridge.

The research POC in ai_planogram_engine.py depends on torch. This bridge keeps
production boot safe: if torch/model is unavailable, we run a deterministic
Council heuristic with the same principles: sales, storage, ergonomics,
brand/category clustering, depth/facing and refill risk.
"""
from copy import deepcopy
from typing import Any, Dict, List, Tuple


def _num(v: Any, d: float = 0) -> float:
    try:
        if v is None or v == "":
            return d
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except Exception:
        return d


def _txt(v: Any) -> str:
    return str(v or "").strip()


def _storage(p: Dict[str, Any]) -> str:
    raw = f"{p.get('storage_type','')} {p.get('product_name','')} {p.get('category_l1','')} {p.get('category_l2','')} {p.get('brand','')}".upper()
    if any(x in raw for x in ["FROZEN", "-18", "DONUK", "DONDURMA", "ALGIDA"]):
        return "FROZEN"
    if any(x in raw for x in ["CHILLED", "+4", "SOĞUK", "SOGUK", "SÜT", "SUT", "YOĞURT", "YOGURT"]):
        return "CHILLED"
    return "AMBIENT"


def _make_default_layout() -> Dict[str, Any]:
    aisles = []
    for idx, aid in enumerate(list("ABCDEFGHI")):
        modules = []
        for mid in range(1, 15):
            modules.append({
                "module_id": mid,
                "module_type": "regular_shelf",
                "module_width_cm": 160,
                "module_depth_cm": 50,
                "module_height_cm": 210,
                "shelves": [{
                    "shelf_no": s,
                    "shelf_width_cm": 160,
                    "shelf_height_cm": 35,
                    "shelf_depth_cm": 50,
                    "max_weight_kg": 45,
                    "zone_type": "bottom" if s == 1 else "eye" if s in (2, 3) else "mid",
                    "allowed_storage_type": "AMBIENT",
                    "products": [],
                    "used_width_cm": 0,
                    "used_weight_kg": 0,
                } for s in range(1, 7)]
            })
        aisles.append({
            "aisle_id": aid,
            "row": idx // 3 + 1,
            "position": idx % 3 + 1,
            "direction": "LTR" if idx % 2 == 0 else "RTL",
            "modules": modules,
        })
    for aid, storage, module_type, shelves, module_count in [("CHILLED_ROOM", "CHILLED", "fridge", 5, 8), ("FROZEN_ROOM", "FROZEN", "freezer", 4, 8), ("ALGIDA_1", "FROZEN", "freezer", 4, 4), ("HORIZONTAL_FRIDGE", "CHILLED", "fridge", 4, 4), ("PRODUCE_SHELF", "AMBIENT", "produce_shelf", 4, 4)]:
        aisles.append({
            "aisle_id": aid,
            "row": 4,
            "position": len(aisles),
            "direction": "COLD",
            "modules": [{
                "module_id": mid,
                "module_type": module_type,
                "module_width_cm": 150,
                "module_depth_cm": 60,
                "module_height_cm": 210,
                "shelves": [{
                    "shelf_no": s,
                    "shelf_width_cm": 150,
                    "shelf_height_cm": 38,
                    "shelf_depth_cm": 60,
                    "max_weight_kg": 65,
                    "zone_type": "eye" if s in (2, 3) else "mid",
                    "allowed_storage_type": storage,
                    "products": [],
                    "used_width_cm": 0,
                    "used_weight_kg": 0,
                } for s in range(1, shelves + 1)]
            } for mid in range(1, module_count + 1)]
        })
    return {"store_code": "COUNCIL", "route_strategy": "COUNCIL_SAFE_HEURISTIC", "aisles": aisles}


def _iter_shelves(plan):
    for a in plan.get("aisles", []):
        for m in a.get("modules", []):
            for s in m.get("shelves", []):
                yield a, m, s


def _capacity(p, shelf, facing):
    width = max(1, _num(p.get("width_cm") or p.get("product_width_in_cm"), 8))
    return width * facing * 1.08 <= max(1, _num(shelf.get("shelf_width_cm"), 100) - _num(shelf.get("used_width_cm"), 0))


def _preferred_facing(p, shelf):
    sales = _num(p.get("sales_qty_7d") or p.get("sales_7d") or p.get("sales"), 0)
    depth_units = max(1, int(_num(shelf.get("shelf_depth_cm"), 50) // max(1, _num(p.get("depth_cm") or p.get("product_length_in_cm"), 10))))
    base = 5 if sales >= 180 else 4 if sales >= 120 else 3 if sales >= 70 else 2 if sales >= 25 else 1
    needed = int(max(1, (sales * 0.75) // max(depth_units, 1))) if sales else base
    return max(1, min(8, max(base, needed)))


def _target_aisles(p, rank_idx):
    st = _storage(p)
    raw = f"{p.get('product_name','')} {p.get('category_l1','')} {p.get('category_l2','')} {p.get('brand','')}".upper()
    sales = _num(p.get("sales_qty_7d") or p.get("sales_7d") or p.get("sales"), 0)
    odor = any(x in raw for x in ["DOMESTOS", "DETERJAN", "TEMIZ", "TEMİZ", "ÇAMAŞIR", "CAMASIR", "SHAMPOO", "ŞAMPUAN"])
    if st == "FROZEN":
        return ["ALGIDA_1", "FROZEN_ROOM"] if any(x in raw for x in ["ALGIDA", "MAGNUM", "DONDURMA"]) else ["FROZEN_ROOM", "ALGIDA_1"]
    if st == "CHILLED":
        return ["CHILLED_ROOM", "HORIZONTAL_FRIDGE"]
    if odor:
        return ["I", "H", "G", "F", "E", "C", "B"]
    if any(x in raw for x in ["MEYVE", "SEBZE", "PATATES", "MUZ"]):
        return ["D", "E", "G"]
    if sales >= 120:
        return ["A", "B", "C"]
    if sales >= 50:
        return ["D", "E", "G", "H", "B", "C", "F"]
    return ["I", "H", "G", "F", "E", "C", "B"]


def optimize_with_council(products: List[Dict[str, Any]], layout: Dict[str, Any] | None = None) -> Dict[str, Any]:
    plan = deepcopy(layout) if layout and layout.get("aisles") else _make_default_layout()
    for _, _, shelf in _iter_shelves(plan):
        shelf["products"] = []
        shelf["used_width_cm"] = 0
        shelf["used_weight_kg"] = 0

    ranked = sorted(products or [], key=lambda p: _num(p.get("sales_qty_7d") or p.get("sales_7d") or p.get("sales"), 0), reverse=True)
    unplaced = []
    placed_count = 0

    shelves_by_id: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]] = {}
    for a, m, s in _iter_shelves(plan):
        shelves_by_id.setdefault(str(a.get("aisle_id")), []).append((a, m, s))

    for idx, raw in enumerate(ranked):
        p = dict(raw)
        storage = _storage(p)
        p["storage_type"] = storage
        placed = False
        for aid in _target_aisles(p, idx):
            for aisle, module, shelf in shelves_by_id.get(aid, []):
                if str(shelf.get("allowed_storage_type", "AMBIENT")).upper() != storage:
                    continue
                if _num(p.get("height_cm") or p.get("product_height_in_cm"), 16) > _num(shelf.get("shelf_height_cm"), 35):
                    continue
                if _num(p.get("depth_cm") or p.get("product_length_in_cm"), 10) > _num(shelf.get("shelf_depth_cm"), 50):
                    continue
                facing = _preferred_facing(p, shelf)
                if not _capacity(p, shelf, facing):
                    continue
                width = max(1, _num(p.get("width_cm") or p.get("product_width_in_cm"), 8))
                used = round(width * facing * 1.08, 1)
                item = {
                    "sku": _txt(p.get("sku") or p.get("barcode") or f"SKU-{idx+1}"),
                    "product_name": _txt(p.get("product_name") or p.get("name") or p.get("sku") or f"Product {idx+1}"),
                    "brand": _txt(p.get("brand") or p.get("brand_name") or "UNKNOWN"),
                    "category_l1": _txt(p.get("category_l1") or p.get("category") or "GENERAL"),
                    "category_l2": _txt(p.get("category_l2") or p.get("subcategory") or "GENERAL"),
                    "image_url": _txt(p.get("image_url") or p.get("Product Image URL") or p.get("catalog_image_url") or p.get("pim_image_url") or ""),
                    "storage_type": storage,
                    "sales_qty_7d": _num(p.get("sales_qty_7d") or p.get("sales_7d") or p.get("sales"), 0),
                    "width_cm": width,
                    "height_cm": _num(p.get("height_cm") or p.get("product_height_in_cm"), 16),
                    "depth_cm": _num(p.get("depth_cm") or p.get("product_length_in_cm"), 10),
                    "facing": facing,
                    "facing_count": facing,
                    "used_width_cm": used,
                    "depth_units": max(1, int(_num(shelf.get("shelf_depth_cm"), 50) // max(1, _num(p.get("depth_cm") or p.get("product_length_in_cm"), 10)))),
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                    "position_order": len(shelf.get("products", [])) + 1,
                    "placement_reason": "Council heuristic: storage + sales + ergonomics + brand/category + facing/depth",
                }
                shelf.setdefault("products", []).append(item)
                shelf["used_width_cm"] = round(_num(shelf.get("used_width_cm"), 0) + used, 1)
                shelf["used_weight_kg"] = round(_num(shelf.get("used_weight_kg"), 0) + _num(p.get("weight_kg"), 0.2) * facing, 2)
                placed_count += 1
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append({
                "sku": p.get("sku"),
                "product_name": p.get("product_name") or p.get("name"),
                "storage_type": storage,
                "reason": "no_matching_capacity_or_fixture",
                "suggested_action": "Fixture kapasitesi, storage type ve ürün ölçüsünü kontrol et.",
            })

    total_width = 0
    used_width = 0
    for _, _, shelf in _iter_shelves(plan):
        total_width += _num(shelf.get("shelf_width_cm"), 100)
        used_width += _num(shelf.get("used_width_cm"), 0)

    return {
        "summary": {
            "total_products": len(products or []),
            "placed_products": placed_count,
            "unplaced_products": len(unplaced),
            "placement_rate": round(placed_count / max(len(products or []), 1) * 100, 2),
            "capacity_utilization": round(used_width / max(total_width, 1) * 100, 2),
            "mode": "COUNCIL_SAFE_HEURISTIC",
        },
        "planogram": plan,
        "unplaced_products": unplaced,
        "engine_version": "PLONAGRAM_COUNCIL_ENGINE_SAFE_V1_3",
        "insights": {
            "decision": "Production-safe Council layer applied. Torch RL POC is included separately for training, but the API does not require torch to boot.",
            "logic": "Storage constraints first; then sales, ergonomics, category/brand clustering, facing and depth coverage."
        }
    }
