from typing import Any, Dict, List, Optional
from collections import Counter

try:
    from services.product_visual_resolver import resolve_product_visual
except Exception:
    def resolve_product_visual(product: Dict[str, Any]) -> Dict[str, Any]:
        url = product.get("image_url") or product.get("Product Image URL") or product.get("catalog_image_url") or product.get("pim_image_url") or ""
        if url:
            return {"visual_type": "image_url", "image_url": url, "visual_source": "product"}
        return {
            "visual_type": "category_fallback",
            "image_url": "",
            "visual_source": "fallback",
            "fallback_label": (product.get("brand") or product.get("brand_name") or product.get("category_l1") or "SKU")[:12],
        }


def _num(v, default=0):
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except Exception:
        return default


def _get(d: Dict[str, Any], *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d.get(k) not in [None, ""]:
            return d.get(k)
    return default


def normalize_product_for_twin(product: Dict[str, Any]) -> Dict[str, Any]:
    visual = resolve_product_visual(product or {})
    storage = str(_get(product, "storage_type", "storage_class", "_storage", "Storage Type", default="AMBIENT")).upper()

    return {
        "sku": str(_get(product, "sku", "SKU", "barcode", default="")),
        "barcode": str(_get(product, "barcode", "Barcodes", "product_barcodes", default="")),
        "product_name": str(_get(product, "product_name", "Product Name", "name", default="Unnamed Product")),
        "brand": str(_get(product, "brand", "brand_name", "Brand", default="UNKNOWN")),
        "category_l1": str(_get(product, "category_l1", "Category L1", "frontend_category_local", default="GENERAL")),
        "category_l2": str(_get(product, "category_l2", "Category L2", "frontend_subcategory_local", default="GENERAL")),
        "storage_type": storage,
        "abc_class": str(_get(product, "abc_class", "ABC", "_abc", default="")),
        "rank": _num(_get(product, "rank", "Rank", default=0), 0),
        "order_share_pct": _num(_get(product, "order_share_pct", "% Orders", "percent_orders", default=0), 0),
        "stop_share_pct": _num(_get(product, "stop_share_pct", "% Stops", "percent_stops", default=0), 0),
        "on_hand_qty": _num(_get(product, "on_hand_qty", "On-Hand Qty", default=0), 0),
        "current_location": str(_get(product, "current_location", "Location", default="")),
        "secondary_location": str(_get(product, "secondary_location", "Secondary Location", default="")),
        "image_url": visual.get("image_url", ""),
        "visual": visual,
        "width_cm": _num(_get(product, "width_cm", "product_width_in_cm", default=10), 10),
        "height_cm": _num(_get(product, "height_cm", "product_height_in_cm", default=20), 20),
        "depth_cm": _num(_get(product, "depth_cm", "product_length_in_cm", default=10), 10),
        "weight_kg": _num(_get(product, "weight_kg", "product_weight_value", default=0.2), 0.2),
        "facing": int(_num(_get(product, "facing", "facing_count", default=1), 1)),
        "facing_count": int(_num(_get(product, "facing_count", "facing", default=1), 1)),
        "depth_units": int(_num(_get(product, "depth_units", default=1), 1)),
    }


def _iter_placed_products(planogram: Dict[str, Any]):
    for aisle in (planogram or {}).get("aisles", []):
        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                for p in shelf.get("products", []):
                    yield aisle, module, shelf, p


def build_visual_twin_payload(
    planogram_result: Dict[str, Any],
    merged_products: Optional[List[Dict[str, Any]]] = None,
    excluded_products: Optional[List[Dict[str, Any]]] = None,
    review_products: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Converts planogram + V1.9 pipeline output into a 3D/2D product-visual payload.

    Rule:
    - Product names are metadata, not default 3D labels.
    - `image_url` / `visual` are first-class fields for shelf tile render.
    - excluded_products never enter the 3D shelf scene.
    """
    planogram_result = planogram_result or {}
    planogram = planogram_result.get("planogram") or planogram_result.get("layout") or {}
    excluded_products = excluded_products or planogram_result.get("excluded_products") or []
    review_products = review_products or planogram_result.get("review_products") or []

    shelves = []
    placed_tiles = []

    for aisle, module, shelf, product in _iter_placed_products(planogram):
        shelf_id = f"{aisle.get('aisle_id')}|{module.get('module_id')}|{shelf.get('shelf_no')}"
        normalized = normalize_product_for_twin(product)

        tile = {
            **normalized,
            "shelf_id": shelf_id,
            "aisle_id": aisle.get("aisle_id"),
            "module_id": module.get("module_id"),
            "shelf_no": shelf.get("shelf_no"),
            "position_order": _num(product.get("position_order"), len(placed_tiles) + 1),
            "render_mode": "image_tile" if normalized.get("image_url") else "fallback_tile",
            "show_text_label_default": False,
        }
        placed_tiles.append(tile)

        if not any(s["shelf_id"] == shelf_id for s in shelves):
            shelves.append({
                "shelf_id": shelf_id,
                "aisle_id": aisle.get("aisle_id"),
                "module_id": module.get("module_id"),
                "shelf_no": shelf.get("shelf_no"),
                "storage_type": shelf.get("allowed_storage_type") or shelf.get("storage_type") or "",
                "shelf_width_cm": _num(shelf.get("shelf_width_cm"), 100),
                "shelf_depth_cm": _num(shelf.get("shelf_depth_cm"), 50),
                "shelf_height_cm": _num(shelf.get("shelf_height_cm"), 35),
                "used_width_cm": _num(shelf.get("used_width_cm") or shelf.get("used"), 0),
            })

    visual_counts = Counter("with_image" if p.get("image_url") else "fallback" for p in placed_tiles)
    storage_counts = Counter(p.get("storage_type") for p in placed_tiles)

    return {
        "status": "success",
        "scene_version": "V1_9_3_VISUAL_PRODUCT_TWIN",
        "summary": {
            "placed_tiles": len(placed_tiles),
            "with_image": visual_counts.get("with_image", 0),
            "fallback_tiles": visual_counts.get("fallback", 0),
            "excluded_products": len(excluded_products or []),
            "review_products": len(review_products or []),
            "storage_counts": dict(storage_counts),
        },
        "scene_rules": {
            "default_product_text_labels": False,
            "render_product_images": True,
            "excluded_products_enter_scene": False,
            "location_field_usage": "delta_only",
        },
        "shelves": shelves,
        "product_tiles": placed_tiles,
        "excluded_products": [normalize_product_for_twin(p) | {
            "planogram_class": p.get("planogram_class"),
            "reason_code": p.get("reason_code"),
            "human_action": p.get("human_action"),
        } for p in excluded_products or []],
        "review_products": [normalize_product_for_twin(p) | {
            "planogram_class": p.get("planogram_class"),
            "reason_code": p.get("reason_code"),
            "human_action": p.get("human_action"),
        } for p in review_products or []],
    }