from __future__ import annotations

from typing import Any, Dict


CATEGORY_COLORS = {
    "BEVERAGES": "#4F8CFF",
    "WATER": "#2EB7FF",
    "READY TO CONSUME": "#FF9F43",
    "HOME / PET": "#A889FF",
    "DAIRY": "#18C7DF",
    "FROZEN": "#7B61FF",
    "ICE CREAM": "#7B61FF",
    "FRUITS / VEGETABLES": "#17A66A",
    "FOOD": "#F5B900",
    "GENERAL": "#657085",
}


def _text(v: Any, default: str = "") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _upper(v: Any) -> str:
    return _text(v).upper()


def pick_image_url(product: Dict[str, Any]) -> tuple[str, str]:
    """Visual precedence: ABC image > visual override > catalog image > fallback."""
    candidates = [
        ("abc_upload", product.get("abc_image_url")),
        ("abc_upload", product.get("Product Image URL")),
        ("abc_upload", product.get("image_url")),
        ("visual_override", product.get("visual_override_url")),
        ("catalog", product.get("catalog_image_url")),
        ("catalog", product.get("pim_image_url")),
        ("catalog", product.get("master_image_url")),
    ]
    for source, url in candidates:
        url = _text(url)
        if url.startswith("http://") or url.startswith("https://"):
            return url, source
    return "", "fallback"


def fallback_visual(product: Dict[str, Any]) -> Dict[str, Any]:
    cat1 = _upper(product.get("category_l1") or product.get("frontend_category_local") or "GENERAL")
    cat2 = _upper(product.get("category_l2") or product.get("frontend_subcategory_local") or "")
    storage = _upper(product.get("storage_type") or product.get("storage_class") or "AMBIENT")
    brand = _text(product.get("brand") or product.get("brand_name") or "")
    name = _text(product.get("product_name") or product.get("name") or "Product")

    color = CATEGORY_COLORS.get(cat1) or CATEGORY_COLORS.get(cat2) or CATEGORY_COLORS["GENERAL"]
    if storage == "CHILLED":
        color = "#18C7DF"
    elif storage in ["FROZEN", "ICE_CREAM"]:
        color = "#7B61FF"

    label = brand[:10] if brand else name[:10]
    return {
        "kind": "generated_package_tile",
        "label": label,
        "category_l1": cat1,
        "category_l2": cat2,
        "storage_type": storage,
        "color": color,
    }


def resolve_product_visual(product: Dict[str, Any]) -> Dict[str, Any]:
    url, source = pick_image_url(product or {})
    return {
        "image_url": url,
        "visual_source": source,
        "fallback_visual": fallback_visual(product or {}),
    }


def attach_visual(product: Dict[str, Any]) -> Dict[str, Any]:
    visual = resolve_product_visual(product)
    out = dict(product or {})
    out["image_url"] = visual["image_url"] or out.get("image_url", "")
    out["visual_source"] = visual["visual_source"]
    out["fallback_visual"] = visual["fallback_visual"]
    return out
