"""Fail-closed physical truth contracts for production Planogram."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional
import re
import unicodedata

APPROVED_DIMENSION_SOURCES = {"master", "file", "approved_master", "approved_override"}
ESTIMATED_DIMENSION_SOURCES = {"ai_estimated", "estimated", "heuristic", "inferred"}
VALID_SIDES = {"L", "R"}
PRODUCTION_PICKER_AISLE_MIN_M = 1.0
PRODUCTION_PICKER_AISLE_MAX_M = 1.5
HEAVY_BOTTOM_THRESHOLD_KG = 3.0
LARGE_BEVERAGE_PALLET_LITERS = 4.0
LARGE_BEVERAGE_PALLET_WEIGHT_KG = 4.0


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return default if value in (None, "") else float(str(value).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _text(value)).lower()
    return "".join(ch for ch in raw if not unicodedata.combining(ch)).replace("ı", "i").strip()


def _first(row: Dict[str, Any], *fields: str) -> Any:
    for field in fields:
        if row.get(field) not in (None, ""):
            return row[field]
    return ""


def _product_text(product: Dict[str, Any]) -> str:
    fields = ("product_name", "name", "Product Name", "brand", "brand_name", "category_l1", "category_l2", "frontend_category_local", "frontend_subcategory_local", "product_contents_value", "product_contents_unit", "volume", "volume_unit", "pack_type")
    return _norm(" ".join(_text(_first(product, field)) for field in fields))


def authoritative_storage_value(product: Dict[str, Any]) -> str:
    """Storage supplied by catalog/master, not a later allocator inference."""
    return _text(_first(product, "catalog_storage_condition_raw", "catalog_storage_type", "storage_raw", "Storage Type"))


def explicit_storage_value(product: Dict[str, Any]) -> str:
    return authoritative_storage_value(product) or _text(_first(product, "storage_type", "storage"))


def normalize_temperature_zone(value: Any, default: str = "AMBIENT") -> str:
    raw = _norm(value)
    if any(x in raw for x in ("-18", "frozen", "donuk", "dondur", "freezer")):
        return "FROZEN"
    if any(x in raw for x in ("+4", "chilled", "soguk", "dolap", "fridge", "cooler")):
        return "CHILLED"
    if raw:
        return "AMBIENT"
    return default


def product_temperature_zone(product: Dict[str, Any]) -> str:
    return normalize_temperature_zone(explicit_storage_value(product))


def parse_pack_metrics(product: Dict[str, Any]) -> Dict[str, Any]:
    raw = _product_text(product)
    count, liters, source = 1, None, "missing"
    match = re.search(r"(?:^|[^0-9])(\d{1,3})\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l|lt|ltr|litre|liter)(?:[^a-z0-9]|$)", raw)
    if match:
        count = max(1, int(match.group(1)))
        value, unit = _num(match.group(2)), match.group(3)
        liters = value / 1000 if unit == "ml" else value / 100 if unit == "cl" else value
        source = "name_multipack"
    else:
        value = _num(_first(product, "product_contents_value", "volume", "volume_value"))
        unit = _norm(_first(product, "product_contents_unit", "volume_unit"))
        if value > 0 and unit in {"ml", "cl", "l", "lt", "ltr", "litre", "liter"}:
            count = int(max(1, _num(_first(product, "units_in_pack_count", "pack_count"), 1)))
            liters = value / 1000 if unit == "ml" else value / 100 if unit == "cl" else value
            source = "structured_content"
        else:
            single = re.search(r"(?:^|[^0-9])(\d+(?:[.,]\d+)?)\s*(ml|cl|l|lt|ltr|litre|liter)(?:[^a-z0-9]|$)", raw)
            if single:
                value, unit = _num(single.group(1)), single.group(2)
                liters = value / 1000 if unit == "ml" else value / 100 if unit == "cl" else value
                source = "name_single"
    return {"pack_count": count, "unit_liters": None if liters is None else round(liters, 4), "total_pack_liters": None if liters is None else round(count * liters, 4), "source": source}


def is_beverage(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    if any(x in raw for x in ("maden suyu", "meyve suyu", "mineral water", "sparkling water")):
        return True
    return bool(re.search(r"(?:^|[^a-z0-9])(?:beverage|icecek|drink|water|mineral|soda|gazoz|cola|kola|fanta|sprite|ayran|juice|su)(?:[^a-z0-9]|$)", raw))


def is_detergent_or_cleaning(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    return any(x in raw for x in ("deterjan", "cleaning", "cleaner", "bleach", "camasir", "yumusatici", "domestos", "temizleyici", "bulasik"))


def is_explicit_bulky_pallet_product(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    return any(x in raw for x in ("kedi kumu", "cat litter", "tuvalet kagidi", "toilet paper", "paper towel", "kagit havlu", "damacana"))


def product_weight_kg(product: Dict[str, Any]) -> float:
    return max(0.0, _num(_first(product, "weight_kg", "product_weight_kg", "Weight", "product_weight_value")))


def requires_pallet_fixture(product: Dict[str, Any]) -> bool:
    authoritative = _norm(authoritative_storage_value(product))
    if any(x in authoritative for x in ("pallet", "palet", "hdr")):
        return True
    if is_explicit_bulky_pallet_product(product):
        return True
    legacy = _norm(_first(product, "storage_type", "storage"))
    # Legacy PR #6 can infer PALLET from any 5 L name. For cleaning products
    # that inferred value is not authoritative physical truth.
    if any(x in legacy for x in ("pallet", "palet", "hdr")) and not is_detergent_or_cleaning(product):
        return True
    if not is_beverage(product):
        return False
    total_liters = parse_pack_metrics(product)["total_pack_liters"]
    return (total_liters is not None and total_liters >= LARGE_BEVERAGE_PALLET_LITERS) or product_weight_kg(product) >= LARGE_BEVERAGE_PALLET_WEIGHT_KG


def required_fixture_class(product: Dict[str, Any]) -> str:
    if requires_pallet_fixture(product):
        return "PALLET"
    zone = product_temperature_zone(product)
    return zone if zone in {"CHILLED", "FROZEN"} else "REGULAR_SHELF"


def requires_bottom_shelf(product: Dict[str, Any]) -> bool:
    if requires_pallet_fixture(product):
        return False
    weight = product_weight_kg(product)
    return weight >= HEAVY_BOTTOM_THRESHOLD_KG or (is_detergent_or_cleaning(product) and weight >= 2.0)


def is_approved_dimension_product(product: Dict[str, Any]) -> bool:
    return _norm(product.get("dimension_source")) in APPROVED_DIMENSION_SOURCES and all(_num(product.get(f)) > 0 for f in ("width_cm", "height_cm", "depth_cm"))


def physical_scale_eligible(product: Dict[str, Any]) -> bool:
    return is_approved_dimension_product(product)


def product_truth_report(products: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows, total = list(products or []), 0
    rows = list(rows); total = len(rows)
    approved = sum(is_approved_dimension_product(p) for p in rows)
    estimated = sum(_norm(p.get("dimension_source")) in ESTIMATED_DIMENSION_SOURCES for p in rows)
    missing = sum(_norm(p.get("dimension_source")) == "missing" or any(_num(p.get(f)) <= 0 for f in ("width_cm", "height_cm", "depth_cm")) for p in rows)
    images = sum(bool(_text(_first(p, "image_url", "catalog_image_url", "pim_image_url", "Product Image URL"))) for p in rows)
    master = sum(bool(_text(_first(p, "catalog_global_product_id", "pim_product_id"))) or _norm(p.get("dimension_source")) in {"master", "approved_master"} for p in rows)
    storage = sum(bool(explicit_storage_value(p)) for p in rows)
    pct = lambda n: round(n * 100 / total, 2) if total else 0.0
    return {"dataset_rows": total, "approved_dimension_count": approved, "approved_dimension_coverage_pct": pct(approved), "estimated_dimension_count": estimated, "estimated_dimension_pct": pct(estimated), "missing_dimension_count": missing, "missing_dimension_pct": pct(missing), "image_link_count": images, "image_link_coverage_pct": pct(images), "master_link_count": master, "master_link_coverage_pct": pct(master), "storage_truth_count": storage, "storage_truth_coverage_pct": pct(storage), "dimension_source_counts": dict(Counter(_norm(p.get("dimension_source")) or "unknown" for p in rows)), "required_fixture_counts": dict(Counter(required_fixture_class(p) for p in rows)), "physical_scale_eligible_count": approved, "physical_scale_eligible_pct": pct(approved)}


def iter_product_bearing_shelves(layout: Optional[Dict[str, Any]]):
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            for shelf in module.get("shelves", []) or []:
                yield aisle, module, shelf


def _module_fixture_class(module: Dict[str, Any], shelf: Optional[Dict[str, Any]] = None) -> str:
    raw = _norm(" ".join(_text(x) for x in (module.get("fixture_class"), module.get("fixture_type"), module.get("module_type"), module.get("storage_type"), module.get("zone"), (shelf or {}).get("allowed_storage_type"))))
    if any(x in raw for x in ("pallet", "palet", "hdr", "heavy_rack")): return "PALLET"
    if any(x in raw for x in ("chilled", "+4", "fridge", "cooler", "martek_plus4")): return "CHILLED"
    if any(x in raw for x in ("frozen", "-18", "freezer", "algida", "martek_frozen")): return "FROZEN"
    return "REGULAR_SHELF"


def layout_truth_report(layout: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(layout, dict) or not layout.get("aisles"):
        return {"present": False, "aisle_count": 0, "module_count": 0, "shelf_count": 0, "fixture_capacity_coverage_pct": 0.0, "module_side_coverage_pct": 0.0, "fixture_class_counts": {}, "blockers": ["physical_layout_missing"]}
    aisles = layout["aisles"]
    modules = [m for a in aisles for m in (a.get("modules") or [])]
    shelves = [s for _, _, s in iter_product_bearing_shelves(layout)]
    physical = sum(all(_num(s.get(f)) > 0 for f in ("shelf_width_cm", "shelf_height_cm", "shelf_depth_cm", "max_weight_kg")) and bool(_text(s.get("allowed_storage_type") or s.get("storage_type"))) for s in shelves)
    sided = sum(_text(m.get("side")).upper() in VALID_SIDES for m in modules)
    blockers = []
    if not shelves: blockers.append("product_bearing_shelves_missing")
    if shelves and physical != len(shelves): blockers.append("fixture_capacity_incomplete")
    if modules and sided != len(modules): blockers.append("left_right_module_side_incomplete")
    pct = lambda n, d: round(n * 100 / d, 2) if d else 0.0
    fixtures = Counter(_module_fixture_class(m, s) for a in aisles for m in (a.get("modules") or []) for s in (m.get("shelves") or [None]))
    return {"present": True, "aisle_count": len(aisles), "module_count": len(modules), "shelf_count": len(shelves), "physical_shelf_count": physical, "fixture_capacity_coverage_pct": pct(physical, len(shelves)), "sided_module_count": sided, "module_side_coverage_pct": pct(sided, len(modules)), "fixture_class_counts": dict(fixtures), "blockers": blockers}


def _picker_width_m(dna: Dict[str, Any]) -> Optional[float]:
    for f in ("picker_aisle_width_m", "center_aisle_width_m", "walking_aisle_width_m", "aisle_clear_width_m"):
        if _num(dna.get(f)) > 0: return _num(dna[f])
    for f in ("picker_aisle_width_cm", "center_aisle_width_cm", "walking_aisle_width_cm"):
        if _num(dna.get(f)) > 0: return _num(dna[f]) / 100
    return None


def store_dna_truth_report(store_dna: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(store_dna, dict) or not store_dna:
        return {"present": False, "source": None, "measured": False, "picker_aisle_width_m": None, "picker_aisle_width_valid": False, "side_module_coverage_pct": 0.0, "coverage_pct": 0.0, "blockers": ["store_dna_missing"]}
    source = _text(store_dna.get("source")); measured = source in {"user_approved_store_dna", "measured_store_dna", "approved_store_dna"}
    width = _picker_width_m(store_dna); width_ok = width is not None and PRODUCTION_PICKER_AISLE_MIN_M <= width <= PRODUCTION_PICKER_AISLE_MAX_M
    aisles = store_dna.get("aisle_module_config") or store_dna.get("aisles") or []
    aisle_count = len(aisles) if isinstance(aisles, list) else int(_num(store_dna.get("aisle_count")))
    total = sided = 0
    if isinstance(aisles, list):
        for aisle in aisles:
            left, right, flat = aisle.get("left_modules") or [], aisle.get("right_modules") or [], aisle.get("modules") or []
            total += len(left) + len(right) + len(flat); sided += len(left) + len(right) + sum(_text(m.get("side")).upper() in VALID_SIDES for m in flat)
    if total == 0:
        per = int(_num(store_dna.get("left_modules"))) + int(_num(store_dna.get("right_modules"))); total = aisle_count * per; sided = total if per else 0
    side_pct = round(sided * 100 / total, 2) if total else 0.0
    blockers = []
    if not measured: blockers.append("store_dna_not_measured_or_user_approved")
    if aisle_count <= 0 or total <= 0: blockers.append("store_dna_aisle_module_geometry_missing")
    if side_pct < 100: blockers.append("store_dna_left_right_side_incomplete")
    if width is None: blockers.append("picker_center_aisle_width_missing")
    elif not width_ok: blockers.append("picker_center_aisle_width_outside_1_0_to_1_5m")
    evidence = sum((measured, aisle_count > 0, total > 0, side_pct == 100, width_ok))
    return {"present": True, "source": source or None, "measured": measured, "aisle_count": aisle_count, "module_count": total, "side_module_coverage_pct": side_pct, "picker_aisle_width_m": None if width is None else round(width, 3), "picker_aisle_width_valid": width_ok, "picker_aisle_expected_range_m": [1.0, 1.5], "coverage_pct": round(evidence * 20, 2), "blockers": blockers}


def required_fixture_gap_report(products: Iterable[Dict[str, Any]], layout: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    required = Counter(required_fixture_class(p) for p in products or [])
    available = Counter(layout_truth_report(layout).get("fixture_class_counts") or {})
    missing = sorted(k for k, n in required.items() if n and available.get(k, 0) <= 0)
    return {"required_fixture_counts": dict(required), "available_fixture_counts": dict(available), "missing_fixture_classes": missing}


def physical_constraint_reason(product: Dict[str, Any], module: Dict[str, Any], shelf: Dict[str, Any]) -> Optional[str]:
    required, actual = required_fixture_class(product), _module_fixture_class(module, shelf)
    if required != actual: return f"required_fixture_{required.lower()}_not_match"
    if requires_bottom_shelf(product) and _norm(shelf.get("zone_type")) != "bottom": return "heavy_product_requires_bottom_shelf"
    return None


def production_acceptance_report(products: Iterable[Dict[str, Any]], layout: Optional[Dict[str, Any]], store_dna: Optional[Dict[str, Any]], *, require_images: bool = True) -> Dict[str, Any]:
    rows = list(products or []); dataset = product_truth_report(rows); layout_report = layout_truth_report(layout); dna = store_dna_truth_report(store_dna); fixtures = required_fixture_gap_report(rows, layout)
    blockers: List[str] = []
    if not dataset["dataset_rows"]: blockers.append("product_dataset_empty")
    if dataset["approved_dimension_coverage_pct"] < 100: blockers.append("approved_dimension_coverage_below_100_pct")
    if require_images and dataset["image_link_coverage_pct"] < 100: blockers.append("image_link_coverage_below_100_pct")
    blockers += layout_report.get("blockers", []) + dna.get("blockers", [])
    if fixtures["missing_fixture_classes"]: blockers.append("required_fixture_class_missing")
    blockers = list(dict.fromkeys(blockers))
    return {"production_ready": not blockers, "solver_optimizer_allowed": not blockers, "dataset": dataset, "layout": layout_report, "store_dna": dna, "fixture_requirements": fixtures, "blockers": blockers}


def clone_with_physical_truth(product: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(product); pack = parse_pack_metrics(product); temperature = product_temperature_zone(product); fixture = required_fixture_class(product)
    result.update({"temperature_zone": temperature, "required_fixture_class": fixture, "requires_bottom_shelf": requires_bottom_shelf(product), "physical_scale_eligible": physical_scale_eligible(product), "pack_count": pack["pack_count"], "unit_liters": pack["unit_liters"], "total_pack_liters": pack["total_pack_liters"], "pack_metric_source": pack["source"]})
    allocator_storage = "PALLET" if fixture == "PALLET" else temperature
    result["storage_type"] = allocator_storage; result["_storage"] = allocator_storage
    return result
