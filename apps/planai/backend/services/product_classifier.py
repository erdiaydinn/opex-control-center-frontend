"""Product classification for physics-first planogram placement."""
from __future__ import annotations

import re
from typing import Any, Dict


def _text(v: Any) -> str:
    return str(v or "").strip()


def _norm(v: Any) -> str:
    return (
        _text(v).lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def _hay(product: Dict[str, Any]) -> str:
    fields = [
        product.get("sku"), product.get("barcode"), product.get("product_name"),
        product.get("name"), product.get("brand"), product.get("brand_name"),
        product.get("category_l1"), product.get("category_l2"),
        product.get("frontend_category_local"), product.get("frontend_subcategory_local"),
        product.get("storage_type"), product.get("Storage Type"),
    ]
    return _norm(" ".join(_text(x) for x in fields))


def num(v: Any, d: float = 0) -> float:
    try:
        if v is None or v == "":
            return d
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except Exception:
        return d


def brand(product: Dict[str, Any]) -> str:
    return _text(product.get("brand") or product.get("brand_name") or "UNKNOWN")


def sku(product: Dict[str, Any]) -> str:
    return _text(product.get("sku") or product.get("SKU") or product.get("barcode") or "")


def product_name(product: Dict[str, Any]) -> str:
    return _text(product.get("product_name") or product.get("Product Name") or product.get("name") or sku(product))


def classify_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Return a normalized product with storage_class and merch_group.

    storage_class is physical/temperature. merch_group is adjacency/merchandising.
    """
    p = dict(product or {})
    raw_storage = _norm(p.get("storage_class") or p.get("storage_type") or p.get("Storage Type"))
    hay = _hay(p)
    b = _norm(brand(p))

    # Brand / product-specific overrides first.
    if "algida" in b or "algida" in hay or "ice cream" in hay or "dondurma" in hay:
        storage_class = "ICE_CREAM"
        merch_group = "ICE_CREAM"
    elif raw_storage in {"ice_cream", "icecream"}:
        storage_class = "ICE_CREAM"
        merch_group = "ICE_CREAM"
    elif raw_storage in {"frozen", "donuk", "-18"} or any(x in hay for x in ["frozen", "donuk", "-18", "la lorraine", "dondurulmus", "dondurulmuş"]):
        storage_class = "FROZEN"
        merch_group = "BAKERY_FROZEN" if "la lorraine" in hay or "bakery" in hay or "firin" in hay else "FOOD_FROZEN"
    elif raw_storage in {"chilled", "cold", "+4", "soguk", "soğuk"} or any(x in hay for x in ["sut", "süt", "yogurt", "yoğurt", "peynir", "ayran", "sarkuteri", "şarküteri", "+4", "chilled"]):
        storage_class = "CHILLED"
        merch_group = "FOOD_CHILLED"
    elif any(x in hay for x in ["maydanoz", "marul", "roka", "dereotu", "yesillik", "yeşillik", "kivircik", "kıvırcık"]):
        storage_class = "FRESH_PRODUCE_CHILLED"
        merch_group = "PRODUCE_CHILLED"
    elif any(x in hay for x in ["patates", "sogan", "soğan", "mandalina", "portakal", "limon", "muz", "elma", "domates", "salatalik", "salatalık"]):
        storage_class = "FRESH_PRODUCE_AMBIENT"
        merch_group = "PRODUCE_AMBIENT"
    else:
        storage_class = "AMBIENT"
        if any(x in hay for x in ["domestos", "deterjan", "camasir", "çamaşır", "yumusatici", "yumuşatıcı", "bleach", "temizleyici", "temizlik", "sampuan", "şampuan", "sabun"]):
            merch_group = "NON_FOOD_ODOR"
        elif any(x in hay for x in ["pecete", "peçete", "kagit", "kağıt", "poset", "poşet", "folyo", "strec", "streç", "pet ", "kedi", "kopek", "köpek"]):
            merch_group = "NON_FOOD_NEUTRAL"
        elif num(p.get("weight_kg") or p.get("product_weight_value"), 0) >= 3 or any(x in hay for x in ["5 l", "5l", "10 l", "10l", "damacana"]):
            storage_class = "AMBIENT_HEAVY"
            merch_group = "HEAVY_AMBIENT"
        else:
            merch_group = "FOOD_AMBIENT"

    # Enforce explicit user/catalog storage when not conflicting with richer classification.
    if raw_storage in {"ambient", "ambient_heavy"} and storage_class not in {"ICE_CREAM", "FROZEN", "CHILLED", "FRESH_PRODUCE_AMBIENT", "FRESH_PRODUCE_CHILLED"}:
        storage_class = "AMBIENT_HEAVY" if raw_storage == "ambient_heavy" else "AMBIENT"

    p["sku"] = sku(p)
    p["product_name"] = product_name(p)
    p["brand"] = brand(p)
    p["storage_class"] = storage_class
    p["storage_type"] = storage_class
    p["merch_group"] = merch_group
    p["width_cm"] = num(p.get("width_cm") or p.get("Width") or p.get("product_width_in_cm"), 0)
    p["height_cm"] = num(p.get("height_cm") or p.get("Height") or p.get("product_height_in_cm"), 0)
    p["depth_cm"] = num(p.get("depth_cm") or p.get("Depth") or p.get("product_length_in_cm"), 0)
    p["weight_kg"] = max(0.01, num(p.get("weight_kg") or p.get("product_weight_value"), 0.2))
    p["daily_sales"] = num(p.get("daily_sales") or p.get("sales_qty_7d"), 0) / (7 if p.get("sales_qty_7d") and not p.get("daily_sales") else 1)
    p["sales_qty_7d"] = num(p.get("sales_qty_7d") or p.get("sales_7d"), 0)
    p["percent_orders"] = num(p.get("percent_orders") or p.get("% Orders"), 0)
    p["percent_stops"] = num(p.get("percent_stops") or p.get("% Stops"), 0)
    return p


def is_food_group(merch_group: str) -> bool:
    return str(merch_group or "").upper().startswith("FOOD") or str(merch_group or "").upper().startswith("PRODUCE") or str(merch_group or "").upper() in {"ICE_CREAM", "BAKERY_FROZEN"}


def is_odor_group(merch_group: str) -> bool:
    return str(merch_group or "").upper() == "NON_FOOD_ODOR"
