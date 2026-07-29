
from __future__ import annotations

from typing import Any, Dict, List
import math
import re

TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
    "ş": "s", "Ş": "s", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()

def norm(v: Any) -> str:
    return _s(v).translate(TR_MAP).lower().strip()

def num(v: Any, d: float = 0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return d
        x = float(str(v).replace(",", "."))
        if math.isnan(x) or math.isinf(x):
            return d
        return x
    except Exception:
        return d

def joined_text(product: Dict[str, Any]) -> str:
    keys = [
        "sku", "product_name", "product_name_local", "product_name_english",
        "brand", "brand_name", "category_l1", "category_l2",
        "frontend_category_local", "frontend_subcategory_local",
        "pim_cat_l1", "pim_cat_l2", "storage_type"
    ]
    return norm(" ".join(_s(product.get(k)) for k in keys))

def detect_family(product: Dict[str, Any]) -> str:
    t = joined_text(product)

    if any(x in t for x in ["karpuz", "watermelon"]):
        return "watermelon"
    if any(x in t for x in ["kavun", "melon"]):
        return "melon"
    if any(x in t for x in ["patates", "potato", "sogan", "soğan", "mandalina", "limon", "portakal", "domates", "muz", "elma", "armut"]):
        return "bulk_produce"
    if any(x in t for x in ["maden suyu", "mineral water", "soda", "beypazari", "beypazarı"]):
        return "mineral_water_bottle"
    if any(x in t for x in ["su ", "water", "cola", "kola", "fanta", "sprite", "ice tea", "meyve suyu"]):
        return "beverage_bottle"
    if any(x in t for x in ["cips", "chips", "lays", "ruffles", "doritos"]):
        return "chips_bag"
    if any(x in t for x in ["gofret", "çikolata", "cikolata", "bar", "chocolate"]):
        return "bar_chocolate"
    if any(x in t for x in ["sut", "süt", "milk", "ayran", "kefir"]):
        return "dairy_pack"
    if any(x in t for x in ["yogurt", "yoğurt", "peynir", "cheese"]):
        return "dairy_cup_or_pack"
    if any(x in t for x in ["deterjan", "domestos", "temizlik", "cleaner", "bleach"]):
        return "cleaning_bottle"
    return "generic"

FAMILY_BOUNDS_CM = {
    # min/max per single sellable unit or display unit.
    "mineral_water_bottle": {"min_w": 4, "max_w": 12, "min_d": 4, "max_d": 12, "min_h": 10, "max_h": 35, "expected": {"width_cm": 6, "depth_cm": 6, "height_cm": 18}},
    "beverage_bottle": {"min_w": 4, "max_w": 14, "min_d": 4, "max_d": 14, "min_h": 10, "max_h": 40, "expected": {"width_cm": 8, "depth_cm": 8, "height_cm": 28}},
    "chips_bag": {"min_w": 8, "max_w": 28, "min_d": 2, "max_d": 12, "min_h": 12, "max_h": 38, "expected": {"width_cm": 18, "depth_cm": 6, "height_cm": 25}},
    "bar_chocolate": {"min_w": 4, "max_w": 16, "min_d": 1, "max_d": 6, "min_h": 6, "max_h": 24, "expected": {"width_cm": 8, "depth_cm": 2, "height_cm": 16}},
    "dairy_pack": {"min_w": 5, "max_w": 14, "min_d": 5, "max_d": 14, "min_h": 8, "max_h": 28, "expected": {"width_cm": 8, "depth_cm": 8, "height_cm": 20}},
    "dairy_cup_or_pack": {"min_w": 5, "max_w": 18, "min_d": 5, "max_d": 18, "min_h": 4, "max_h": 22, "expected": {"width_cm": 10, "depth_cm": 10, "height_cm": 12}},
    "cleaning_bottle": {"min_w": 5, "max_w": 18, "min_d": 4, "max_d": 14, "min_h": 12, "max_h": 38, "expected": {"width_cm": 10, "depth_cm": 7, "height_cm": 28}},
    "bulk_produce": {"min_w": 4, "max_w": 30, "min_d": 4, "max_d": 30, "min_h": 4, "max_h": 30, "expected": {"width_cm": 12, "depth_cm": 10, "height_cm": 10}},
    "melon": {"min_w": 10, "max_w": 35, "min_d": 10, "max_d": 35, "min_h": 10, "max_h": 35, "expected": {"width_cm": 20, "depth_cm": 20, "height_cm": 18}},
    "watermelon": {"min_w": 15, "max_w": 55, "min_d": 15, "max_d": 45, "min_h": 12, "max_h": 35, "expected": {"width_cm": 35, "depth_cm": 25, "height_cm": 25}},
    "generic": {"min_w": 2, "max_w": 80, "min_d": 1, "max_d": 80, "min_h": 2, "max_h": 120, "expected": {"width_cm": 10, "depth_cm": 8, "height_cm": 18}},
}

WEIGHT_BOUNDS_KG = {
    "mineral_water_bottle": {"min": 0.15, "max": 2.0, "expected": 0.25},
    "beverage_bottle": {"min": 0.2, "max": 5.5, "expected": 1.0},
    "chips_bag": {"min": 0.03, "max": 0.8, "expected": 0.15},
    "bar_chocolate": {"min": 0.02, "max": 0.5, "expected": 0.08},
    "dairy_pack": {"min": 0.15, "max": 2.5, "expected": 1.0},
    "dairy_cup_or_pack": {"min": 0.05, "max": 2.0, "expected": 0.5},
    "cleaning_bottle": {"min": 0.2, "max": 6.0, "expected": 1.2},
    "bulk_produce": {"min": 0.02, "max": 5.0, "expected": 0.5},
    "melon": {"min": 0.8, "max": 8.0, "expected": 2.5},
    "watermelon": {"min": 2.0, "max": 18.0, "expected": 8.0},
    "generic": {"min": 0.01, "max": 20.0, "expected": 0.3},
}

def content_value(product: Dict[str, Any]) -> float:
    return num(product.get("product_weight_value") or product.get("contents_value") or product.get("net_content_value"), 0)

def content_unit(product: Dict[str, Any]) -> str:
    return norm(product.get("product_weight_unit") or product.get("contents_unit") or product.get("net_content_unit"))

def infer_weight_from_content(product: Dict[str, Any], family: str) -> float:
    val = content_value(product)
    unit = content_unit(product)
    if val <= 0:
        return WEIGHT_BOUNDS_KG.get(family, WEIGHT_BOUNDS_KG["generic"])["expected"]
    if unit in ["g", "gr", "gram"]:
        return round(val / 1000, 3)
    if unit in ["kg", "kilogram"]:
        return round(val, 3)
    if unit in ["ml", "milliliter"]:
        # liquids: approx 1kg / liter
        return round(val / 1000, 3)
    if unit in ["l", "lt", "liter", "litre"]:
        return round(val, 3)
    return WEIGHT_BOUNDS_KG.get(family, WEIGHT_BOUNDS_KG["generic"])["expected"]

def is_dimension_suspicious(w: float, d: float, h: float, family: str) -> List[str]:
    b = FAMILY_BOUNDS_CM.get(family, FAMILY_BOUNDS_CM["generic"])
    reasons = []
    if w <= 0 or d <= 0 or h <= 0:
        reasons.append("missing_dimension")
    if 0 < w < b["min_w"]:
        reasons.append(f"width_too_small_for_{family}")
    if 0 < d < b["min_d"]:
        reasons.append(f"depth_too_small_for_{family}")
    if 0 < h < b["min_h"]:
        reasons.append(f"height_too_small_for_{family}")
    if w > b["max_w"]:
        reasons.append(f"width_too_large_for_{family}")
    if d > b["max_d"]:
        reasons.append(f"depth_too_large_for_{family}")
    if h > b["max_h"]:
        reasons.append(f"height_too_large_for_{family}")

    # Classic catalog bug: 1 cm dimension because content/pack count leaked into physical size.
    if min([x for x in [w, d, h] if x > 0] or [0]) <= 1.5:
        reasons.append("catalog_dimension_looks_like_content_or_unit_count")

    # Meter-scale error: often 200 cm / 500 cm from gram/ml or badly parsed meters.
    if max(w, d, h) >= 150 and family not in ["generic"]:
        reasons.append("dimension_meter_scale_or_content_leak")

    return reasons

def is_weight_suspicious(weight_kg: float, family: str) -> List[str]:
    b = WEIGHT_BOUNDS_KG.get(family, WEIGHT_BOUNDS_KG["generic"])
    reasons = []
    if weight_kg <= 0:
        reasons.append("missing_weight")
    elif weight_kg < b["min"]:
        reasons.append(f"weight_too_low_for_{family}")
    elif weight_kg > b["max"]:
        reasons.append(f"weight_too_high_for_{family}")
    return reasons

def sanitize_dimensions(product: Dict[str, Any], similar_decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    p = dict(product or {})
    family = detect_family(p)

    w = num(p.get("width_cm") or p.get("product_width_in_cm"), 0)
    d = num(p.get("depth_cm") or p.get("product_length_in_cm"), 0)
    h = num(p.get("height_cm") or p.get("product_height_in_cm"), 0)
    weight = num(p.get("weight_kg") or p.get("product_weight_kg"), 0)

    dim_reasons = is_dimension_suspicious(w, d, h, family)
    weight_reasons = is_weight_suspicious(weight, family)

    bounds = FAMILY_BOUNDS_CM.get(family, FAMILY_BOUNDS_CM["generic"])
    expected = dict(bounds["expected"])

    if similar_decision:
        sim_dims = ((similar_decision or {}).get("decision") or {}).get("dimensions") or {}
        sw = num(sim_dims.get("width_cm"), 0)
        sd = num(sim_dims.get("depth_cm"), 0)
        sh = num(sim_dims.get("height_cm"), 0)
        if sw > 0 and sd > 0 and sh > 0:
            expected = {"width_cm": sw, "depth_cm": sd, "height_cm": sh}

    fixed = False
    if dim_reasons:
        p["width_cm"] = expected["width_cm"]
        p["depth_cm"] = expected["depth_cm"]
        p["height_cm"] = expected["height_cm"]
        p["dimension_source"] = "ai_sanity_family_or_similar"
        p["dimension_confidence"] = 0.72 if family != "generic" else 0.48
        fixed = True

    if weight_reasons:
        inferred = infer_weight_from_content(p, family)
        wb = WEIGHT_BOUNDS_KG.get(family, WEIGHT_BOUNDS_KG["generic"])
        # Clamp to plausible market range. Heavy produce like watermelon should not be flattened to 0.3 kg.
        inferred = max(wb["min"], min(wb["max"], inferred))
        p["weight_kg"] = inferred
        p["weight_source"] = "ai_sanity_content_or_family"
        fixed = True

    p["ai_sanity"] = {
        "family": family,
        "fixed": fixed,
        "dimension_reasons": dim_reasons,
        "weight_reasons": weight_reasons,
        "note": build_note(family, dim_reasons, weight_reasons),
    }
    return p

def build_note(family: str, dim_reasons: List[str], weight_reasons: List[str]) -> str:
    notes = []
    if dim_reasons:
        notes.append(f"Ölçü şüpheli: {', '.join(dim_reasons)}. {family} ailesi için piyasa makul ölçüsü kullanıldı.")
    if weight_reasons:
        notes.append(f"Ağırlık şüpheli: {', '.join(weight_reasons)}. Gram/ml içerikten veya ürün ailesinden makul kg tahmini yapıldı.")
    if family == "watermelon":
        notes.append("Karpuz gibi ağır ve hacimli ürünlerde 1 cm / 0.1 kg gibi değerler kabul edilmez; ürün ailesi bazlı ağır ürün mantığı uygulanır.")
    return " ".join(notes) if notes else "Ölçü/ağırlık makul görünüyor."
