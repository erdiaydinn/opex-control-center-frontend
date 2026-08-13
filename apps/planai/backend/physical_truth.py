"""Fail-closed physical truth contracts for Planogram production acceptance.

This module deliberately does not replace the deterministic allocator.  It
qualifies the evidence the allocator is allowed to trust: approved SKU
measurements, image linkage, measured fixture capacity and Store DNA geometry.
Production optimization must not run on guessed dimensions or synthetic store
capacity.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple
import re
import unicodedata


APPROVED_DIMENSION_SOURCES = {"master", "file", "approved_master", "approved_override"}
ESTIMATED_DIMENSION_SOURCES = {"ai_estimated", "estimated", "heuristic", "inferred"}
VALID_SIDES = {"L", "R"}
VALID_STORAGE = {"AMBIENT", "CHILLED", "FROZEN", "PALLET"}
PRODUCTION_PICKER_AISLE_MIN_M = 1.0
PRODUCTION_PICKER_AISLE_MAX_M = 1.5
HEAVY_BOTTOM_THRESHOLD_KG = 3.0
LARGE_BEVERAGE_PALLET_LITERS = 4.0
LARGE_BEVERAGE_PALLET_WEIGHT_KG = 4.0


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _text(value)).lower()
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return raw.replace("ı", "i").strip()


def _first(product: Dict[str, Any], *fields: str) -> Any:
    for field in fields:
        value = product.get(field)
        if value not in (None, ""):
            return value
    return ""


def _product_text(product: Dict[str, Any]) -> str:
    return _norm(
        " ".join(
            _text(_first(product, field))
            for field in (
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
        )
    )


def normalize_temperature_zone(value: Any, default: str = "AMBIENT") -> str:
    raw = _norm(value)
    if not raw:
        return default
    if any(token in raw for token in ("-18", "frozen", "donuk", "dondur", "freezer")):
        return "FROZEN"
    if any(token in raw for token in ("+4", "chilled", "soguk", "dolap", "fridge", "cooler")):
        return "CHILLED"
    if any(token in raw for token in ("pallet", "palet", "hdr")):
        return "AMBIENT"
    if any(token in raw for token in ("ambient", "raf", "shelf", "dry", "kuru")):
        return "AMBIENT"
    return default


def explicit_storage_value(product: Dict[str, Any]) -> str:
    return _text(
        _first(
            product,
            "catalog_storage_condition_raw",
            "catalog_storage_type",
            "storage_raw",
            "Storage Type",
            "storage_type",
            "storage",
        )
    )


def product_temperature_zone(product: Dict[str, Any]) -> str:
    return normalize_temperature_zone(explicit_storage_value(product), "AMBIENT")


def parse_pack_metrics(product: Dict[str, Any]) -> Dict[str, Any]:
    """Return deterministic sell-pack volume/count evidence when available.

    The parser is intentionally conservative.  It recognizes explicit pack
    notation such as 6x1.5L, 12 x 500 ml and single 5 L sizes.  It never turns
    an arbitrary numeric token into a beverage volume.
    """

    raw = _product_text(product)
    count = 1
    unit_liters: Optional[float] = None
    source = "missing"

    match = re.search(
        r"(?:^|[^0-9])(?P<count>\d{1,3})\s*[x×]\s*"
        r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>ml|cl|l|lt|ltr|litre|liter)"
        r"(?:[^a-z0-9]|$)",
        raw,
    )
    if match:
        count = max(1, int(match.group("count")))
        value = _num(match.group("value"))
        unit = match.group("unit")
        if unit == "ml":
            unit_liters = value / 1000.0
        elif unit == "cl":
            unit_liters = value / 100.0
        else:
            unit_liters = value
        source = "name_multipack"
    else:
        pack_count = int(max(1, _num(_first(product, "units_in_pack_count", "pack_count"), 1)))
        contents_value = _num(
            _first(
                product,
                "product_contents_value",
                "volume",
                "volume_value",
            ),
            0,
        )
        contents_unit = _norm(
            _first(
                product,
                "product_contents_unit",
                "volume_unit",
            )
        )
        if contents_value > 0 and contents_unit in {"ml", "cl", "l", "lt", "ltr", "litre", "liter"}:
            count = pack_count
            if contents_unit == "ml":
                unit_liters = contents_value / 1000.0
            elif contents_unit == "cl":
                unit_liters = contents_value / 100.0
            else:
                unit_liters = contents_value
            source = "structured_content"
        else:
            single = re.search(
                r"(?:^|[^0-9])(?P<value>\d+(?:[.,]\d+)?)\s*"
                r"(?P<unit>ml|cl|l|lt|ltr|litre|liter)(?:[^a-z0-9]|$)",
                raw,
            )
            if single:
                value = _num(single.group("value"))
                unit = single.group("unit")
                if unit == "ml":
                    unit_liters = value / 1000.0
                elif unit == "cl":
                    unit_liters = value / 100.0
                else:
                    unit_liters = value
                source = "name_single"

    total_liters = None if unit_liters is None else round(count * unit_liters, 4)
    return {
        "pack_count": count,
        "unit_liters": None if unit_liters is None else round(unit_liters, 4),
        "total_pack_liters": total_liters,
        "source": source,
    }


def is_beverage(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    return any(
        token in raw
        for token in (
            " beverage ",
            " icecek ",
            " drink ",
            " water ",
            " maden suyu ",
            " mineral ",
            " soda ",
            " gazoz ",
            " cola ",
            " kola ",
            " fanta ",
            " sprite ",
            " ayran ",
            " juice ",
            " meyve suyu ",
        )
    ) or bool(re.search(r"(?:^|\s)su(?:\s|$)", raw))


def is_detergent_or_cleaning(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    return any(
        token in raw
        for token in (
            "deterjan",
            "cleaning",
            "cleaner",
            "bleach",
            "camasir",
            "yumusatici",
            "domestos",
            "temizleyici",
            "bulastik",
            "bulaşık",
        )
    )


def is_explicit_bulky_pallet_product(product: Dict[str, Any]) -> bool:
    raw = _product_text(product)
    return any(
        token in raw
        for token in (
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
    return max(
        0.0,
        _num(
            _first(
                product,
                "weight_kg",
                "product_weight_kg",
                "Weight",
                "product_weight_value",
            ),
            0,
        ),
    )


def requires_pallet_fixture(product: Dict[str, Any]) -> bool:
    explicit = _norm(explicit_storage_value(product))
    if any(token in explicit for token in ("pallet", "palet", "hdr")):
        return True

    if is_explicit_bulky_pallet_product(product):
        return True

    if not is_beverage(product):
        # A 5 L detergent is heavy and belongs low, but volume alone does not
        # make it pallet stock.  This prevents the historical detergent/pallet
        # false positive.
        return False

    metrics = parse_pack_metrics(product)
    total_liters = metrics.get("total_pack_liters")
    if total_liters is not None and total_liters >= LARGE_BEVERAGE_PALLET_LITERS:
        return True

    return product_weight_kg(product) >= LARGE_BEVERAGE_PALLET_WEIGHT_KG


def required_fixture_class(product: Dict[str, Any]) -> str:
    if requires_pallet_fixture(product):
        return "PALLET"
    temperature = product_temperature_zone(product)
    if temperature == "CHILLED":
        return "CHILLED"
    if temperature == "FROZEN":
        return "FROZEN"
    return "REGULAR_SHELF"


def requires_bottom_shelf(product: Dict[str, Any]) -> bool:
    if requires_pallet_fixture(product):
        return False
    return product_weight_kg(product) >= HEAVY_BOTTOM_THRESHOLD_KG or (
        is_detergent_or_cleaning(product) and product_weight_kg(product) >= 2.0
    )


def is_approved_dimension_product(product: Dict[str, Any]) -> bool:
    source = _norm(product.get("dimension_source"))
    if source not in APPROVED_DIMENSION_SOURCES:
        return False
    return all(
        _num(product.get(field), 0) > 0
        for field in ("width_cm", "height_cm", "depth_cm")
    )


def physical_scale_eligible(product: Dict[str, Any]) -> bool:
    return is_approved_dimension_product(product)


def product_truth_report(products: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(products or [])
    total = len(rows)
    approved = sum(1 for product in rows if is_approved_dimension_product(product))
    estimated = sum(
        1
        for product in rows
        if _norm(product.get("dimension_source")) in ESTIMATED_DIMENSION_SOURCES
    )
    missing = sum(
        1
        for product in rows
        if _norm(product.get("dimension_source")) == "missing"
        or any(_num(product.get(field), 0) <= 0 for field in ("width_cm", "height_cm", "depth_cm"))
    )
    images = sum(
        1
        for product in rows
        if _text(
            _first(
                product,
                "image_url",
                "catalog_image_url",
                "pim_image_url",
                "Product Image URL",
            )
        )
    )
    master_linked = sum(
        1
        for product in rows
        if _text(_first(product, "catalog_global_product_id", "pim_product_id"))
        or _norm(product.get("dimension_source")) in {"master", "approved_master"}
    )
    storage_truth = sum(1 for product in rows if explicit_storage_value(product))

    source_counts = Counter(_norm(product.get("dimension_source")) or "unknown" for product in rows)
    fixture_counts = Counter(required_fixture_class(product) for product in rows)

    def pct(value: int) -> float:
        return round((value / total) * 100, 2) if total else 0.0

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
        "master_link_count": master_linked,
        "master_link_coverage_pct": pct(master_linked),
        "storage_truth_count": storage_truth,
        "storage_truth_coverage_pct": pct(storage_truth),
        "dimension_source_counts": dict(sorted(source_counts.items())),
        "required_fixture_counts": dict(sorted(fixture_counts.items())),
        "physical_scale_eligible_count": approved,
        "physical_scale_eligible_pct": pct(approved),
    }


def iter_product_bearing_shelves(layout: Optional[Dict[str, Any]]):
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            for shelf in module.get("shelves", []) or []:
                yield aisle, module, shelf


def _module_fixture_class(module: Dict[str, Any], shelf: Optional[Dict[str, Any]] = None) -> str:
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
    if any(token in raw for token in ("pallet", "palet", "hdr", "heavy_rack")):
        return "PALLET"
    if any(token in raw for token in ("chilled", "+4", "fridge", "cooler", "martek_plus4")):
        return "CHILLED"
    if any(token in raw for token in ("frozen", "-18", "freezer", "algida", "martek_frozen")):
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

    aisles = layout.get("aisles") or []
    modules = [module for aisle in aisles for module in (aisle.get("modules") or [])]
    shelves = [shelf for _, _, shelf in iter_product_bearing_shelves(layout)]

    physical_shelves = 0
    for shelf in shelves:
        if all(
            _num(shelf.get(field), 0) > 0
            for field in (
                "shelf_width_cm",
                "shelf_height_cm",
                "shelf_depth_cm",
                "max_weight_kg",
            )
        ) and _text(shelf.get("allowed_storage_type") or shelf.get("storage_type")):
            physical_shelves += 1

    sided_modules = sum(1 for module in modules if _text(module.get("side")).upper() in VALID_SIDES)
    fixture_counts = Counter(
        _module_fixture_class(module, shelf)
        for aisle in aisles
        for module in (aisle.get("modules") or [])
        for shelf in (module.get("shelves") or [None])
    )

    def pct(value: int, denominator: int) -> float:
        return round((value / denominator) * 100, 2) if denominator else 0.0

    blockers: List[str] = []
    if not shelves:
        blockers.append("product_bearing_shelves_missing")
    if shelves and physical_shelves != len(shelves):
        blockers.append("fixture_capacity_incomplete")
    if modules and sided_modules != len(modules):
        blockers.append("left_right_module_side_incomplete")

    return {
        "present": True,
        "aisle_count": len(aisles),
        "module_count": len(modules),
        "shelf_count": len(shelves),
        "physical_shelf_count": physical_shelves,
        "fixture_capacity_coverage_pct": pct(physical_shelves, len(shelves)),
        "sided_module_count": sided_modules,
        "module_side_coverage_pct": pct(sided_modules, len(modules)),
        "fixture_class_counts": dict(sorted(fixture_counts.items())),
        "blockers": blockers,
    }


def _picker_width_m(store_dna: Dict[str, Any]) -> Optional[float]:
    for field in (
        "picker_aisle_width_m",
        "center_aisle_width_m",
        "walking_aisle_width_m",
        "aisle_clear_width_m",
    ):
        value = _num(store_dna.get(field), 0)
        if value > 0:
            return value
    for field in ("picker_aisle_width_cm", "center_aisle_width_cm", "walking_aisle_width_cm"):
        value = _num(store_dna.get(field), 0)
        if value > 0:
            return value / 100.0
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
    measured = source in {"user_approved_store_dna", "measured_store_dna", "approved_store_dna"}
    picker_width = _picker_width_m(store_dna)
    picker_valid = bool(
        picker_width is not None
        and PRODUCTION_PICKER_AISLE_MIN_M <= picker_width <= PRODUCTION_PICKER_AISLE_MAX_M
    )

    aisles = store_dna.get("aisle_module_config") or store_dna.get("aisles") or []
    aisle_count = len(aisles) if isinstance(aisles, list) else int(_num(store_dna.get("aisle_count"), 0))
    total_modules = 0
    side_modules = 0
    if isinstance(aisles, list):
        for aisle in aisles:
            for module in aisle.get("left_modules", []) or []:
                total_modules += 1
                side_modules += int(_text(module.get("side") or "L").upper() == "L")
            for module in aisle.get("right_modules", []) or []:
                total_modules += 1
                side_modules += int(_text(module.get("side") or "R").upper() == "R")
            for module in aisle.get("modules", []) or []:
                total_modules += 1
                side_modules += int(_text(module.get("side")).upper() in VALID_SIDES)
    if total_modules == 0:
        left = int(_num(store_dna.get("left_modules"), 0))
        right = int(_num(store_dna.get("right_modules"), 0))
        per_aisle = left + right
        total_modules = max(0, aisle_count * per_aisle)
        side_modules = total_modules if per_aisle > 0 else 0

    side_pct = round((side_modules / total_modules) * 100, 2) if total_modules else 0.0
    blockers: List[str] = []
    if not measured:
        blockers.append("store_dna_not_measured_or_user_approved")
    if aisle_count <= 0 or total_modules <= 0:
        blockers.append("store_dna_aisle_module_geometry_missing")
    if side_pct < 100:
        blockers.append("store_dna_left_right_side_incomplete")
    if picker_width is None:
        blockers.append("picker_center_aisle_width_missing")
    elif not picker_valid:
        blockers.append("picker_center_aisle_width_outside_1_0_to_1_5m")

    evidence_count = sum(
        [
            bool(measured),
            aisle_count > 0,
            total_modules > 0,
            side_pct == 100,
            picker_valid,
        ]
    )

    return {
        "present": True,
        "source": source or None,
        "measured": measured,
        "aisle_count": aisle_count,
        "module_count": total_modules,
        "side_module_coverage_pct": side_pct,
        "picker_aisle_width_m": None if picker_width is None else round(picker_width, 3),
        "picker_aisle_width_valid": picker_valid,
        "picker_aisle_expected_range_m": [
            PRODUCTION_PICKER_AISLE_MIN_M,
            PRODUCTION_PICKER_AISLE_MAX_M,
        ],
        "coverage_pct": round((evidence_count / 5) * 100, 2),
        "blockers": blockers,
    }


def required_fixture_gap_report(
    products: Iterable[Dict[str, Any]],
    layout: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    product_requirements = Counter(required_fixture_class(product) for product in products or [])
    available = Counter(layout_truth_report(layout).get("fixture_class_counts") or {})
    missing: List[str] = []
    for requirement, count in product_requirements.items():
        if count <= 0:
            continue
        if available.get(requirement, 0) <= 0:
            missing.append(requirement)
    return {
        "required_fixture_counts": dict(sorted(product_requirements.items())),
        "available_fixture_counts": dict(sorted(available.items())),
        "missing_fixture_classes": sorted(missing),
    }


def physical_constraint_reason(
    product: Dict[str, Any],
    module: Dict[str, Any],
    shelf: Dict[str, Any],
) -> Optional[str]:
    fixture = _module_fixture_class(module, shelf)
    required = required_fixture_class(product)
    if required != fixture:
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
    product_report = product_truth_report(rows)
    layout_report = layout_truth_report(layout)
    dna_report = store_dna_truth_report(store_dna)
    fixture_report = required_fixture_gap_report(rows, layout)

    blockers: List[str] = []
    if product_report["dataset_rows"] == 0:
        blockers.append("product_dataset_empty")
    if product_report["approved_dimension_coverage_pct"] < 100:
        blockers.append("approved_dimension_coverage_below_100_pct")
    if require_images and product_report["image_link_coverage_pct"] < 100:
        blockers.append("image_link_coverage_below_100_pct")
    blockers.extend(layout_report.get("blockers") or [])
    blockers.extend(dna_report.get("blockers") or [])
    if fixture_report["missing_fixture_classes"]:
        blockers.append("required_fixture_class_missing")

    blockers = list(dict.fromkeys(blockers))
    return {
        "production_ready": not blockers,
        "solver_optimizer_allowed": not blockers,
        "dataset": product_report,
        "layout": layout_report,
        "store_dna": dna_report,
        "fixture_requirements": fixture_report,
        "blockers": blockers,
    }


def clone_with_physical_truth(product: Dict[str, Any]) -> Dict[str, Any]:
    """Attach physical-truth metadata without mutating the source row."""
    result = deepcopy(product)
    pack = parse_pack_metrics(product)
    result["temperature_zone"] = product_temperature_zone(product)
    result["required_fixture_class"] = required_fixture_class(product)
    result["requires_bottom_shelf"] = requires_bottom_shelf(product)
    result["physical_scale_eligible"] = physical_scale_eligible(product)
    result["pack_count"] = pack.get("pack_count")
    result["unit_liters"] = pack.get("unit_liters")
    result["total_pack_liters"] = pack.get("total_pack_liters")
    result["pack_metric_source"] = pack.get("source")
    return result
