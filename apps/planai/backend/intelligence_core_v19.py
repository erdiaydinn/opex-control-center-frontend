"""
Plonagram V1.9 Spatial + Intelligence Core

Purpose:
- Make catalog fields operational truth instead of decoration.
- Make case_pack_qty a hard operational constraint.
- Produce product-level placement confidence and plan-level AI confidence.
- Provide shelf swap/add/remove impact comparison, like a FIFA substitution view.

This module is pure Python and safe to import from FastAPI routes or tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
import math
import unicodedata


NO_INFO_VALUES = {"", "0", "x", "xx", "nan", "none", "null", "bilgi yok", "unknown", "-", "--"}


def clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"nan", "none", "null"}:
        return ""
    return s


def norm(v: Any) -> str:
    s = clean(v).lower()
    # Turkish-safe normalization for rule matching, not for display.
    s = s.replace("ı", "i").replace("İ", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.strip()


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or clean(v) == "":
            return default
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except Exception:
        return default


def intval(v: Any, default: int = 0) -> int:
    try:
        return int(float(str(v).replace(",", ".").strip()))
    except Exception:
        return default


def get_any(d: Dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    if not isinstance(d, dict):
        return default
    lower = {str(k).lower(): k for k in d.keys()}
    for k in keys:
        if k in d and d[k] not in [None, ""]:
            return d[k]
        real = lower.get(str(k).lower())
        if real is not None and d[real] not in [None, ""]:
            return d[real]
    return default


def sku_of(p: Dict[str, Any]) -> str:
    return clean(get_any(p, ["sku", "SKU", "barcode", "product_barcodes"], ""))


def name_of(p: Dict[str, Any]) -> str:
    return clean(get_any(p, ["product_name", "product_name_local", "name", "Product Name"], ""))


def brand_of(p: Dict[str, Any]) -> str:
    b = clean(get_any(p, ["brand", "brand_name", "Brand"], ""))
    if b:
        return b
    n = name_of(p)
    return n.split(" ")[0] if n else "UNKNOWN"


def cat1_of(p: Dict[str, Any]) -> str:
    return clean(get_any(p, ["category_l1", "frontend_category_local", "Category L1", "category"], "GENERAL")) or "GENERAL"


def cat2_of(p: Dict[str, Any]) -> str:
    return clean(get_any(p, ["category_l2", "frontend_subcategory_local", "Category L2", "subcategory"], "GENERAL")) or "GENERAL"


def width_of(p: Dict[str, Any]) -> float:
    return max(0.0, num(get_any(p, ["width_cm", "product_width_in_cm", "Width", "en"], 0), 0))


def depth_of(p: Dict[str, Any]) -> float:
    return max(0.0, num(get_any(p, ["depth_cm", "product_length_in_cm", "length_cm", "Depth", "derinlik"], 0), 0))


def height_of(p: Dict[str, Any]) -> float:
    return max(0.0, num(get_any(p, ["height_cm", "product_height_in_cm", "Height", "boy"], 0), 0))


def weight_of(p: Dict[str, Any]) -> float:
    return max(0.0, num(get_any(p, ["weight_kg", "product_weight_value", "Weight"], 0), 0))


def case_pack_of(p: Dict[str, Any]) -> int:
    cp = intval(get_any(p, ["case_pack_qty", "case_pack", "Case Pack", "units_in_pack_count"], 0), 0)
    return max(0, cp)


def sales_of(p: Dict[str, Any]) -> float:
    return num(get_any(p, ["sales_qty_7d", "sales_7d", "daily_sales", "sales", "Sales 7D"], 0), 0)


def normalize_storage_type(v: Any) -> str:
    n = norm(v).upper()
    if n in {"AMBIENT", "RAF", "SHELF", "ROOM", "DRY"}:
        return "AMBIENT"
    if n in {"CHILLED", "DOLAP", "+4", "FRIDGE", "COOLER", "COLD"}:
        return "CHILLED"
    if n in {"FROZEN", "DONUK", "-18", "FREEZER", "DONDURMA"}:
        return "FROZEN"
    return ""


def resolve_fixture_target(product: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve where the product must go.

    Priority:
    1) storage_raw as the hard fixture source.
    2) storage_type if storage_raw is empty/0/x/unknown.
    3) category/name fallback only if the previous two are unusable.
    """
    raw_original = clean(get_any(product, ["storage_raw", "Storage Raw"], ""))
    raw = norm(raw_original)
    st_original = clean(get_any(product, ["storage_type", "Storage Type", "storage"], ""))
    st = normalize_storage_type(st_original)
    warning = None

    def result(storage_type: str, fixture_target: str, source: str, confidence: float) -> Dict[str, Any]:
        nonlocal warning
        if st and st != storage_type and source == "storage_raw":
            warning = "storage_raw_storage_type_conflict"
        return {
            "storage_type": storage_type,
            "fixture_target": fixture_target,
            "placement_source": source,
            "placement_confidence_source": confidence,
            "storage_raw": raw_original,
            "catalog_storage_type": st_original,
            "data_quality_warning": warning,
        }

    if raw not in NO_INFO_VALUES:
        if any(x in raw for x in ["raf", "shelf", "ambient", "dry"]):
            return result("AMBIENT", "SHELF", "storage_raw", 1.0)
        if any(x in raw for x in ["dolap", "+4", "chill", "fridge", "cooler", "soguk", "sogut"]):
            return result("CHILLED", "FRIDGE", "storage_raw", 1.0)
        if any(x in raw for x in ["donuk", "-18", "frozen", "freezer", "dondurma", "algida"]):
            return result("FROZEN", "FREEZER", "storage_raw", 1.0)
        warning = "unrecognized_storage_raw"

    if st:
        if st == "AMBIENT":
            return result("AMBIENT", "SHELF", "storage_type", 0.85)
        if st == "CHILLED":
            return result("CHILLED", "FRIDGE", "storage_type", 0.85)
        if st == "FROZEN":
            return result("FROZEN", "FREEZER", "storage_type", 0.85)

    hay = norm(" ".join([name_of(product), brand_of(product), cat1_of(product), cat2_of(product)]))
    if any(x in hay for x in ["dondurma", "donuk", "frozen", "ice cream", "algida", "-18"]):
        return result("FROZEN", "FREEZER", "category_inference", 0.55)
    if any(x in hay for x in ["sut", "yogurt", "peynir", "et", "tavuk", "chilled", "+4", "soguk"]):
        return result("CHILLED", "FRIDGE", "category_inference", 0.55)
    return result("AMBIENT", "SHELF", "fallback_default", 0.35)


def shelf_fixture_target(aisle: Dict[str, Any], module: Dict[str, Any], shelf: Dict[str, Any]) -> str:
    raw = norm(" ".join([
        clean(get_any(module, ["fixture_type", "module_type", "type"], "")),
        clean(get_any(aisle, ["fixture_type", "zone_type", "aisle_type"], "")),
        clean(get_any(shelf, ["allowed_storage_type"], "")),
        clean(get_any(module, ["temperature"], "")),
        clean(get_any(aisle, ["temperature"], "")),
    ]))
    if any(x in raw for x in ["freezer", "frozen", "donuk", "-18", "algida"]):
        return "FREEZER"
    if any(x in raw for x in ["fridge", "chilled", "dolap", "cooler", "+4", "cold"]):
        return "FRIDGE"
    return "SHELF"


def iter_shelves(plan: Dict[str, Any]) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], str]]:
    """Yield aisle, module, shelf, side.

    Supports both legacy layout:
      aisle.modules[].shelves[]
    and V2 spatial layout:
      aisle.faces.L.modules[].shelves[]
    """
    for aisle in plan.get("aisles", []) or []:
        faces = aisle.get("faces")
        if isinstance(faces, dict):
            for side, face in faces.items():
                for module in face.get("modules", []) or []:
                    module.setdefault("side", side)
                    for shelf in module.get("shelves", []) or []:
                        yield aisle, module, shelf, str(side)
        else:
            for module in aisle.get("modules", []) or []:
                side = clean(module.get("side") or "")
                for shelf in module.get("shelves", []) or []:
                    yield aisle, module, shelf, side


def depth_units(product: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    d = depth_of(product)
    shelf_depth = num(get_any(shelf, ["shelf_depth_cm", "depth_cm"], 50), 50)
    if d <= 0:
        return 0
    return max(1, int(shelf_depth // d))


def facing_units(product: Dict[str, Any]) -> int:
    return max(1, intval(get_any(product, ["facing_count", "facing", "visible_facing"], 1), 1))


def raw_capacity_units(product: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    return facing_units(product) * depth_units(product, shelf)


def case_pack_rounded_units(raw_units: int, case_pack_qty: int) -> Dict[str, Any]:
    if raw_units <= 0:
        return {"units": 0, "rounding_applied": False, "extra_units": 0}
    if case_pack_qty <= 1:
        return {"units": raw_units, "rounding_applied": False, "extra_units": 0}
    rounded = int(math.ceil(raw_units / case_pack_qty) * case_pack_qty)
    return {
        "units": rounded,
        "rounding_applied": rounded != raw_units,
        "extra_units": rounded - raw_units,
    }


def width_fit(product: Dict[str, Any], shelf: Dict[str, Any]) -> bool:
    shelf_width = num(get_any(shelf, ["shelf_width_cm", "width_cm"], 100), 100)
    used = num(get_any(shelf, ["used_width_cm", "used"], 0), 0)
    needed = width_of(product) * facing_units(product) * 1.08
    return used + needed <= shelf_width + 0.0001


def dimension_fit(product: Dict[str, Any], shelf: Dict[str, Any]) -> bool:
    shelf_height = num(get_any(shelf, ["shelf_height_cm", "height_cm"], 35), 35)
    shelf_depth = num(get_any(shelf, ["shelf_depth_cm", "depth_cm"], 50), 50)
    return height_of(product) <= shelf_height + 0.0001 and depth_of(product) <= shelf_depth + 0.0001


def product_placement_confidence(
    product: Dict[str, Any],
    aisle: Optional[Dict[str, Any]] = None,
    module: Optional[Dict[str, Any]] = None,
    shelf: Optional[Dict[str, Any]] = None,
    existing_products: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    target = resolve_fixture_target(product)
    reasons: List[str] = []
    warnings: List[str] = []

    score = 0.0

    # 25 pts: storage_raw/storage_type confidence.
    source_conf = float(target.get("placement_confidence_source", 0.35))
    score += 25 * source_conf
    if target.get("placement_source") == "storage_raw":
        reasons.append(f"storage_raw='{target.get('storage_raw')}' fixture hedefini net verdi")
    elif target.get("placement_source") == "storage_type":
        reasons.append("storage_type ile fixture hedefi belirlendi")
    else:
        warnings.append("storage_raw ve storage_type eksik/kararsız; kategori fallback kullanıldı")

    if target.get("data_quality_warning"):
        warnings.append(str(target["data_quality_warning"]))
        score -= 8

    # 20 pts: dimensions.
    dims_ok = width_of(product) > 0 and depth_of(product) > 0 and height_of(product) > 0
    dim_source = norm(get_any(product, ["dimension_source"], "catalog"))
    if dims_ok:
        dim_points = 20 if dim_source not in {"ai_estimated", "estimated", "fallback"} else 12
        score += dim_points
        reasons.append("ürün ölçüleri mevcut")
        if dim_points < 20:
            warnings.append("ürün ölçüsü tahmini; doğrulama önerilir")
    else:
        warnings.append("ürün ölçüsü eksik")

    # 15 pts: case pack.
    cp = case_pack_of(product)
    if cp > 1:
        score += 15
        reasons.append(f"case_pack_qty mevcut: {cp}")
    else:
        score += 4
        warnings.append("case_pack_qty eksik; koli bazlı öneri zayıf")

    # 15 pts: fixture/capacity fit if shelf context exists.
    if aisle is not None and module is not None and shelf is not None:
        actual_fixture = shelf_fixture_target(aisle, module, shelf)
        if actual_fixture == target["fixture_target"]:
            score += 8
            reasons.append("fixture hedefi ile raf/dolap tipi uyumlu")
        else:
            warnings.append(f"fixture uyumsuz: beklenen {target['fixture_target']}, mevcut {actual_fixture}")
            score -= 12

        if dimension_fit(product, shelf) and width_fit(product, shelf):
            score += 7
            reasons.append("raf kapasite/ölçü uyumu var")
        else:
            warnings.append("raf kapasite veya ölçü uyumu zayıf")
            score -= 8
    else:
        score += 7
        warnings.append("raf bağlamı yok; fixture/capacity confidence kısmi hesaplandı")

    # 10 pts: category/brand compatibility.
    if existing_products:
        c1 = norm(cat1_of(product))
        c2 = norm(cat2_of(product))
        b = norm(brand_of(product))
        same_cat1 = sum(1 for p in existing_products if norm(cat1_of(p)) == c1)
        same_cat2 = sum(1 for p in existing_products if norm(cat2_of(p)) == c2)
        same_brand = sum(1 for p in existing_products if norm(brand_of(p)) == b)
        if same_brand > 0 or same_cat2 > 0:
            score += 10
            reasons.append("aynı marka/alt kategori bloğuna uyumlu")
        elif same_cat1 > 0:
            score += 7
            reasons.append("aynı ana kategori bloğuna uyumlu")
        else:
            score += 3
            warnings.append("raf içi kategori/marka yakınlığı düşük")
    else:
        score += 6

    # 10 pts: ABC/sales data confidence.
    abc = clean(get_any(product, ["abc", "abc_class", "ABC"], ""))
    sales = sales_of(product)
    if abc or sales > 0:
        score += 10
        reasons.append("ABC/satış verisi mevcut")
    else:
        score += 3
        warnings.append("ABC/satış verisi eksik; öneri sıralaması daha az güvenilir")

    score = max(0, min(100, round(score)))
    if score >= 85:
        level = "HIGH"
    elif score >= 65:
        level = "MEDIUM"
    else:
        level = "LOW"

    raw_units = raw_capacity_units(product, shelf or {}) if shelf else intval(get_any(product, ["raw_recommended_units"], 0), 0)
    rounded = case_pack_rounded_units(raw_units, cp)

    return {
        "sku": sku_of(product),
        "product_name": name_of(product),
        "brand": brand_of(product),
        "category_l1": cat1_of(product),
        "category_l2": cat2_of(product),
        "storage_type": target["storage_type"],
        "fixture_target": target["fixture_target"],
        "placement_source": target["placement_source"],
        "placement_confidence": score,
        "confidence_level": level,
        "confidence_reasons": reasons[:8],
        "confidence_warnings": warnings[:8],
        "case_pack_qty": cp,
        "raw_capacity_units": raw_units,
        "case_pack_rounded_units": rounded["units"],
        "case_pack_rounding_applied": rounded["rounding_applied"],
        "case_pack_extra_units": rounded["extra_units"],
        "print_visible": False,
    }


def shelf_category_violations(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    violations = []
    if len(products) <= 1:
        return violations
    cat1s = {norm(cat1_of(p)) for p in products if norm(cat1_of(p))}
    cat2s = {norm(cat2_of(p)) for p in products if norm(cat2_of(p))}
    if len(cat1s) > 1:
        violations.append({"type": "mixed_category_l1", "categories": sorted(cat1s)})
    if len(products) >= 3 and len(cat2s) > 2:
        violations.append({"type": "mixed_category_l2", "categories": sorted(cat2s)})
    return violations


def score_planogram_intelligence(plan: Dict[str, Any]) -> Dict[str, Any]:
    product_count = 0
    confidence_scores: List[int] = []
    violations: List[Dict[str, Any]] = []
    case_pack_missing = 0
    case_pack_rounding = 0
    storage_violations = 0
    category_violations = 0
    capacity_violations = 0

    for aisle, module, shelf, side in iter_shelves(plan):
        products = shelf.get("products", []) or []
        category_issues = shelf_category_violations(products)
        if category_issues:
            category_violations += len(category_issues)
            violations.extend([
                {
                    **issue,
                    "aisle_id": aisle.get("aisle_id"),
                    "side": side,
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                }
                for issue in category_issues
            ])

        for product in products:
            product_count += 1
            conf = product_placement_confidence(product, aisle, module, shelf, existing_products=products)
            confidence_scores.append(conf["placement_confidence"])
            if conf["fixture_target"] != shelf_fixture_target(aisle, module, shelf):
                storage_violations += 1
                violations.append({
                    "type": "storage_fixture_violation",
                    "sku": conf["sku"],
                    "product_name": conf["product_name"],
                    "expected_fixture": conf["fixture_target"],
                    "actual_fixture": shelf_fixture_target(aisle, module, shelf),
                    "aisle_id": aisle.get("aisle_id"),
                    "side": side,
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                })
            if not dimension_fit(product, shelf) or not width_fit(product, shelf):
                capacity_violations += 1
            if conf["case_pack_qty"] <= 1:
                case_pack_missing += 1
            if conf["case_pack_rounding_applied"]:
                case_pack_rounding += 1

    avg_conf = round(sum(confidence_scores) / len(confidence_scores), 1) if confidence_scores else 0

    storage_score = max(0, 20 - storage_violations * 3)
    fixture_score = max(0, 15 - storage_violations * 2)
    capacity_score = max(0, 15 - capacity_violations * 2)
    category_score = max(0, 10 - category_violations * 2)
    case_pack_score = 15 if product_count == 0 else max(0, 15 - round((case_pack_missing / max(product_count, 1)) * 15))
    confidence_component = round(avg_conf * 0.25)

    planogram_score = min(100, max(0, storage_score + fixture_score + capacity_score + category_score + case_pack_score + confidence_component + 15))

    # AI confidence is intentionally different from planogram score.
    # It is about how trustworthy the recommendation is given data quality and operational uncertainty.
    ai_confidence = min(100, max(0, round(avg_conf - (case_pack_missing * 0.4) - (storage_violations * 2) - (category_violations * 1.5))))

    if planogram_score >= 85 and ai_confidence >= 80:
        council_decision = "YAYINA_UYGUN"
    elif planogram_score >= 70 and ai_confidence >= 65:
        council_decision = "KOSULLU_YAYIN"
    elif planogram_score >= 50:
        council_decision = "DUZELTME_GEREKLI"
    else:
        council_decision = "YAYINLANMAMALI"

    return {
        "status": "success",
        "product_count": product_count,
        "planogram_score": planogram_score,
        "ai_confidence_score": ai_confidence,
        "council_decision": council_decision,
        "score_breakdown": {
            "storage_compliance": storage_score,
            "fixture_fit": fixture_score,
            "capacity_fit": capacity_score,
            "category_isolation": category_score,
            "case_pack_compliance": case_pack_score,
            "product_confidence_avg": avg_conf,
        },
        "risk_summary": {
            "storage_violations": storage_violations,
            "capacity_violations": capacity_violations,
            "category_violations": category_violations,
            "case_pack_missing": case_pack_missing,
            "case_pack_rounding_applied": case_pack_rounding,
        },
        "violations": violations[:200],
    }


def refill_risk(product: Dict[str, Any], shelf: Dict[str, Any]) -> Dict[str, Any]:
    sales = sales_of(product)
    raw_units = raw_capacity_units(product, shelf)
    cp = case_pack_of(product)
    rounded = case_pack_rounded_units(raw_units, cp)["units"] or raw_units
    if sales <= 0 or rounded <= 0:
        return {"level": "UNKNOWN", "days_cover": None, "refill_per_day": None}
    days = round((rounded / sales) * 7, 1) if sales > 0 else None
    refill_per_day = round(sales / max(rounded, 1), 2)
    if days is not None and days < 1:
        level = "HIGH"
    elif days is not None and days < 3:
        level = "MEDIUM"
    else:
        level = "LOW"
    return {"level": level, "days_cover": days, "refill_per_day": refill_per_day}


def compare_shelf_change(
    shelf: Dict[str, Any],
    current_product: Optional[Dict[str, Any]],
    candidate_product: Dict[str, Any],
    aisle: Optional[Dict[str, Any]] = None,
    module: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    aisle = aisle or {}
    module = module or {}
    existing = shelf.get("products", []) or []
    current = current_product or {}
    candidate = candidate_product or {}

    current_conf = product_placement_confidence(current, aisle, module, shelf, existing_products=existing) if current else None
    candidate_conf = product_placement_confidence(candidate, aisle, module, shelf, existing_products=existing)

    current_refill = refill_risk(current, shelf) if current else {"level": "EMPTY", "days_cover": None, "refill_per_day": None}
    candidate_refill = refill_risk(candidate, shelf)

    current_sales = sales_of(current) if current else 0
    candidate_sales = sales_of(candidate)

    current_units = current_conf["case_pack_rounded_units"] if current_conf else 0
    candidate_units = candidate_conf["case_pack_rounded_units"]

    impact = {
        "sales_delta": round(candidate_sales - current_sales, 2),
        "confidence_delta": (candidate_conf["placement_confidence"] - (current_conf["placement_confidence"] if current_conf else 0)),
        "capacity_units_delta": candidate_units - current_units,
        "case_pack_extra_units": candidate_conf["case_pack_extra_units"],
    }

    risk_flags = []
    if candidate_conf["confidence_level"] == "LOW":
        risk_flags.append("candidate_low_confidence")
    if candidate_refill["level"] == "HIGH":
        risk_flags.append("high_refill_risk")
    if candidate_conf["case_pack_qty"] <= 1:
        risk_flags.append("missing_case_pack_qty")
    if candidate_conf["confidence_warnings"]:
        risk_flags.extend(candidate_conf["confidence_warnings"][:3])

    recommendation = "APPLY" if candidate_conf["placement_confidence"] >= 75 and candidate_refill["level"] != "HIGH" else "REVIEW"
    if candidate_conf["placement_confidence"] < 60:
        recommendation = "DO_NOT_APPLY"

    return {
        "status": "success",
        "mode": "FIFA_STYLE_SHELF_IMPACT",
        "current": current_conf,
        "candidate": candidate_conf,
        "current_refill": current_refill,
        "candidate_refill": candidate_refill,
        "impact": impact,
        "risk_flags": risk_flags,
        "recommendation": recommendation,
        "print_visible": False,
    }


def sort_suggestions_by_confidence(products: List[Dict[str, Any]], shelf: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    scored = []
    for p in products or []:
        conf = product_placement_confidence(p, shelf=shelf)
        scored.append({**p, "placement_confidence": conf["placement_confidence"], "confidence_level": conf["confidence_level"]})
    return sorted(scored, key=lambda x: (x.get("placement_confidence", 0), sales_of(x)), reverse=True)
