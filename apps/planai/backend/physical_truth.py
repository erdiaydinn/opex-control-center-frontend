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
        return (
            default
            if value in (None, "")
            else float(str(value).replace(",", ".").replace("%", "").strip())
        )
    except (TypeError, ValueError):
        return default


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _text(value)).lower()
    return (
        "".join(ch for ch in raw if not unicodedata.combining(ch))
        .replace("ı", "i")
        .strip()
    )


def _first(row: Dict[str, Any], *fields: str) -> Any:
    for field in fields:
        if row.get(field) not in (None, ""):
            return row[field]
    return ""


MASS_UNIT_TO_KG = {
    "kg": 1.0,
    "kilogram": 1.0,
    "kilograms": 1.0,
    "g": 0.001,
    "gr": 0.001,
    "gram": 0.001,
    "grams": 0.001,
    "mg": 0.000001,
}


def normalize_mass_kg(product: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize mass without interpreting an unqualified catalog value as kg."""
    if product.get("mass_ambiguous") is True:
        return {
            "value_kg": None,
            "source": product.get("mass_source") or "unqualified_weight",
            "unit": product.get("mass_unit"),
            "valid": False,
            "ambiguous": True,
        }
    for field in ("weight_kg", "product_weight_kg"):
        value = _num(product.get(field), -1.0)
        if value > 0:
            return {
                "value_kg": round(value, 6),
                "source": field,
                "unit": "kg",
                "valid": True,
                "ambiguous": False,
            }
    weight_g = _num(product.get("weight_g"), -1.0)
    if weight_g > 0:
        return {
            "value_kg": round(weight_g / 1000.0, 6),
            "source": "weight_g",
            "unit": "g",
            "valid": True,
            "ambiguous": False,
        }
    raw_value = _first(product, "product_weight_value", "Weight", "agirlik")
    value = _num(raw_value, -1.0)
    if value > 0:
        unit = _norm(
            _first(
                product,
                "product_weight_unit",
                "weight_unit",
                "Weight Unit",
                "agirlik_birimi",
            )
        )
        factor = MASS_UNIT_TO_KG.get(unit)
        if factor is None:
            return {
                "value_kg": None,
                "source": "unqualified_weight",
                "unit": unit or None,
                "valid": False,
                "ambiguous": True,
            }
        return {
            "value_kg": round(value * factor, 6),
            "source": "structured_weight",
            "unit": unit,
            "valid": True,
            "ambiguous": False,
        }
    return {
        "value_kg": None,
        "source": "missing",
        "unit": None,
        "valid": False,
        "ambiguous": False,
    }


def _product_text(product: Dict[str, Any]) -> str:
    fields = (
        "product_name",
        "name",
        "Product Name",
        "brand",
        "brand_name",
        "category_l1",
        "category_l2",
        "frontend_category_local",
        "frontend_subcategory_local",
        "product_contents_value",
        "product_contents_unit",
        "volume",
        "volume_unit",
        "pack_type",
    )
    return _norm(" ".join(_text(_first(product, field)) for field in fields))


def authoritative_storage_value(product: Dict[str, Any]) -> str:
    """Storage supplied by catalog/master, not a later allocator inference."""
    return _text(
        _first(
            product,
            "catalog_storage_condition_raw",
            "catalog_storage_type",
            "storage_raw",
            "Storage Type",
        )
    )


def explicit_storage_value(product: Dict[str, Any]) -> str:
    return authoritative_storage_value(product) or _text(
        _first(product, "storage_type", "storage")
    )


def normalize_temperature_zone(value: Any, default: str = "AMBIENT") -> str:
    raw = _norm(value)
    if any(x in raw for x in ("-18", "frozen", "donuk", "dondur", "freezer")):
        return "FROZEN"
    if any(
        x in raw for x in ("+4", "chilled", "soguk", "dolap", "fridge", "cooler")
    ):
        return "CHILLED"
    if raw:
        return "AMBIENT"
    return default


def product_temperature_zone(product: Dict[str, Any]) -> str:
    return normalize_temperature_zone(explicit_storage_value(product))


def parse_pack_metrics(product: Dict[str, Any]) -> Dict[str, Any]:
    raw = _product_text(product)
    count, liters, source = 1, None, "missing"
    match = re.search(
        r"(?:^|[^0-9])(\d{1,3})\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*"
        r"(ml|cl|l|lt|ltr|litre|liter)(?:[^a-z0-9]|$)",
        raw,
    )
    if match:
        count = max(1, int(match.group(1)))
        value, unit = _num(match.group(2)), match.group(3)
        liters = value / 1000 if unit == "ml" else value / 100 if unit == "cl" else value
        source = "name_multipack"
    else:
        value = _num(
            _first(product, "product_contents_value", "volume", "volume_value")
        )
        unit = _norm(_first(product, "product_contents_unit", "volume_unit"))
        if value > 0 and unit in {"ml", "cl", "l", "lt", "ltr", "litre", "liter"}:
            count = int(
                max(1, _num(_first(product, "units_in_pack_count", "pack_count"), 1))
            )
            liters = (
                value / 1000
                if unit == "ml"
                else value / 100 if unit == "cl" else value
            )
            source = "structured_content"
        else:
            single = re.search(
                r"(?:^|[^0-9])(\d+(?:[.,]\d+)?)\s*"
                r"(ml|cl|l|lt|ltr|litre|liter)(?:[^a-z0-9]|$)",
                raw,
            )
            if single:
                value, unit = _num(single.group(1)), single.group(2)
                liters = (
                    value / 1000
                    if unit == "ml"
                    else value / 100 if unit == "cl" else value
                )
                source = "name_single"
    return {
        "pack_count": count,
        "unit_liters": None if liters is None else round(liters, 4),
        "total_pack_liters": None if liters is None else round(count * liters, 4),
        "source": source,
    }


def is_beverage(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    if any(
        x in raw
        for x in ("maden suyu", "meyve suyu", "mineral water", "sparkling water")
    ):
        return True
    return bool(
        re.search(
            r"(?:^|[^a-z0-9])(?:beverage|icecek|drink|water|mineral|soda|gazoz|"
            r"cola|kola|fanta|sprite|ayran|juice|su)(?:[^a-z0-9]|$)",
            raw,
        )
    )


def is_detergent_or_cleaning(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    return any(
        x in raw
        for x in (
            "deterjan",
            "cleaning",
            "cleaner",
            "bleach",
            "camasir",
            "yumusatici",
            "domestos",
            "temizleyici",
            "bulasik",
        )
    )


def is_explicit_bulky_pallet_product(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    return any(
        x in raw
        for x in (
            "kedi kumu",
            "cat litter",
            "tuvalet kagidi",
            "toilet paper",
            "paper towel",
            "kagit havlu",
            "damacana",
        )
    )


def product_weight_kg(product: Dict[str, Any]) -> float:
    normalized = normalize_mass_kg(product)
    return float(normalized["value_kg"] or 0.0)


def requires_pallet_fixture(product: Dict[str, Any]) -> bool:
    authoritative = _norm(authoritative_storage_value(product))
    if any(x in authoritative for x in ("pallet", "palet", "hdr")):
        return True
    if is_explicit_bulky_pallet_product(product):
        return True
    legacy = _norm(_first(product, "storage_type", "storage"))
    # Legacy PR #6 can infer PALLET from any 5 L name. For cleaning products
    # that inferred value is not authoritative physical truth.
    if any(x in legacy for x in ("pallet", "palet", "hdr")) and not is_detergent_or_cleaning(
        product
    ):
        return True
    if not is_beverage(product):
        return False
    total_liters = parse_pack_metrics(product)["total_pack_liters"]
    return (
        total_liters is not None and total_liters >= LARGE_BEVERAGE_PALLET_LITERS
    ) or product_weight_kg(product) >= LARGE_BEVERAGE_PALLET_WEIGHT_KG


def required_fixture_class(product: Dict[str, Any]) -> str:
    if requires_pallet_fixture(product):
        return "PALLET"
    zone = product_temperature_zone(product)
    return zone if zone in {"CHILLED", "FROZEN"} else "REGULAR_SHELF"


def requires_bottom_shelf(product: Dict[str, Any]) -> bool:
    if requires_pallet_fixture(product):
        return False
    weight = product_weight_kg(product)
    return weight >= HEAVY_BOTTOM_THRESHOLD_KG or (
        is_detergent_or_cleaning(product) and weight >= 2.0
    )


def is_approved_dimension_product(product: Dict[str, Any]) -> bool:
    return _norm(product.get("dimension_source")) in APPROVED_DIMENSION_SOURCES and all(
        _num(product.get(field)) > 0 for field in ("width_cm", "height_cm", "depth_cm")
    )


def physical_scale_eligible(product: Dict[str, Any]) -> bool:
    return is_approved_dimension_product(product)


def product_truth_report(products: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(products or [])
    total = len(rows)
    approved = sum(is_approved_dimension_product(product) for product in rows)
    estimated = sum(
        _norm(product.get("dimension_source")) in ESTIMATED_DIMENSION_SOURCES
        for product in rows
    )
    missing = sum(
        _norm(product.get("dimension_source")) == "missing"
        or any(
            _num(product.get(field)) <= 0
            for field in ("width_cm", "height_cm", "depth_cm")
        )
        for product in rows
    )
    images = sum(
        bool(
            _text(
                _first(
                    product,
                    "image_url",
                    "catalog_image_url",
                    "pim_image_url",
                    "Product Image URL",
                )
            )
        )
        for product in rows
    )
    master = sum(
        bool(_text(_first(product, "catalog_global_product_id", "pim_product_id")))
        or _norm(product.get("dimension_source")) in {"master", "approved_master"}
        for product in rows
    )
    storage = sum(bool(explicit_storage_value(product)) for product in rows)
    masses = [normalize_mass_kg(product) for product in rows]
    ambiguous_mass = sum(item["ambiguous"] for item in masses)

    def pct(count: int) -> float:
        return round(count * 100 / total, 2) if total else 0.0

    return {
        "dataset_rows": total,
        "approved_dimension_count": approved,
        "approved_dimension_coverage_pct": pct(approved),
        "estimated_dimension_count": estimated,
        "estimated_dimension_pct": pct(estimated),
        "missing_dimension_count": missing,
        "missing_dimension_pct": pct(missing),
        "image_link_count": images,
        "image_link_coverage_pct": pct(images),
        "master_link_count": master,
        "master_link_coverage_pct": pct(master),
        "storage_truth_count": storage,
        "storage_truth_coverage_pct": pct(storage),
        "ambiguous_mass_count": ambiguous_mass,
        "mass_source_counts": dict(Counter(item["source"] for item in masses)),
        "dimension_source_counts": dict(
            Counter(
                _norm(product.get("dimension_source")) or "unknown"
                for product in rows
            )
        ),
        "required_fixture_counts": dict(
            Counter(required_fixture_class(product) for product in rows)
        ),
        "physical_scale_eligible_count": approved,
        "physical_scale_eligible_pct": pct(approved),
    }


def iter_product_bearing_shelves(layout: Optional[Dict[str, Any]]):
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            for shelf in module.get("shelves", []) or []:
                yield aisle, module, shelf


def _module_fixture_class(
    module: Dict[str, Any], shelf: Optional[Dict[str, Any]] = None
) -> str:
    raw = _norm(
        " ".join(
            _text(value)
            for value in (
                module.get("fixture_class"),
                module.get("fixture_type"),
                module.get("module_type"),
                module.get("storage_type"),
                module.get("zone"),
                (shelf or {}).get("allowed_storage_type"),
            )
        )
    )
    if any(x in raw for x in ("pallet", "palet", "hdr", "heavy_rack")):
        return "PALLET"
    if any(x in raw for x in ("chilled", "+4", "fridge", "cooler", "martek_plus4")):
        return "CHILLED"
    if any(x in raw for x in ("frozen", "-18", "freezer", "algida", "martek_frozen")):
        return "FROZEN"
    return "REGULAR_SHELF"


def layout_truth_report(layout: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(layout, dict) or not layout.get("aisles"):
        return {
            "present": False,
            "aisle_count": 0,
            "module_count": 0,
            "shelf_count": 0,
            "fixture_capacity_coverage_pct": 0.0,
            "module_side_coverage_pct": 0.0,
            "fixture_class_counts": {},
            "blockers": ["physical_layout_missing"],
        }
    aisles = layout["aisles"]
    modules = [module for aisle in aisles for module in (aisle.get("modules") or [])]
    shelves = [shelf for _, _, shelf in iter_product_bearing_shelves(layout)]
    physical = sum(
        all(
            _num(shelf.get(field)) > 0
            for field in (
                "shelf_width_cm",
                "shelf_height_cm",
                "shelf_depth_cm",
                "max_weight_kg",
            )
        )
        and bool(_text(shelf.get("allowed_storage_type") or shelf.get("storage_type")))
        for shelf in shelves
    )
    sided = sum(_text(module.get("side")).upper() in VALID_SIDES for module in modules)
    blockers = []
    if not shelves:
        blockers.append("product_bearing_shelves_missing")
    if shelves and physical != len(shelves):
        blockers.append("fixture_capacity_incomplete")
    if modules and sided != len(modules):
        blockers.append("left_right_module_side_incomplete")

    def pct(count: int, denominator: int) -> float:
        return round(count * 100 / denominator, 2) if denominator else 0.0

    fixtures = Counter(
        _module_fixture_class(module, shelf)
        for aisle in aisles
        for module in (aisle.get("modules") or [])
        for shelf in (module.get("shelves") or [None])
    )
    return {
        "present": True,
        "aisle_count": len(aisles),
        "module_count": len(modules),
        "shelf_count": len(shelves),
        "physical_shelf_count": physical,
        "fixture_capacity_coverage_pct": pct(physical, len(shelves)),
        "sided_module_count": sided,
        "module_side_coverage_pct": pct(sided, len(modules)),
        "fixture_class_counts": dict(fixtures),
        "blockers": blockers,
    }


def _picker_width_m(dna: Dict[str, Any]) -> Optional[float]:
    for field in (
        "picker_aisle_width_m",
        "center_aisle_width_m",
        "walking_aisle_width_m",
        "aisle_clear_width_m",
    ):
        if _num(dna.get(field)) > 0:
            return _num(dna[field])
    for field in (
        "picker_aisle_width_cm",
        "center_aisle_width_cm",
        "walking_aisle_width_cm",
    ):
        if _num(dna.get(field)) > 0:
            return _num(dna[field]) / 100
    return None


def store_dna_truth_report(store_dna: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(store_dna, dict) or not store_dna:
        return {
            "present": False,
            "source": None,
            "measured": False,
            "picker_aisle_width_m": None,
            "picker_aisle_width_valid": False,
            "side_module_coverage_pct": 0.0,
            "coverage_pct": 0.0,
            "blockers": ["store_dna_missing"],
        }
    source = _text(store_dna.get("source"))
    measured = source in {
        "user_approved_store_dna",
        "measured_store_dna",
        "approved_store_dna",
    }
    width = _picker_width_m(store_dna)
    width_ok = (
        width is not None
        and PRODUCTION_PICKER_AISLE_MIN_M <= width <= PRODUCTION_PICKER_AISLE_MAX_M
    )
    aisles = store_dna.get("aisle_module_config") or store_dna.get("aisles") or []
    aisle_count = (
        len(aisles)
        if isinstance(aisles, list)
        else int(_num(store_dna.get("aisle_count")))
    )
    total = sided = 0
    if isinstance(aisles, list):
        for aisle in aisles:
            left = aisle.get("left_modules") or []
            right = aisle.get("right_modules") or []
            flat = aisle.get("modules") or []
            total += len(left) + len(right) + len(flat)
            sided += (
                len(left)
                + len(right)
                + sum(
                    _text(module.get("side")).upper() in VALID_SIDES
                    for module in flat
                )
            )
    if total == 0:
        per = int(_num(store_dna.get("left_modules"))) + int(
            _num(store_dna.get("right_modules"))
        )
        total = aisle_count * per
        sided = total if per else 0
    side_pct = round(sided * 100 / total, 2) if total else 0.0
    blockers = []
    if not measured:
        blockers.append("store_dna_not_measured_or_user_approved")
    if aisle_count <= 0 or total <= 0:
        blockers.append("store_dna_aisle_module_geometry_missing")
    if side_pct < 100:
        blockers.append("store_dna_left_right_side_incomplete")
    if width is None:
        blockers.append("picker_center_aisle_width_missing")
    elif not width_ok:
        blockers.append("picker_center_aisle_width_outside_1_0_to_1_5m")
    evidence = sum((measured, aisle_count > 0, total > 0, side_pct == 100, width_ok))
    return {
        "present": True,
        "source": source or None,
        "measured": measured,
        "aisle_count": aisle_count,
        "module_count": total,
        "side_module_coverage_pct": side_pct,
        "picker_aisle_width_m": None if width is None else round(width, 3),
        "picker_aisle_width_valid": width_ok,
        "picker_aisle_expected_range_m": [1.0, 1.5],
        "coverage_pct": round(evidence * 20, 2),
        "blockers": blockers,
    }


def required_fixture_gap_report(
    products: Iterable[Dict[str, Any]], layout: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    required = Counter(required_fixture_class(product) for product in products or [])
    available = Counter(layout_truth_report(layout).get("fixture_class_counts") or {})
    missing = sorted(
        fixture_class
        for fixture_class, count in required.items()
        if count and available.get(fixture_class, 0) <= 0
    )
    return {
        "required_fixture_counts": dict(required),
        "available_fixture_counts": dict(available),
        "missing_fixture_classes": missing,
    }


def physical_constraint_reason(
    product: Dict[str, Any], module: Dict[str, Any], shelf: Dict[str, Any]
) -> Optional[str]:
    required = required_fixture_class(product)
    actual = _module_fixture_class(module, shelf)
    if required != actual:
        return f"required_fixture_{required.lower()}_not_match"
    if requires_bottom_shelf(product) and _norm(shelf.get("zone_type")) != "bottom":
        return "heavy_product_requires_bottom_shelf"
    return None


def production_acceptance_report(
    products: Iterable[Dict[str, Any]],
    layout: Optional[Dict[str, Any]],
    store_dna: Optional[Dict[str, Any]],
    *,
    require_images: bool = True,
) -> Dict[str, Any]:
    rows = list(products or [])
    dataset = product_truth_report(rows)
    layout_report = layout_truth_report(layout)
    dna = store_dna_truth_report(store_dna)
    fixtures = required_fixture_gap_report(rows, layout)
    blockers: List[str] = []
    if not dataset["dataset_rows"]:
        blockers.append("product_dataset_empty")
    if dataset["approved_dimension_coverage_pct"] < 100:
        blockers.append("approved_dimension_coverage_below_100_pct")
    if dataset["ambiguous_mass_count"]:
        blockers.append("ambiguous_mass_unit_present")
    if require_images and dataset["image_link_coverage_pct"] < 100:
        blockers.append("image_link_coverage_below_100_pct")
    blockers += layout_report.get("blockers", []) + dna.get("blockers", [])
    if fixtures["missing_fixture_classes"]:
        blockers.append("required_fixture_class_missing")
    blockers = list(dict.fromkeys(blockers))
    return {
        "production_ready": not blockers,
        "solver_optimizer_allowed": not blockers,
        "dataset": dataset,
        "layout": layout_report,
        "store_dna": dna,
        "fixture_requirements": fixtures,
        "blockers": blockers,
    }


def clone_with_physical_truth(product: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(product)
    pack = parse_pack_metrics(product)
    mass = normalize_mass_kg(product)
    temperature = product_temperature_zone(product)
    fixture = required_fixture_class(product)
    if mass["valid"]:
        result["weight_kg"] = mass["value_kg"]
    result.update(
        {
            "temperature_zone": temperature,
            "required_fixture_class": fixture,
            "requires_bottom_shelf": requires_bottom_shelf({**product, **result}),
            "physical_scale_eligible": physical_scale_eligible(product),
            "pack_count": pack["pack_count"],
            "unit_liters": pack["unit_liters"],
            "total_pack_liters": pack["total_pack_liters"],
            "pack_metric_source": pack["source"],
            "mass_source": mass["source"],
            "mass_unit": mass["unit"],
            "mass_valid": mass["valid"],
            "mass_ambiguous": mass["ambiguous"],
        }
    )
    allocator_storage = "PALLET" if fixture == "PALLET" else temperature
    result["storage_type"] = allocator_storage
    result["_storage"] = allocator_storage
    return result
