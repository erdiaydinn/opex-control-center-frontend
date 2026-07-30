from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple
import os
import re
import math
import pandas as pd

try:
    from overrides import apply_overrides_to_product
except Exception:
    def apply_overrides_to_product(p):
        return p


# =====================================================
# PLANAI / PLONAGRAM PREMIUM ENGINE
# Sales + Category + Storage + Brand Cluster + Depth
# Master Data + Image + Rules + Diagnostics + Fast Index
# =====================================================

MASTER_CSV = "data/master_products.csv"
MASTER_XLSX = "data/master_products.xlsx"

MASTER_CACHE = {
    "loaded": False,
    "rows": [],
    "by_sku": {},
    "by_barcode": {},
    "by_catalog": {},
    "by_pim": {},
    "by_key": {},
}

DEFAULT_SCORING_CONFIG = {
    "sales": 1.35,
    "picking": 1.20,
    "ergonomics": 1.00,
    "refill": 0.85,
    "risk": 1.15,
    "fixture": 1.40,
    "brand_cluster": 1.25,
    "balance": 0.80,
    "coverage": 1.10,
}

DEFAULT_BRAND_SIDE_RULES = {
    "ulker": "L",
    "ülker": "L",
    "eti": "R",
    "nescafe": "L",
    "nestle": "L",
    "coca cola": "L",
    "fanta": "L",
    "sprite": "L",
    "ruffles": "R",
    "lays": "R",
    "doritos": "R",
    "pinar": "L",
    "pınar": "L",
    "sutas": "R",
    "sütaş": "R",
    "algida": "L",
    "la lorraine": "R",
    "domestos": "L",
    "dove": "R",
}


# =====================================================
# BASIC HELPERS
# =====================================================

def num(v: Any, d: float = 0) -> float:
    try:
        if v is None or v == "":
            return d
        if isinstance(v, float) and math.isnan(v):
            return d
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except Exception:
        return d


def inum(v: Any, d: int = 0) -> int:
    try:
        return int(float(str(v).replace(",", ".").strip()))
    except Exception:
        return d


def clean_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v).strip()


def key(v: Any) -> str:
    return clean_text(v).upper()


def norm(v: Any) -> str:
    return (
        clean_text(v)
        .lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
        .strip()
    )


def get(p: Dict[str, Any], names: List[str], default: Any = "") -> Any:
    for n in names:
        if n in p and p[n] not in [None, ""]:
            return p[n]

    lower = {str(k).lower(): k for k in p.keys()}
    for n in names:
        real = lower.get(str(n).lower())
        if real is not None and p[real] not in [None, ""]:
            return p[real]

    return default


def first_non_empty(*values: Any) -> str:
    for v in values:
        s = clean_text(v)
        if s:
            return s
    return ""


def first_barcode(v: Any) -> str:
    raw = clean_text(v)
    if not raw:
        return ""
    parts = re.split(r"[|;, ]+", raw)
    return clean_text(parts[0]) if parts else ""


def safe_pct(numerator: float, denominator: float) -> float:
    return round((numerator / max(denominator, 1)) * 100, 2)


# =====================================================
# MASTER DATA
# =====================================================

def product_dedup_key(p: Dict[str, Any]) -> str:
    existing = clean_text(get(p, ["planogram_product_key"], ""))
    if existing:
        return existing

    name = norm(get(p, ["product_name", "Product Name", "product_name_local", "pim_product_name_local"], ""))
    b = norm(get(p, ["brand", "Brand", "brand_name"], ""))
    weight_val = norm(get(p, ["product_contents_value", "product_weight_value", "weight_kg"], ""))
    weight_unit = norm(get(p, ["product_contents_unit", "product_weight_unit"], ""))
    cat = norm(get(p, ["frontend_category_local", "Category L1", "category_l1", "category"], ""))
    sub = norm(get(p, ["frontend_subcategory_local", "Category L2", "category_l2", "subcategory"], ""))

    return f"{name}|{b}|{weight_val}|{weight_unit}|{cat}|{sub}"


def read_master_rows() -> List[Dict[str, Any]]:
    if os.path.exists(MASTER_XLSX):
        df = pd.read_excel(MASTER_XLSX)
    elif os.path.exists(MASTER_CSV):
        try:
            df = pd.read_csv(MASTER_CSV)
        except UnicodeDecodeError:
            df = pd.read_csv(MASTER_CSV, encoding="utf-8-sig")
    else:
        return []

    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def load_master(force: bool = False) -> Dict[str, Any]:
    if MASTER_CACHE["loaded"] and not force:
        return MASTER_CACHE

    rows = read_master_rows()

    by_sku = {}
    by_barcode = {}
    by_catalog = {}
    by_pim = {}
    by_key = {}

    for r in rows:
        sku_v = norm(get(r, ["sku", "SKU"], ""))
        barcode_v = norm(first_barcode(get(r, ["product_barcodes", "barcode", "Barcode", "Barcodes"], "")))
        catalog_v = norm(get(r, ["catalog_global_product_id"], ""))
        pim_v = norm(get(r, ["pim_product_id"], ""))
        pkey_v = norm(product_dedup_key(r))

        if sku_v:
            by_sku[sku_v] = r
        if barcode_v:
            by_barcode[barcode_v] = r
        if catalog_v:
            by_catalog[catalog_v] = r
        if pim_v:
            by_pim[pim_v] = r
        if pkey_v:
            by_key[pkey_v] = r

    MASTER_CACHE.update({
        "loaded": True,
        "rows": rows,
        "by_sku": by_sku,
        "by_barcode": by_barcode,
        "by_catalog": by_catalog,
        "by_pim": by_pim,
        "by_key": by_key,
    })

    return MASTER_CACHE


def find_master_match(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    master = load_master()

    sku_v = norm(get(p, ["sku", "SKU"], ""))
    barcode_v = norm(first_barcode(get(p, ["product_barcodes", "barcode", "Barcode", "Barcodes"], "")))
    catalog_v = norm(get(p, ["catalog_global_product_id"], ""))
    pim_v = norm(get(p, ["pim_product_id"], ""))
    pkey_v = norm(product_dedup_key(p))

    return (
        master["by_sku"].get(sku_v)
        or master["by_barcode"].get(barcode_v)
        or master["by_catalog"].get(catalog_v)
        or master["by_pim"].get(pim_v)
        or master["by_key"].get(pkey_v)
    )


# =====================================================
# PRODUCT ACCESSORS
# =====================================================

def product_name(p: Dict[str, Any]) -> str:
    return clean_text(get(p, ["product_name", "Product Name", "name"], ""))


def sku(p: Dict[str, Any]) -> str:
    return clean_text(get(p, ["sku", "SKU", "barcode"], ""))


def brand(p: Dict[str, Any]) -> str:
    b = get(p, ["brand", "Brand", "brand_name"], "")
    if clean_text(b):
        return clean_text(b)

    name = product_name(p)
    return clean_text(name.split(" ")[0]) if name else "UNKNOWN"


def category_l1(p: Dict[str, Any]) -> str:
    return clean_text(get(p, [
        "category_l1",
        "Category L1",
        "category",
        "frontend_category_local",
        "pim_cat_l1",
    ], "GENERAL"))


def category_l2(p: Dict[str, Any]) -> str:
    return clean_text(get(p, [
        "category_l2",
        "Category L2",
        "subcategory",
        "frontend_subcategory_local",
        "pim_cat_l2",
    ], "GENERAL"))


def image_url(p: Dict[str, Any]) -> str:
    return clean_text(get(p, [
        "image_url",
        "Product Image URL",
        "catalog_image_url",
        "pim_image_url",
    ], ""))


def storage_type(p: Dict[str, Any]) -> str:
    raw = key(
        f"{get(p, ['storage_type', 'Storage Type', 'Storage'], '')} "
        f"{product_name(p)} "
        f"{category_l1(p)} "
        f"{category_l2(p)}"
    )

    if any(x in raw for x in ["FROZEN", "DONUK", "-18", "DONDUR", "ICE CREAM", "FREEZER", "ALGIDA"]):
        return "FROZEN"

    if any(x in raw for x in ["CHILLED", "COLD", "+4", "SÜT", "SUT", "DAIRY", "YOĞURT", "YOGURT", "FRIDGE"]):
        return "CHILLED"

    return "AMBIENT"


def shelf_storage(shelf: Dict[str, Any]) -> str:
    return key(get(shelf, ["allowed_storage_type"], "AMBIENT"))


def width(p: Dict[str, Any]) -> float:
    return max(1, num(get(p, ["width_cm", "Width", "en", "product_width_in_cm"], 10), 10))


def height(p: Dict[str, Any]) -> float:
    return max(1, num(get(p, ["height_cm", "Height", "boy", "product_height_in_cm"], 20), 20))


def depth(p: Dict[str, Any]) -> float:
    return max(1, num(get(p, ["depth_cm", "Depth", "derinlik", "product_length_in_cm"], 10), 10))


def weight(p: Dict[str, Any]) -> float:
    return max(0.01, num(get(p, ["weight_kg", "Weight", "agirlik", "product_weight_value"], 0.2), 0.2))


def sales_7d(p: Dict[str, Any]) -> float:
    return num(get(p, ["sales_qty_7d", "sales_7d", "sales", "Sales 7D", "% Orders", "percent_orders"], 0), 0)


def percent_stops(p: Dict[str, Any]) -> float:
    return num(get(p, ["percent_stops", "% Stops", "Picking Frequency"], 0), 0)


def on_hand(p: Dict[str, Any]) -> float:
    return num(get(p, ["on_hand_qty", "On-Hand Qty", "stock", "Stock", "Stok"], 0), 0)


def case_pack(p: Dict[str, Any]) -> float:
    return max(1, num(get(p, [
        "case_pack_qty",
        "case_pack",
        "Case Pack",
        "units_in_pack_count",
    ], 12), 12))


def is_approval(p: Dict[str, Any]) -> bool:
    raw = key(f"{get(p, ['current_location', 'Location', 'Lokasyon'], '')} {get(p, ['secondary_location'], '')}")
    return any(x in raw for x in ["APPROVAL", "APPROVE", "ONAY", "FIRE", "IMHA", "İMHA"])


# =====================================================
# ENRICHMENT / NORMALIZATION
# =====================================================

def ai_estimate_dimensions(p: Dict[str, Any]) -> Dict[str, Any]:
    raw = norm(f"{product_name(p)} {category_l1(p)} {category_l2(p)} {brand(p)}")
    st = storage_type(p)

    if any(x in raw for x in ["poset", "poşet", "shopping bag", "bag"]):
        return {"width_cm": 18, "height_cm": 28, "depth_cm": 2, "weight_kg": 0.02, "confidence": 0.88, "reason": "shopping_bag"}

    if "su" in raw or "water" in raw:
        if any(x in raw for x in ["5l", "5 l", "10l", "10 l"]):
            return {"width_cm": 24, "height_cm": 36, "depth_cm": 24, "weight_kg": 5, "confidence": 0.75, "reason": "large_water"}
        return {"width_cm": 8, "height_cm": 28, "depth_cm": 8, "weight_kg": 1, "confidence": 0.70, "reason": "water_bottle"}

    if any(x in raw for x in ["cola", "kola", "fanta", "sprite", "icecek", "içecek", "beverage"]):
        return {"width_cm": 9, "height_cm": 28, "depth_cm": 9, "weight_kg": 1, "confidence": 0.68, "reason": "beverage"}

    if any(x in raw for x in ["cips", "chips", "ruffles", "lays", "doritos"]):
        return {"width_cm": 18, "height_cm": 25, "depth_cm": 6, "weight_kg": 0.12, "confidence": 0.62, "reason": "chips_bag"}

    if any(x in raw for x in ["cikolata", "çikolata", "chocolate"]):
        return {"width_cm": 8, "height_cm": 16, "depth_cm": 2, "weight_kg": 0.08, "confidence": 0.60, "reason": "chocolate_bar"}

    if st == "CHILLED":
        return {"width_cm": 10, "height_cm": 18, "depth_cm": 10, "weight_kg": 0.5, "confidence": 0.55, "reason": "chilled_generic"}

    if st == "FROZEN":
        return {"width_cm": 14, "height_cm": 16, "depth_cm": 12, "weight_kg": 0.5, "confidence": 0.52, "reason": "frozen_generic"}

    return {"width_cm": 10, "height_cm": 20, "depth_cm": 10, "weight_kg": 0.3, "confidence": 0.35, "reason": "generic"}


def enrich_product(raw: Dict[str, Any], allow_ai_dimensions: bool = True) -> Dict[str, Any]:
    original = dict(raw or {})
    original = apply_overrides_to_product(original)

    master = find_master_match(original) or {}

    merged = {**master, **original}

    p_name = first_non_empty(
        get(original, ["product_name", "Product Name", "name"], ""),
        get(master, ["product_name", "product_name_local", "pim_product_name_local"], ""),
    )

    b_name = first_non_empty(
        get(original, ["brand", "Brand", "brand_name"], ""),
        get(master, ["brand_name"], ""),
        p_name.split(" ")[0] if p_name else "",
        "UNKNOWN",
    )

    cat1 = first_non_empty(
        get(original, ["category_l1", "Category L1", "category", "frontend_category_local"], ""),
        get(master, ["frontend_category_local", "pim_cat_l1"], ""),
        "GENERAL",
    )

    cat2 = first_non_empty(
        get(original, ["category_l2", "Category L2", "subcategory", "frontend_subcategory_local"], ""),
        get(master, ["frontend_subcategory_local", "pim_cat_l2"], ""),
        "GENERAL",
    )

    base = {
        **merged,
        "product_name": p_name,
        "brand": b_name,
        "brand_name": b_name,
        "category_l1": cat1,
        "category_l2": cat2,
    }

    estimate = ai_estimate_dimensions(base)

    file_w = get(original, ["width_cm", "Width", "en", "product_width_in_cm"], "")
    file_h = get(original, ["height_cm", "Height", "boy", "product_height_in_cm"], "")
    file_d = get(original, ["depth_cm", "Depth", "derinlik", "product_length_in_cm"], "")

    master_w = get(master, ["product_width_in_cm", "width_cm"], "")
    master_h = get(master, ["product_height_in_cm", "height_cm"], "")
    master_d = get(master, ["product_length_in_cm", "depth_cm"], "")

    has_file_dim = file_w not in [None, ""] and file_h not in [None, ""] and file_d not in [None, ""]
    has_master_dim = master_w not in [None, ""] and master_h not in [None, ""] and master_d not in [None, ""]

    if has_file_dim:
        w, h, d = num(file_w), num(file_h), num(file_d)
        dim_source, dim_conf, dim_reason = "file", 1, "file_dimensions"
    elif has_master_dim:
        w, h, d = num(master_w), num(master_h), num(master_d)
        dim_source, dim_conf, dim_reason = "master", 1, "master_dimensions"
    elif allow_ai_dimensions:
        w, h, d = estimate["width_cm"], estimate["height_cm"], estimate["depth_cm"]
        dim_source, dim_conf, dim_reason = "ai_estimated", estimate["confidence"], estimate["reason"]
    else:
        w, h, d = 0, 0, 0
        dim_source, dim_conf, dim_reason = "missing", 0, "missing_dimensions"

    result = {
        **merged,
        "sku": first_non_empty(get(original, ["sku", "SKU"], ""), get(master, ["sku"], ""), get(original, ["barcode"], "")),
        "barcode": first_non_empty(
            get(original, ["barcode", "Barcode", "Barcodes", "product_barcodes"], ""),
            get(master, ["product_barcodes"], ""),
        ),
        "pim_product_id": first_non_empty(get(original, ["pim_product_id"], ""), get(master, ["pim_product_id"], "")),
        "catalog_global_product_id": first_non_empty(get(original, ["catalog_global_product_id"], ""), get(master, ["catalog_global_product_id"], "")),
        "planogram_product_key": product_dedup_key({**master, **original}),
        "product_name": p_name,
        "brand": b_name,
        "brand_name": b_name,
        "category_l1": cat1,
        "category_l2": cat2,
        "frontend_category_local": cat1,
        "frontend_subcategory_local": cat2,
        "storage_type": storage_type(base),
        "image_url": first_non_empty(
            get(original, ["image_url", "Product Image URL", "catalog_image_url", "pim_image_url"], ""),
            get(master, ["image_url", "catalog_image_url", "pim_image_url"], ""),
        ),
        "width_cm": max(0, w),
        "height_cm": max(0, h),
        "depth_cm": max(0, d),
        "weight_kg": max(0.01, num(first_non_empty(
            get(original, ["weight_kg", "Weight", "product_weight_value"], ""),
            get(master, ["product_weight_value"], ""),
            estimate.get("weight_kg", 0.2),
        ), 0.2)),
        "sales_qty_7d": sales_7d(original),
        "percent_stops": percent_stops(original),
        "on_hand_qty": on_hand(original),
        "case_pack_qty": case_pack({**master, **original}),
        "dimension_source": dim_source,
        "dimension_confidence": dim_conf,
        "dimension_reason": dim_reason,
        "current_location": clean_text(get(original, ["current_location", "Location", "Lokasyon"], "")),
        "secondary_location": clean_text(get(original, ["secondary_location"], "")),
    }

    result["_storage"] = storage_type(result)
    result["_merch_group"] = merch_group(result)
    return result


# =====================================================
# PRODUCT CLASSIFICATION
# =====================================================

def merch_group(p: Dict[str, Any]) -> str:
    raw = key(f"{product_name(p)} {category_l1(p)} {category_l2(p)} {brand(p)}")
    st = storage_type(p)

    if st == "CHILLED":
        return "FOOD_CHILLED"
    if st == "FROZEN":
        return "FOOD_FROZEN"

    odor_words = [
        "DOMESTOS", "DETERJAN", "TEMIZ", "TEMİZ", "BLEACH",
        "ÇAMAŞIR", "CAMASIR", "YUMUSATICI", "YUMUŞATICI",
        "CLEANING", "SOAP", "DOVE", "ŞAMPUAN", "SHAMPOO",
        "TUVALET", "BANYO", "MUTFAK", "KIREC", "KİREÇ",
    ]

    if any(w in raw for w in odor_words):
        return "NON_FOOD_ODOR"

    non_food_words = [
        "DISPOSABLE", "POŞET", "POSET", "BAG", "PET", "HOME",
        "PEÇETE", "PECETE", "KAĞIT", "KAGIT", "FOIL", "STREÇ", "STREC",
    ]

    if any(w in raw for w in non_food_words):
        return "NON_FOOD_NEUTRAL"

    return "FOOD_AMBIENT"


def is_food(p: Dict[str, Any]) -> bool:
    return merch_group(p).startswith("FOOD")


def is_odor(p: Dict[str, Any]) -> bool:
    return merch_group(p) == "NON_FOOD_ODOR"


def product_score(p: Dict[str, Any]) -> float:
    return sales_7d(p) * 3.0 + percent_stops(p) * 12.0 + on_hand(p) * 0.02


def classify_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(products, key=product_score, reverse=True)
    n = max(len(ranked), 1)
    result = []

    for i, p in enumerate(ranked):
        x = dict(p)
        pct = i / n

        if pct <= 0.08:
            tier, abc = "HOT", "A"
        elif pct <= 0.25:
            tier, abc = "FAST", "A"
        elif pct <= 0.55:
            tier, abc = "MID", "B"
        else:
            tier, abc = "BACK", "C"

        x["_tier"] = get(x, ["tier", "front_tier"], "") or tier
        x["_abc"] = get(x, ["abc", "abc_class", "ABC"], "") or abc
        x["_score"] = product_score(x)
        x["_storage"] = storage_type(x)
        x["_merch_group"] = merch_group(x)
        result.append(x)

    return result


# =====================================================
# FACING / DEPTH / COVERAGE
# =====================================================

def facing_count(p: Dict[str, Any]) -> int:
    s = sales_7d(p)
    stops = percent_stops(p)
    tier = p.get("_tier")

    if tier == "HOT" or s >= 140 or stops >= 10:
        return 5
    if tier == "FAST" or s >= 80 or stops >= 6:
        return 3
    if tier == "MID" or s >= 30:
        return 2
    return 1


def depth_units(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    return max(1, int(num(shelf.get("shelf_depth_cm"), 50) // max(depth(p), 1)))


def total_capacity_units(p: Dict[str, Any], shelf: Dict[str, Any], facing: int) -> int:
    return depth_units(p, shelf) * facing


def coverage_days(p: Dict[str, Any], shelf: Dict[str, Any], facing: int) -> Optional[float]:
    s = sales_7d(p)
    if s <= 0:
        return None
    return round((total_capacity_units(p, shelf, facing) / s) * 7, 1)


def preferred_facing(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    base = facing_count(p)
    cp = case_pack(p)
    depth_cap = depth_units(p, shelf)
    weekly = sales_7d(p)

    if weekly > 0:
        needed_units = min(max(cp, weekly * 0.7), weekly * 1.4)
        needed_facing = int((needed_units + depth_cap - 1) // depth_cap)
        base = max(base, needed_facing)

    return max(1, min(8, base))


def used_width(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    f = preferred_facing(p, shelf)
    effective_width = depth(p) if p.get("is_rotated") else width(p)
    return effective_width * f * 1.1


# =====================================================
# LAYOUT
# =====================================================

def make_shelves(count: int, storage: str = "AMBIENT", width_cm: float = 100, height_cm: float = 35, depth_cm: float = 50, max_weight: float = 45) -> List[Dict[str, Any]]:
    shelves = []
    count = max(1, int(count))

    for i in range(count):
        no = i + 1
        if no == 1:
            zone = "bottom"
        elif no == count:
            zone = "top"
        elif no in [math.ceil(count / 2), math.ceil(count / 2) + 1]:
            zone = "eye"
        else:
            zone = "mid"

        shelves.append({
            "shelf_no": no,
            "shelf_width_cm": width_cm,
            "shelf_height_cm": height_cm,
            "shelf_depth_cm": depth_cm,
            "max_weight_kg": max_weight,
            "zone_type": zone,
            "allowed_storage_type": storage,
            "allowed_categories": [],
            "blocked_categories": [],
            "assignment_rule": None,
            "products": [],
            "used_width_cm": 0,
            "used_weight_kg": 0,
            "used": 0,
        })

    return shelves


def generate_default_layout() -> Dict[str, Any]:
    aisles = []
    rows = [
        {"ids": ["A", "B", "C", "D"], "dir": "LTR"},
        {"ids": ["H", "G", "F", "E"], "dir": "RTL"},
        {"ids": ["I", "J", "K", "L"], "dir": "LTR"},
    ]

    distance = 1

    for row_index, row in enumerate(rows):
        for pos_index, aid in enumerate(row["ids"]):
            aisles.append({
                "aisle_id": aid,
                "row": row_index + 1,
                "position": pos_index + 1,
                "direction": row["dir"],
                "distance_to_dispatch": distance,
                "aisle_type": "double_sided",
                "sides": ["L", "R"],
                "zone_type": "AMBIENT_ZONE",
                "modules": [
                    {
                        "module_id": i + 1,
                        "side": "L" if i % 2 == 0 else "R",
                        "module_type": "regular_shelf",
                        "distance_to_dispatch": i + 1,
                        "module_width_cm": 100,
                        "module_depth_cm": 50,
                        "module_height_cm": 200,
                        "assignment_rule": None,
                        "shelves": make_shelves(6, "AMBIENT", 100, 35, 50, 45),
                    }
                    for i in range(10)
                ],
            })
            distance += 1

    aisles.append({
        "aisle_id": "MARTEK+4",
        "row": 2,
        "position": 5,
        "direction": "COLD",
        "distance_to_dispatch": distance,
        "aisle_type": "single_sided",
        "sides": ["L"],
        "zone_type": "COLD_ZONE",
        "fixture_type": "four_door_cooler",
        "door_count": 4,
        "modules": [
            {
                "module_id": i + 1,
                "door_no": f"{i * 2 + 1}-{i * 2 + 2}",
                "side": "L",
                "module_type": "fridge",
                "fixture_type": "cooler_module_2door",
                "temperature": "+4",
                "module_width_cm": 150,
                "module_depth_cm": 60,
                "module_height_cm": 200,
                "assignment_rule": None,
                "shelves": make_shelves(5, "CHILLED", 150, 35, 55, 60),
            }
            for i in range(2)
        ],
    })
    distance += 1

    aisles.append({
        "aisle_id": "MARTEK-18",
        "row": 1,
        "position": 5,
        "direction": "COLD",
        "distance_to_dispatch": distance,
        "aisle_type": "single_sided",
        "sides": ["L"],
        "zone_type": "FROZEN_ZONE",
        "fixture_type": "four_door_freezer",
        "door_count": 4,
        "modules": [
            {
                "module_id": i + 1,
                "door_no": f"{i * 2 + 1}-{i * 2 + 2}",
                "side": "L",
                "module_type": "freezer",
                "fixture_type": "freezer_module_2door",
                "temperature": "-18",
                "module_width_cm": 150,
                "module_depth_cm": 65,
                "module_height_cm": 200,
                "assignment_rule": None,
                "shelves": make_shelves(4, "FROZEN", 150, 40, 60, 70),
            }
            for i in range(2)
        ],
    })

    return {
        "store_code": "AUTO",
        "route_strategy": "S_PATTERN_DYNAMIC",
        "aisles": aisles,
    }


def prepare_layout(layout: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    plan = deepcopy(layout or generate_default_layout())

    for a in plan.get("aisles", []):
        for m in a.get("modules", []):
            for s in m.get("shelves", []):
                s["products"] = []
                s["used_width_cm"] = 0
                s["used_weight_kg"] = 0
                s["used"] = 0

    return plan


# =====================================================
# SCORING
# =====================================================

def route_score(aisle: Dict[str, Any], module: Dict[str, Any]) -> float:
    row = num(aisle.get("row"), 99)
    pos = num(aisle.get("position"), 99)
    mid = num(module.get("module_id"), 99)
    return row * 100 + pos * 10 + mid


def front_zone_score(p: Dict[str, Any], aisle: Dict[str, Any]) -> float:
    aid = key(aisle.get("aisle_id"))
    tier = p.get("_tier")

    if is_odor(p):
        if aid in ["A", "B"]:
            return -500
        if aid in ["I", "J", "K", "L", "Z"]:
            return 200
        return 50

    if tier == "HOT":
        if aid == "A":
            return 300
        if aid == "B":
            return 220
        if aid in ["C", "D"]:
            return 100
        return -80

    if tier == "FAST":
        if aid in ["A", "B"]:
            return 220
        if aid in ["C", "D", "H", "G"]:
            return 100
        return -20

    if tier == "MID":
        if aid in ["C", "D", "H", "G", "F", "E"]:
            return 120
        if aid in ["A", "B"]:
            return -40
        return 40

    if aid in ["I", "J", "K", "L", "Z", "E", "F"]:
        return 140

    if aid in ["A", "B"]:
        return -180

    return 30


def ergonomics_score(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    z = key(shelf.get("zone_type"))
    w = weight(p)
    tier = p.get("_tier")

    if w >= 3:
        if z == "BOTTOM":
            return 160
        if z in ["TOP", "EYE"]:
            return -100

    if tier in ["HOT", "FAST"]:
        if z == "EYE":
            return 160
        if z == "MID":
            return 120
        if z == "BOTTOM":
            return 20
        return -40

    if tier == "BACK":
        if z in ["TOP", "BOTTOM"]:
            return 80
        return 20

    return 50


def storage_score(p: Dict[str, Any], aisle: Dict[str, Any], module: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    needed = p.get("_storage") or storage_type(p)
    allowed = shelf_storage(shelf)

    if needed != allowed:
        return -99999

    mtype = key(module.get("module_type"))

    if needed == "CHILLED" and "FRIDGE" in mtype:
        return 300
    if needed == "FROZEN" and "FREEZER" in mtype:
        return 300
    if needed == "AMBIENT" and "REGULAR" in mtype:
        return 120

    return 50


def brand_score(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    products = shelf.get("products", [])
    if not products:
        return 40

    same_brand = sum(1 for x in products if norm(x.get("brand")) == norm(brand(p)))
    same_cat = sum(1 for x in products if norm(x.get("category_l2")) == norm(category_l2(p)))

    return same_brand * 180 + same_cat * 90


def balance_score(shelf: Dict[str, Any]) -> float:
    used = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    width_cm = num(shelf.get("shelf_width_cm"), 100)
    util = used / max(width_cm, 1)

    if util == 0:
        return 70
    if util < 0.35:
        return 40
    if util < 0.75:
        return 10
    if util > 0.90:
        return -120

    return -20


def coverage_score(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    f = preferred_facing(p, shelf)
    cov = coverage_days(p, shelf, f)

    if cov is None:
        return 0
    if cov < 1:
        return -140
    if cov < 2:
        return -60
    if cov <= 7:
        return 80
    return 40


def brand_side(product: Dict[str, Any], module: Dict[str, Any], rules: Optional[Dict[str, str]]) -> float:
    if not rules:
        rules = DEFAULT_BRAND_SIDE_RULES

    b = norm(brand(product))
    c = norm(category_l1(product))

    normalized = {norm(k): key(v) for k, v in rules.items()}

    wanted = (
        normalized.get(f"{c}::{b}")
        or normalized.get(f"all::{b}")
        or normalized.get(b)
    )

    if not wanted:
        for rk, rv in normalized.items():
            rule_brand = rk.split("::")[-1]
            if rule_brand and rule_brand in b:
                wanted = rv
                break

    if not wanted:
        return 0

    return 60 if key(module.get("side")) == wanted else -120


def module_rule_matches(p: Dict[str, Any], module: Dict[str, Any]) -> bool:
    rule = module.get("assignment_rule")
    if not rule:
        return True

    rb = norm(rule.get("brand", ""))
    rc = norm(rule.get("category", ""))

    b = norm(brand(p))
    n = norm(product_name(p))
    c1 = norm(category_l1(p))
    c2 = norm(category_l2(p))

    brand_ok = True if not rb else rb in b or rb in n
    cat_ok = True if not rc else rc in c1 or rc in c2

    return brand_ok and cat_ok


def existing_groups_on_aisle(aisle: Dict[str, Any]) -> set:
    groups = set()
    for m in aisle.get("modules", []):
        for s in m.get("shelves", []):
            for p in s.get("products", []):
                g = p.get("merch_group") or p.get("_merch_group")
                if g:
                    groups.add(g)
    return groups


def merch_compatible(p: Dict[str, Any], aisle: Dict[str, Any], cached_groups: Optional[set] = None) -> bool:
    aid = key(aisle.get("aisle_id"))
    groups = cached_groups if cached_groups is not None else existing_groups_on_aisle(aisle)

    if aid == "A" and not is_food(p):
        return False

    if is_food(p) and "NON_FOOD_ODOR" in groups:
        return False

    if is_odor(p) and any(str(g).startswith("FOOD") for g in groups):
        return False

    return True


def placement_score(
    p: Dict[str, Any],
    aisle: Dict[str, Any],
    module: Dict[str, Any],
    shelf: Dict[str, Any],
    scoring_config: Optional[Dict[str, float]] = None,
    brand_side_rules: Optional[Dict[str, str]] = None,
) -> float:
    cfg = {**DEFAULT_SCORING_CONFIG, **(scoring_config or {})}

    score = 0
    score += p.get("_score", 0) * 1.2 * cfg["sales"]
    score += front_zone_score(p, aisle) * cfg["picking"]
    score += ergonomics_score(p, shelf) * cfg["ergonomics"]
    score += storage_score(p, aisle, module, shelf) * cfg["fixture"]
    score += brand_score(p, shelf) * cfg["brand_cluster"]
    score += balance_score(shelf) * cfg["balance"]
    score += coverage_score(p, shelf) * cfg["coverage"]

    score += max(0, 220 - route_score(aisle, module) * 0.8) * cfg["picking"]
    score += brand_side(p, module, brand_side_rules)

    if sales_7d(p) < 10 and key(aisle.get("aisle_id")) in ["A", "B"]:
        score -= 250

    if p.get("dimension_source") == "ai_estimated" and num(p.get("dimension_confidence"), 0) < 0.55:
        score -= 50 * cfg["risk"]

    return score


# =====================================================
# CONSTRAINTS
# =====================================================

def dimension_fit(p: Dict[str, Any], shelf: Dict[str, Any]) -> bool:
    if height(p) > num(shelf.get("shelf_height_cm"), 35):
        return False
    if depth(p) > num(shelf.get("shelf_depth_cm"), 50):
        return False
    return True


def weight_fit(p: Dict[str, Any], shelf: Dict[str, Any]) -> bool:
    current = num(shelf.get("used_weight_kg"), 0)
    add = weight(p) * preferred_facing(p, shelf)
    limit = num(shelf.get("max_weight_kg"), 45)
    return current + add <= limit


def capacity_fit(p: Dict[str, Any], shelf: Dict[str, Any]) -> bool:
    current = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    return current + used_width(p, shelf) <= num(shelf.get("shelf_width_cm"), 100)


def can_place(
    p: Dict[str, Any],
    aisle: Dict[str, Any],
    module: Dict[str, Any],
    shelf: Dict[str, Any],
    aisle_groups: Optional[set] = None,
) -> Tuple[bool, str]:
    if storage_score(p, aisle, module, shelf) < -1000:
        return False, "storage_not_fit"

    if not module_rule_matches(p, module):
        return False, "module_rule_not_match"

    shelf_rule = shelf.get("assignment_rule")
    if shelf_rule and not module_rule_matches(p, {"assignment_rule": shelf_rule}):
        return False, "shelf_rule_not_match"

    if not merch_compatible(p, aisle, aisle_groups):
        return False, "merch_not_compatible"

    if not dimension_fit(p, shelf):
        return False, "dimension_not_fit"

    if not capacity_fit(p, shelf):
        return False, "capacity_not_fit"

    if not weight_fit(p, shelf):
        return False, "weight_not_fit"

    return True, "ok"


# =====================================================
# FAST INDEX
# =====================================================

def build_shelf_index(plan: Dict[str, Any]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, set]]:
    shelf_pool = {"AMBIENT": [], "CHILLED": [], "FROZEN": [], "PALLET": []}
    aisle_groups = {}

    for aisle in plan.get("aisles", []):
        aid = clean_text(aisle.get("aisle_id"))
        aisle_groups[aid] = set()

        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                storage = shelf_storage(shelf)
                if storage not in shelf_pool:
                    shelf_pool[storage] = []

                shelf_pool[storage].append({
                    "aisle": aisle,
                    "module": module,
                    "shelf": shelf,
                    "route": route_score(aisle, module),
                })

    return shelf_pool, aisle_groups


def place_product_fast(
    plan: Dict[str, Any],
    p: Dict[str, Any],
    shelf_pool: Dict[str, List[Dict[str, Any]]],
    aisle_groups: Dict[str, set],
    scoring_config: Optional[Dict[str, float]] = None,
    brand_side_rules: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Optional[Dict[str, Any]], str]:

    storage = p.get("_storage") or storage_type(p)

    candidates = shelf_pool.get(storage, [])

    candidates = sorted(
        candidates,
        key=lambda x: (
            num(x["shelf"].get("used_width_cm"), 0),
            x.get("route", 9999),
        )
    )[:40]

    best = None
    best_score = -10**18
    last_reason = "no_candidate"

    for item in candidates:
        aisle, module, shelf = item["aisle"], item["module"], item["shelf"]

        remaining_width = num(shelf.get("shelf_width_cm"), 100) - num(shelf.get("used_width_cm"), 0)

        if remaining_width < width(p):
            last_reason = "early_capacity_reject"
            continue

        aid = clean_text(aisle.get("aisle_id"))
        groups = aisle_groups.get(aid, set())

        ok, reason = can_place(p, aisle, module, shelf, groups)

        if not ok:
            last_reason = reason
            continue

        sc = placement_score(
            p,
            aisle,
            module,
            shelf,
            scoring_config,
            brand_side_rules,
        )

        if sc > best_score:
            best_score = sc
            best = item

    if not best:
        return False, None, last_reason

    aisle, module, shelf = best["aisle"], best["module"], best["shelf"]

    f = preferred_facing(p, shelf)
    u = used_width(p, shelf)
    cap_units = total_capacity_units(p, shelf, f)
    cov = coverage_days(p, shelf, f)

    placed = {
        "sku": sku(p),
        "barcode": clean_text(get(p, ["barcode", "product_barcodes"], "")),
        "product_name": product_name(p),
        "brand": brand(p),
        "brand_name": brand(p),
        "category_l1": category_l1(p),
        "category_l2": category_l2(p),
        "frontend_category_local": category_l1(p),
        "frontend_subcategory_local": category_l2(p),
        "image_url": image_url(p),
        "storage_type": p.get("_storage"),
        "merch_group": p.get("_merch_group"),
        "abc_class": p.get("_abc"),
        "tier": p.get("_tier"),
        "front_tier": p.get("_tier"),
        "sales_qty_7d": sales_7d(p),
        "percent_stops": percent_stops(p),
        "on_hand_qty": on_hand(p),
        "width_cm": width(p),
        "height_cm": height(p),
        "depth_cm": depth(p),
        "weight_kg": weight(p),
        "case_pack_qty": case_pack(p),
        "facing": f,
        "facing_count": f,
        "used_width_cm": round(u, 1),
        "depth_units": depth_units(p, shelf),
        "total_capacity_units": cap_units,
        "coverage_days": cov,
        "dimension_source": p.get("dimension_source"),
        "dimension_confidence": p.get("dimension_confidence"),
        "dimension_reason": p.get("dimension_reason"),
        "aisle": aisle.get("aisle_id"),
        "aisle_id": aisle.get("aisle_id"),
        "module_id": module.get("module_id"),
        "shelf_no": shelf.get("shelf_no"),
        "position_order": len(shelf.get("products", [])) + 1,
        "placement_score": round(best_score, 1),
    }

    shelf.setdefault("products", []).append(placed)
    shelf["used_width_cm"] = round(num(shelf.get("used_width_cm"), 0) + u, 1)
    shelf["used"] = shelf["used_width_cm"]
    shelf["used_weight_kg"] = round(num(shelf.get("used_weight_kg"), 0) + weight(p) * f, 2)

    aisle_groups.setdefault(clean_text(aisle.get("aisle_id")), set()).add(p.get("_merch_group"))

    return True, placed, "ok"

# =====================================================
# SUMMARY / DIAGNOSTICS
# =====================================================

def summarize(plan: Dict[str, Any], total_products: int, unplaced: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_width = 0
    used_width = 0
    capacity_warnings = []

    for a in plan.get("aisles", []):
        for m in a.get("modules", []):
            for s in m.get("shelves", []):
                sw = num(s.get("shelf_width_cm"), 100)
                su = num(s.get("used_width_cm", s.get("used", 0)), 0)
                total_width += sw
                used_width += su

                util = su / max(sw, 1)
                if util >= 0.90:
                    capacity_warnings.append({
                        "aisle": a.get("aisle_id"),
                        "module_id": m.get("module_id"),
                        "shelf_no": s.get("shelf_no"),
                        "utilization_pct": round(util * 100),
                    })

    placed = total_products - len(unplaced)

    return {
        "total": total_products,
        "placed": placed,
        "unplaced": len(unplaced),
        "total_products": total_products,
        "placed_products": placed,
        "unplaced_products": len(unplaced),
        "capacity_utilization_pct": round((used_width / max(total_width, 1)) * 100),
        "capacity_warnings": capacity_warnings,
        "strategy": "sales + category + storage + brand cluster + depth coverage + picking route + ergonomics + master enrichment",
    }


def validate_planogram(plan: Dict[str, Any]) -> Dict[str, Any]:
    violations = []
    empty_shelves = []
    overfilled_shelves = []
    low_fill_shelves = []

    for aisle in plan.get("aisles", []):
        for module in aisle.get("modules", []):
            module_rule = module.get("assignment_rule")

            for shelf in module.get("shelves", []):
                sw = num(shelf.get("shelf_width_cm"), 100)
                su = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
                util = su / max(sw, 1)

                base = {
                    "aisle_id": aisle.get("aisle_id"),
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                    "used_width_cm": round(su, 2),
                    "shelf_width_cm": round(sw, 2),
                    "utilization_pct": round(util * 100, 2),
                    "product_count": len(shelf.get("products", [])),
                    "allowed_storage_type": shelf_storage(shelf),
                }

                if not shelf.get("products"):
                    empty_shelves.append(base)
                elif util > 1:
                    overfilled_shelves.append(base)
                elif util < 0.35:
                    low_fill_shelves.append(base)

                for p in shelf.get("products", []):
                    if shelf_storage(shelf) != key(p.get("storage_type")):
                        violations.append({**base, "type": "storage_violation", "sku": p.get("sku"), "product_name": p.get("product_name")})

                    if module_rule and not module_rule_matches(p, module):
                        violations.append({**base, "type": "module_rule_violation", "sku": p.get("sku"), "product_name": p.get("product_name"), "rule": module_rule})

                    shelf_rule = shelf.get("assignment_rule")
                    if shelf_rule and not module_rule_matches(p, {"assignment_rule": shelf_rule}):
                        violations.append({**base, "type": "shelf_rule_violation", "sku": p.get("sku"), "product_name": p.get("product_name"), "rule": shelf_rule})

    return {
        "strict_rule_violations": violations,
        "empty_shelves": empty_shelves,
        "overfilled_shelves": overfilled_shelves,
        "low_fill_shelves": low_fill_shelves,
        "summary": {
            "strict_rule_violation_count": len(violations),
            "empty_shelf_count": len(empty_shelves),
            "overfilled_shelf_count": len(overfilled_shelves),
            "low_fill_shelf_count": len(low_fill_shelves),
        },
    }


# =====================================================
# MAIN ENGINE
# =====================================================

def generate_planogram(
    products: List[Dict[str, Any]],
    layout: Optional[Dict[str, Any]],
    mode: str = "HYBRID",
    brand_side_rules: Optional[Dict[str, str]] = None,
    scoring_config: Optional[Dict[str, float]] = None,
    allow_ai_dimensions: bool = True,
) -> Dict[str, Any]:
    raw_products = products or []
    plan = prepare_layout(layout or generate_default_layout())

    # PERFORMANCE GUARD
    MAX_PRODUCTS = 500

    raw_products = sorted(
        raw_products,
        key=lambda x: (
            -num(get(x, ["sales_qty_7d", "sales_7d", "sales"], 0), 0),
            -num(get(x, ["percent_stops", "% Stops"], 0), 0),
        )
    )[:MAX_PRODUCTS]


    clean_products = []
    unplaced = []
    alerts = {
        "approval_fire_products": [],
        "dimension_missing": [],
        "storage_violations": [],
        "capacity_warnings": [],
        "low_coverage": [],
        "ai_dimension_low_confidence": [],
    }

    for raw in raw_products:
        p = enrich_product(raw, allow_ai_dimensions=allow_ai_dimensions)

        if is_approval(p):
            item = {
                "sku": sku(p),
                "product_name": product_name(p),
                "reason": "approval_area_fire_stock",
                "suggested_action": "Approval/FIRE alanındaki ürün satış planogramına dahil edilmez.",
            }
            unplaced.append(item)
            alerts["approval_fire_products"].append(item)
            continue

        if not sku(p):
            unplaced.append({
                "sku": None,
                "product_name": product_name(p),
                "reason": "missing_sku",
            })
            continue

        if width(p) <= 0 or height(p) <= 0 or depth(p) <= 0:
            item = {
                "sku": sku(p),
                "product_name": product_name(p),
                "reason": "dimension_missing",
            }
            unplaced.append(item)
            alerts["dimension_missing"].append(item)
            continue

        if p.get("dimension_source") == "ai_estimated" and num(p.get("dimension_confidence"), 0) < 0.55:
            alerts["ai_dimension_low_confidence"].append({
                "sku": sku(p),
                "product_name": product_name(p),
                "confidence": p.get("dimension_confidence"),
                "reason": p.get("dimension_reason"),
            })

        clean_products.append(p)

    ranked = classify_products(clean_products)
    ranked = sorted(
        ranked,
        key=lambda p: (
            {"AMBIENT": 1, "CHILLED": 2, "FROZEN": 3, "PALLET": 4}.get(p.get("_storage"), 9),
            -p.get("_score", 0),
        ),
    )

    shelf_pool, aisle_groups = build_shelf_index(plan)

    for p in ranked:
        ok, placed, reason = place_product_fast(
            plan,
            p,
            shelf_pool,
            aisle_groups,
            scoring_config=scoring_config,
            brand_side_rules=brand_side_rules,
        )

        if not ok:
            unplaced.append({
                "sku": sku(p),
                "product_name": product_name(p),
                "brand": brand(p),
                "category_l1": category_l1(p),
                "category_l2": category_l2(p),
                "storage_type": p.get("_storage"),
                "reason": f"no_capacity_or_constraint_for_{p.get('_storage')}",
                "constraint_reason": reason,
                "suggested_action": "Raf/dolap kapasitesini artır, facing azalt, storage alanını kontrol et veya ürün ölçüsünü doğrula.",
            })
        else:
            if placed and placed.get("coverage_days") is not None and placed.get("coverage_days") < 1:
                alerts["low_coverage"].append({
                    "sku": placed["sku"],
                    "product_name": placed["product_name"],
                    "coverage_days": placed["coverage_days"],
                    "suggested_action": "Bu ürün için facing veya derinlik kapasitesi artırılmalı.",
                })

    summary = summarize(plan, len(raw_products), unplaced)
    alerts["capacity_warnings"] = summary["capacity_warnings"]

    diagnostics = validate_planogram(plan)

    return {
        "summary": summary,
        "planogram": plan,
        "unplaced": unplaced,
        "unplaced_products": unplaced,
        "alerts": alerts,
        "diagnostics": diagnostics,
        "insights": {
            "sales_optimization": "Yüksek satış ve yüksek stop oranlı ürünler ön koridorlara ve ergonomik raflara taşındı.",
            "category_logic": "Kategori ve marka blokları aynı raf/modül çevresinde tutulmaya çalışıldı.",
            "storage_logic": "CHILLED ve FROZEN ürünler yalnızca uygun dolap/freezer alanına yerleştirildi.",
            "depth_logic": "Raf derinliği, ürün derinliği ve koli içi adet bilgisiyle coverage hesaplandı.",
            "picking_efficiency": "A/B ön koridorlar hızlı ürünlere, arka koridorlar yavaş/non-food ürünlere ayrıldı.",
            "risk_notes": "Approval/FIRE ürünleri, storage dışı ürünler ve constraint dışı SKU'lar satış planogramına alınmadı.",
            "master_data": "Ürün görseli ve ölçüleri master_products dosyasından tamamlandı; eksiklerde AI tahmini kullanıldı.",
        },
        "recommended_actions": [
            "Coverage < 1 gün olan ürünlerde facing artır veya daha derin raf/dolap seç.",
            "Kapasite %90 üzeri raflarda SKU azalt veya blokları yeniden dağıt.",
            "Approval/FIRE alanındaki ürünleri satış planına dahil etme.",
            "Düşük satışlı markaları A koridorundan uzaklaştır; aynı marka içinde en satanı öne al.",
            "Non-food odor ürünlerini gıda koridorlarından ayır.",
            "AI tahmini ölçüleri düşük güvenliyse master data dosyasına doğrulanmış ölçü ekle.",
        ],
        "optimized": True,
    }


# Backward compatible alias
def run_engine(products: List[Dict[str, Any]], layout: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    return generate_planogram(products, layout, **kwargs)


# =====================================================
# EDIT / ACTION HELPERS
# =====================================================

def find_shelf(plan: Dict[str, Any], aisle_id: str, module_id: int, shelf_no: int):
    for aisle in plan.get("aisles", []):
        if clean_text(aisle.get("aisle_id")) != clean_text(aisle_id):
            continue
        for module in aisle.get("modules", []):
            if inum(module.get("module_id")) != inum(module_id):
                continue
            for shelf in module.get("shelves", []):
                if inum(shelf.get("shelf_no")) == inum(shelf_no):
                    return aisle, module, shelf
    return None, None, None


def find_product(plan: Dict[str, Any], target_sku: str) -> Optional[Dict[str, Any]]:
    for aisle in plan.get("aisles", []):
        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                for p in shelf.get("products", []):
                    if clean_text(p.get("sku")) == clean_text(target_sku):
                        return p
    return None


def remove_product_from_plan(plan: Dict[str, Any], target_sku: str) -> Optional[Dict[str, Any]]:
    for aisle in plan.get("aisles", []):
        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                products = shelf.get("products", [])
                for i, p in enumerate(products):
                    if clean_text(p.get("sku")) == clean_text(target_sku):
                        removed = products.pop(i)
                        recalc_plan(plan)
                        return removed
    return None


def recalc_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    for aisle in plan.get("aisles", []):
        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                su = 0
                sw = 0
                for p in shelf.get("products", []):
                    fake = {**p, "_storage": p.get("storage_type"), "_tier": p.get("front_tier"), "_abc": p.get("abc_class")}
                    su += num(p.get("used_width_cm"), 0) or used_width(fake, shelf)
                    sw += weight(fake) * inum(p.get("facing_count", p.get("facing", 1)), 1)

                shelf["used_width_cm"] = round(su, 1)
                shelf["used"] = shelf["used_width_cm"]
                shelf["used_weight_kg"] = round(sw, 2)

    return plan


def add_product_to_shelf(plan: Dict[str, Any], product: Dict[str, Any], aisle_id: str, module_id: int, shelf_no: int, force: bool = False) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    p = enrich_product(product)

    remove_product_from_plan(next_plan, sku(p))

    aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)
    if not shelf:
        return {"status": "error", "message": "target_shelf_not_found", "planogram": next_plan}

    p = classify_products([p])[0]

    ok, reason = can_place(p, aisle, module, shelf, existing_groups_on_aisle(aisle))
    if not ok and not force:
        return {
            "status": "error",
            "message": "product_cannot_fit_target_shelf",
            "reason": reason,
            "product": p,
            "planogram": next_plan,
        }

    f = preferred_facing(p, shelf)
    u = used_width(p, shelf)

    placed = {
        **p,
        "sku": sku(p),
        "product_name": product_name(p),
        "brand": brand(p),
        "category_l1": category_l1(p),
        "category_l2": category_l2(p),
        "image_url": image_url(p),
        "storage_type": p.get("_storage"),
        "facing": f,
        "facing_count": f,
        "used_width_cm": round(u, 1),
        "aisle_id": aisle.get("aisle_id"),
        "module_id": module.get("module_id"),
        "shelf_no": shelf.get("shelf_no"),
        "position_order": len(shelf.get("products", [])) + 1,
    }

    shelf.setdefault("products", []).append(placed)
    recalc_plan(next_plan)

    return {"status": "success", "planogram": next_plan, "product": placed}


def update_facing(plan: Dict[str, Any], target_sku: str, delta: int) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    p = find_product(next_plan, target_sku)

    if not p:
        return {"status": "error", "message": "sku_not_found", "planogram": next_plan}

    p["facing_count"] = max(1, min(12, inum(p.get("facing_count", p.get("facing", 1)), 1) + delta))
    p["facing"] = p["facing_count"]

    recalc_plan(next_plan)
    return {"status": "success", "planogram": next_plan, "product": p}


def rotate_product(plan: Dict[str, Any], target_sku: str) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    p = find_product(next_plan, target_sku)

    if not p:
        return {"status": "error", "message": "sku_not_found", "planogram": next_plan}

    p["is_rotated"] = not bool(p.get("is_rotated"))
    recalc_plan(next_plan)

    return {"status": "success", "planogram": next_plan, "product": p}


def move_product(plan: Dict[str, Any], target_sku: str, aisle_id: str, module_id: int, shelf_no: int, force: bool = False) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    removed = remove_product_from_plan(next_plan, target_sku)

    if not removed:
        return {"status": "error", "message": "sku_not_found", "planogram": next_plan}

    return add_product_to_shelf(next_plan, removed, aisle_id, module_id, shelf_no, force=force)


def apply_module_rule(layout: Dict[str, Any], aisle_id: str, module_id: int, rule: Dict[str, Any]) -> Dict[str, Any]:
    next_layout = deepcopy(layout)

    for aisle in next_layout.get("aisles", []):
        if clean_text(aisle.get("aisle_id")) != clean_text(aisle_id):
            continue
        for module in aisle.get("modules", []):
            if inum(module.get("module_id")) == inum(module_id):
                module["assignment_rule"] = rule

    return next_layout


def apply_shelf_rule(layout: Dict[str, Any], aisle_id: str, module_id: int, shelf_no: int, rule: Dict[str, Any]) -> Dict[str, Any]:
    next_layout = deepcopy(layout)
    _, _, shelf = find_shelf(next_layout, aisle_id, module_id, shelf_no)

    if shelf:
        shelf["assignment_rule"] = rule
        if rule.get("allowed_storage_type"):
            shelf["allowed_storage_type"] = rule["allowed_storage_type"]

    return next_layout


def suggest_empty_space(plan: Dict[str, Any], products: List[Dict[str, Any]], aisle_id: str, module_id: int, shelf_no: int, limit: int = 30) -> Dict[str, Any]:
    aisle, module, shelf = find_shelf(plan, aisle_id, module_id, shelf_no)
    if not shelf:
        return {"status": "error", "message": "shelf_not_found", "suggestions": []}

    placed_skus = set()
    for a in plan.get("aisles", []):
        for m in a.get("modules", []):
            for s in m.get("shelves", []):
                for p in s.get("products", []):
                    placed_skus.add(clean_text(p.get("sku")))

    remaining = num(shelf.get("shelf_width_cm"), 100) - num(shelf.get("used_width_cm"), 0)

    existing_brands = {norm(p.get("brand")) for p in shelf.get("products", [])}
    existing_cat1 = {norm(p.get("category_l1")) for p in shelf.get("products", [])}
    existing_cat2 = {norm(p.get("category_l2")) for p in shelf.get("products", [])}

    suggestions = []

    for raw in products:
        p = enrich_product(raw)
        p = classify_products([p])[0]

        if sku(p) in placed_skus:
            continue

        ok, reason = can_place(p, aisle, module, shelf, existing_groups_on_aisle(aisle))
        if not ok:
            continue

        f = preferred_facing(p, shelf)
        usage = used_width(p, shelf)

        if usage > remaining:
            continue

        sc = product_score(p)
        if norm(brand(p)) in existing_brands:
            sc += 300
        if norm(category_l2(p)) in existing_cat2:
            sc += 180
        if norm(category_l1(p)) in existing_cat1:
            sc += 120

        suggestions.append({
            **p,
            "sku": sku(p),
            "product_name": product_name(p),
            "brand": brand(p),
            "category_l1": category_l1(p),
            "category_l2": category_l2(p),
            "image_url": image_url(p),
            "facing_count": f,
            "estimated_usage_cm": round(usage, 2),
            "remaining_width_cm": round(remaining, 2),
            "suggestion_score": round(sc, 2),
            "fit_reason": "Storage uyumu, kalan cm, aynı marka/kategori yakınlığı ve satış skoruna göre önerildi.",
        })

    suggestions.sort(key=lambda x: x["suggestion_score"], reverse=True)

    return {
        "status": "success",
        "remaining_width_cm": round(remaining, 2),
        "suggestions": suggestions[:limit],
    }


# =====================================================
# BLOCK STUDIO / SHELF-MODULE OPTIMIZE
# =====================================================

def commit_block_studio(plan: Dict[str, Any], aisle_id: str, module_id: int, shelf_no: int, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)

    if not shelf:
        return {"status": "error", "message": "shelf_not_found", "planogram": next_plan}

    shelf_width = num(shelf.get("shelf_width_cm"), 100)
    rebuilt = []
    block_results = []

    for block in blocks:
        block_width = shelf_width * num(block.get("width_pct"), 0) / 100
        block_products = [classify_products([enrich_product(p)])[0] for p in block.get("products", [])]
        block_products.sort(key=product_score, reverse=True)

        used = 0
        accepted = []
        rejected = []

        for p in block_products:
            f = preferred_facing(p, shelf)
            usage = used_width(p, shelf)

            if used + usage <= block_width:
                placed = {
                    **p,
                    "sku": sku(p),
                    "product_name": product_name(p),
                    "brand": brand(p),
                    "category_l1": category_l1(p),
                    "category_l2": category_l2(p),
                    "image_url": image_url(p),
                    "storage_type": p.get("_storage"),
                    "facing_count": f,
                    "facing": f,
                    "used_width_cm": round(usage, 1),
                    "block_name": block.get("name"),
                    "position_order": len(rebuilt) + 1,
                }
                accepted.append(placed)
                rebuilt.append(placed)
                used += usage
            else:
                rejected.append({
                    "sku": sku(p),
                    "product_name": product_name(p),
                    "reason": "block_capacity_not_enough",
                    "needed_width_cm": round(usage, 2),
                    "block_remaining_cm": round(block_width - used, 2),
                })

        block_results.append({
            "block_name": block.get("name"),
            "block_width_cm": round(block_width, 2),
            "used_width_cm": round(used, 2),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejected": rejected,
        })

    shelf["products"] = rebuilt
    recalc_plan(next_plan)

    return {
        "status": "success",
        "planogram": next_plan,
        "block_results": block_results,
    }


def optimize_shelf(plan: Dict[str, Any], products: List[Dict[str, Any]], aisle_id: str, module_id: int, shelf_no: int) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)

    if not shelf:
        return {"status": "error", "message": "shelf_not_found", "planogram": next_plan}

    candidate_products = products or shelf.get("products", [])
    enriched = classify_products([enrich_product(p) for p in candidate_products])
    enriched.sort(key=product_score, reverse=True)

    shelf["products"] = []
    shelf["used_width_cm"] = 0
    shelf["used_weight_kg"] = 0
    shelf["used"] = 0

    accepted = []
    rejected = []

    for p in enriched:
        ok, reason = can_place(p, aisle, module, shelf, existing_groups_on_aisle(aisle))

        if not ok:
            rejected.append({"sku": sku(p), "product_name": product_name(p), "reason": reason})
            continue

        result = add_product_to_shelf(next_plan, p, aisle_id, module_id, shelf_no, force=False)
        if result["status"] == "success":
            accepted.append(result["product"])
            next_plan = result["planogram"]
            _, _, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)
        else:
            rejected.append({"sku": sku(p), "product_name": product_name(p), "reason": result.get("reason")})

    return {
        "status": "success",
        "planogram": next_plan,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected,
    }


def optimize_module(plan: Dict[str, Any], products: List[Dict[str, Any]], aisle_id: str, module_id: int) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    aisle, module, _ = find_shelf(next_plan, aisle_id, module_id, 1)

    if not module:
        return {"status": "error", "message": "module_not_found", "planogram": next_plan}

    for shelf in module.get("shelves", []):
        shelf["products"] = []
        shelf["used_width_cm"] = 0
        shelf["used_weight_kg"] = 0
        shelf["used"] = 0

    enriched = classify_products([enrich_product(p) for p in products])
    enriched.sort(key=product_score, reverse=True)

    accepted = []
    rejected = []

    for p in enriched:
        best = None
        best_score = -10**18

        for shelf in module.get("shelves", []):
            ok, reason = can_place(p, aisle, module, shelf, existing_groups_on_aisle(aisle))
            if not ok:
                continue

            sc = placement_score(p, aisle, module, shelf)
            if sc > best_score:
                best_score = sc
                best = shelf

        if not best:
            rejected.append({"sku": sku(p), "product_name": product_name(p), "reason": "no_fit_in_module"})
            continue

        result = add_product_to_shelf(next_plan, p, aisle_id, module_id, best.get("shelf_no"), force=False)
        if result["status"] == "success":
            accepted.append(result["product"])
            next_plan = result["planogram"]
            aisle, module, _ = find_shelf(next_plan, aisle_id, module_id, 1)
        else:
            rejected.append({"sku": sku(p), "product_name": product_name(p), "reason": result.get("reason")})

    return {
        "status": "success",
        "planogram": next_plan,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected,
    }


# =====================================================
# PICKING ROUTE
# =====================================================

def build_sku_location_map(plan: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    m = {}

    for aisle in plan.get("aisles", []):
        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                for p in shelf.get("products", []):
                    m[clean_text(p.get("sku"))] = {
                        "sku": p.get("sku"),
                        "product_name": p.get("product_name"),
                        "brand": p.get("brand"),
                        "storage_type": p.get("storage_type"),
                        "aisle_id": aisle.get("aisle_id"),
                        "row": aisle.get("row", 99),
                        "position": aisle.get("position", 99),
                        "direction": aisle.get("direction", "LTR"),
                        "zone_type": aisle.get("zone_type", "AMBIENT_ZONE"),
                        "module_id": module.get("module_id"),
                        "side": module.get("side", "L"),
                        "shelf_no": shelf.get("shelf_no"),
                        "route_order": route_score(aisle, module),
                    }

    return m


def optimize_picking_route(order_skus: List[str], plan: Dict[str, Any]) -> Dict[str, Any]:
    sku_map = build_sku_location_map(plan)
    found = []
    missing = []

    for raw in order_skus or []:
        s = clean_text(raw)
        if not s:
            continue
        if s in sku_map:
            found.append(sku_map[s])
        else:
            missing.append(s)

    ambient = [x for x in found if x["storage_type"] in ["AMBIENT", "PALLET"]]
    chilled = [x for x in found if x["storage_type"] == "CHILLED"]
    frozen = [x for x in found if x["storage_type"] == "FROZEN"]

    def sort_s(items):
        return sorted(items, key=lambda x: (num(x["row"], 99), num(x["position"], 99), num(x["route_order"], 9999)))

    route = sort_s(ambient) + sort_s(chilled) + sort_s(frozen)

    for i, x in enumerate(route):
        x["step"] = i + 1

    heatmap = {}
    for x in route:
        hkey = f"{x['aisle_id']}|{x['module_id']}|{x['storage_type']}"
        h = heatmap.setdefault(hkey, {
            "aisle_id": x["aisle_id"],
            "module_id": x["module_id"],
            "storage_type": x["storage_type"],
            "sku_count": 0,
            "route_pressure": 0,
            "skus": [],
        })
        h["sku_count"] += 1
        h["route_pressure"] += 1 + (1.5 if x["storage_type"] == "FROZEN" else 1 if x["storage_type"] == "CHILLED" else 0)
        h["skus"].append(x["sku"])

    travel_seconds = len(set(x["aisle_id"] for x in route)) * 8
    pick_seconds = len(route) * 12
    total_seconds = travel_seconds + pick_seconds

    return {
        "total_requested": len(order_skus or []),
        "found_count": len(found),
        "missing": missing,
        "route": route,
        "speed": {
            "travel_seconds": travel_seconds,
            "pick_seconds": pick_seconds,
            "total_seconds": total_seconds,
            "total_minutes": round(total_seconds / 60, 1),
            "avg_seconds_per_sku": round(total_seconds / max(len(route), 1)),
            "heatmap": sorted(heatmap.values(), key=lambda x: x["route_pressure"], reverse=True),
        },
        "strategy": "S-Pattern Dynamic: Ambient/Pallet → +4 Chilled → -18 Frozen.",
    }

# =====================================================
# BLACKBELT v22 — INSTANT SHELF PACKING OVERRIDE
# Purpose: return planogram fast (< seconds), pack shelves as blocks,
# avoid one-SKU-per-shelf behavior, enforce storage hard rules.
# =====================================================

BB_VERSION = "BLACKBELT_v22_INSTANT_SHELF_PACKING"


def _bb_storage(p: Dict[str, Any]) -> str:
    raw = key(f"{get(p, ['storage_type','Storage Type','Storage'], '')} {product_name(p)} {category_l1(p)} {category_l2(p)} {brand(p)}")
    if any(x in raw for x in ["FROZEN", "DONUK", "-18", "DONDUR", "DONDURMA", "ICE CREAM", "FREEZER", "ALGIDA", "LA LORRAINE"]):
        return "FROZEN"
    if any(x in raw for x in ["CHILLED", "COLD", "+4", "SÜT", "SUT", "DAIRY", "YOĞURT", "YOGURT", "PEYNIR", "PEYNİR", "SUSHI", "SALMON", "SOMON", "FRIDGE"]):
        return "CHILLED"
    return "AMBIENT"


def _bb_all_shelves(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for aisle in plan.get("aisles", []):
        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                rows.append({"aisle": aisle, "module": module, "shelf": shelf})
    return rows


def _bb_repair_dimensions(p: Dict[str, Any]) -> Dict[str, Any]:
    x = dict(p)
    w, h, d = num(x.get("width_cm"), 0), num(x.get("height_cm"), 0), num(x.get("depth_cm"), 0)
    dirty = (w <= 2 or h <= 2 or d <= 2 or w > 80 or h > 90 or d > 90)
    if dirty:
        est = ai_estimate_dimensions(x)
        x["width_cm"] = est.get("width_cm", 10)
        x["height_cm"] = est.get("height_cm", 20)
        x["depth_cm"] = est.get("depth_cm", 10)
        x["weight_kg"] = max(0.01, num(x.get("weight_kg"), est.get("weight_kg", 0.2)))
        x["dimension_source"] = "rejected_dirty_dimension_ai_fallback"
        x["dimension_confidence"] = min(num(est.get("confidence"), 0.45), 0.75)
        x["dimension_reason"] = f"dirty_dimension_rejected__{est.get('reason','generic')}"
    else:
        x["width_cm"] = max(3, w)
        x["height_cm"] = max(3, h)
        x["depth_cm"] = max(2, d)
    x["storage_type"] = _bb_storage(x)
    x["_storage"] = x["storage_type"]
    x["_merch_group"] = merch_group(x)
    x["image"] = image_url(x)
    x["product_image_url"] = image_url(x)
    return x


def _bb_daily_sales(p: Dict[str, Any]) -> float:
    return max(0.0, num(get(p, ["daily_sales", "avg_daily_sales"], 0), 0) or sales_7d(p) / 7.0)


def _bb_score_raw(p: Dict[str, Any]) -> float:
    return sales_7d(p) * 4.0 + percent_stops(p) * 15.0 + _bb_daily_sales(p) * 12.0 + on_hand(p) * 0.01


def _bb_assign_abc(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(products, key=_bb_score_raw, reverse=True)
    n = max(len(ranked), 1)
    for i, p in enumerate(ranked):
        r = i / n
        if r <= 0.15:
            p["_abc"] = "A"; p["_tier"] = "HOT" if r <= 0.06 else "FAST"
        elif r <= 0.50:
            p["_abc"] = "B"; p["_tier"] = "MID"
        elif r <= 0.90:
            p["_abc"] = "C"; p["_tier"] = "BACK"
        else:
            p["_abc"] = "D"; p["_tier"] = "TAIL"
        p["_score"] = _bb_score_raw(p)
    return ranked


def _bb_target_coverage_days(p: Dict[str, Any]) -> float:
    abc = key(p.get("_abc"))
    if abc == "A": return 0.45
    if abc == "B": return 0.85
    if abc == "C": return 1.50
    return 3.00


def _bb_depth_units(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    return max(1, int(num(shelf.get("shelf_depth_cm"), 50) // max(num(p.get("depth_cm"), 10), 1)))


def _bb_facing_options(p: Dict[str, Any], shelf: Dict[str, Any]) -> List[int]:
    du = _bb_depth_units(p, shelf)
    daily = _bb_daily_sales(p)
    target_units = max(1, daily * _bb_target_coverage_days(p))
    optimal = int(math.ceil(target_units / max(du, 1)))
    if p.get("_abc") == "A":
        optimal = max(optimal, 3)
    elif p.get("_abc") == "B":
        optimal = max(optimal, 2)
    max_by_width = max(1, int(num(shelf.get("shelf_width_cm"), 100) // max(num(p.get("width_cm"), 10) * 1.08, 1)))
    max_cap = 12 if p.get("_abc") == "A" else 8
    optimal = max(1, min(max_cap, max_by_width, optimal))
    return list(range(optimal, 0, -1))


def _bb_used_width_for(p: Dict[str, Any], facing: int) -> float:
    return round(max(3, num(p.get("width_cm"), 10)) * max(1, facing) * 1.08, 2)


def _bb_is_nonfood(p: Dict[str, Any]) -> bool:
    return str(p.get("_merch_group") or merch_group(p)).startswith("NON_FOOD")


def _bb_is_food(p: Dict[str, Any]) -> bool:
    return str(p.get("_merch_group") or merch_group(p)).startswith("FOOD")


def _bb_shelf_products(shelf: Dict[str, Any]) -> List[Dict[str, Any]]:
    return shelf.get("products", []) or []


def _bb_signature_of_shelf(shelf: Dict[str, Any]) -> Dict[str, str]:
    ps = _bb_shelf_products(shelf)
    if not ps:
        return {"storage": shelf_storage(shelf), "merch": "", "cat1": "", "cat2": "", "brand": ""}
    f = ps[0]
    return {
        "storage": key(f.get("storage_type")),
        "merch": key(f.get("merch_group") or f.get("_merch_group")),
        "cat1": key(f.get("category_l1")),
        "cat2": key(f.get("category_l2")),
        "brand": key(f.get("brand")),
    }


def _bb_mix_allowed(p: Dict[str, Any], shelf: Dict[str, Any]) -> bool:
    if shelf_storage(shelf) != key(p.get("_storage") or p.get("storage_type")):
        return False
    ps = _bb_shelf_products(shelf)
    if not ps:
        return True
    if _bb_is_food(p) and any(str(x.get("merch_group") or x.get("_merch_group", "")).startswith("NON_FOOD") for x in ps):
        return False
    if _bb_is_nonfood(p) and any(str(x.get("merch_group") or x.get("_merch_group", "")).startswith("FOOD") for x in ps):
        return False
    sig = _bb_signature_of_shelf(shelf)
    if sig["cat2"] and sig["cat2"] == key(category_l2(p)):
        return True
    if sig["brand"] and sig["brand"] == key(brand(p)):
        return True
    if sig["merch"] and sig["merch"] == key(p.get("_merch_group")) and len(ps) < 5:
        return True
    return False


def _bb_target_max_util(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    st = key(p.get("_storage"))
    if st == "FROZEN": return 0.84
    if st == "CHILLED": return 0.86
    if p.get("_abc") == "A": return 0.92
    return 0.88


def _bb_zone_score(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    z = key(shelf.get("zone_type"))
    abc = key(p.get("_abc"))
    wt = weight(p)
    if wt >= 3:
        return 220 if z == "BOTTOM" else -300 if z in ["TOP", "EYE"] else 20
    if abc == "A":
        return 260 if z == "EYE" else 120 if z == "MID" else -180 if z == "TOP" else 10
    if abc == "B":
        return 140 if z in ["EYE", "MID"] else 30
    if abc == "D":
        return 80 if z in ["TOP", "BOTTOM"] else -80 if z == "EYE" else 20
    return 40


def _bb_shelf_candidate_score(p: Dict[str, Any], aisle: Dict[str, Any], module: Dict[str, Any], shelf: Dict[str, Any], facing: int) -> float:
    ps = _bb_shelf_products(shelf)
    used = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    sw = num(shelf.get("shelf_width_cm"), 100)
    after = (used + _bb_used_width_for(p, facing)) / max(sw, 1)
    sig = _bb_signature_of_shelf(shelf)
    score = 0.0
    if ps:
        score += 600
        if sig["brand"] == key(brand(p)): score += 420
        if sig["cat2"] == key(category_l2(p)): score += 340
        if sig["cat1"] == key(category_l1(p)): score += 160
        if sig["merch"] == key(p.get("_merch_group")): score += 140
    else:
        score -= 420
    target = _bb_target_max_util(p, shelf)
    if 0.68 <= after <= target:
        score += 260
    elif 0.45 <= after < 0.68:
        score += 120
    elif after < 0.35:
        score -= 220
    elif after > target:
        score -= 300 * (after - target) * 10
    score += _bb_zone_score(p, shelf)
    score += facing * 18
    score += max(0, 160 - route_score(aisle, module) * 0.6)
    aid = key(aisle.get("aisle_id"))
    if p.get("_abc") == "A" and aid in ["A", "B", "C", "D"]: score += 120
    if p.get("_abc") in ["C", "D"] and aid in ["A", "B"]: score -= 120
    if _bb_is_nonfood(p) and aid in ["A", "B"]: score -= 300
    return score


def _bb_fits(p: Dict[str, Any], shelf: Dict[str, Any], facing: int, allow_high_util: bool = False) -> bool:
    if shelf_storage(shelf) != key(p.get("_storage") or p.get("storage_type")):
        return False
    if num(p.get("height_cm"), 20) > num(shelf.get("shelf_height_cm"), 35):
        return False
    if num(p.get("depth_cm"), 10) > num(shelf.get("shelf_depth_cm"), 50):
        return False
    used = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    sw = num(shelf.get("shelf_width_cm"), 100)
    after = used + _bb_used_width_for(p, facing)
    if after > sw:
        return False
    target = _bb_target_max_util(p, shelf)
    if not allow_high_util and after / max(sw, 1) > target:
        return False
    if num(shelf.get("used_weight_kg"), 0) + weight(p) * facing > num(shelf.get("max_weight_kg"), 45):
        return False
    return True


def _bb_make_placed(p: Dict[str, Any], aisle: Dict[str, Any], module: Dict[str, Any], shelf: Dict[str, Any], facing: int, score: float) -> Dict[str, Any]:
    du = _bb_depth_units(p, shelf)
    cap = du * facing
    daily = _bb_daily_sales(p)
    refill_per_day = round(daily / max(cap, 1), 2) if daily > 0 else 0
    return {
        "sku": sku(p), "barcode": clean_text(get(p, ["barcode", "product_barcodes"], "")),
        "product_name": product_name(p), "brand": brand(p), "brand_name": brand(p),
        "category_l1": category_l1(p), "category_l2": category_l2(p),
        "frontend_category_local": category_l1(p), "frontend_subcategory_local": category_l2(p),
        "image_url": image_url(p), "image": image_url(p), "product_image_url": image_url(p),
        "storage_type": p.get("_storage"), "merch_group": p.get("_merch_group"),
        "abc_class": p.get("_abc"), "tier": p.get("_tier"), "front_tier": p.get("_tier"),
        "sales_qty_7d": sales_7d(p), "daily_sales": round(daily, 3), "percent_stops": percent_stops(p), "on_hand_qty": on_hand(p),
        "width_cm": num(p.get("width_cm"), 10), "height_cm": num(p.get("height_cm"), 20), "depth_cm": num(p.get("depth_cm"), 10),
        "weight_kg": weight(p), "case_pack_qty": case_pack(p),
        "facing": facing, "facing_count": facing, "used_width_cm": _bb_used_width_for(p, facing),
        "depth_units": du, "total_capacity_units": cap,
        "coverage_days": round(cap / max(daily, 0.01), 1) if daily > 0 else None,
        "refill_per_day": refill_per_day,
        "dimension_source": p.get("dimension_source"), "dimension_confidence": p.get("dimension_confidence"), "dimension_reason": p.get("dimension_reason"),
        "aisle": aisle.get("aisle_id"), "aisle_id": aisle.get("aisle_id"), "module_id": module.get("module_id"), "shelf_no": shelf.get("shelf_no"),
        "position_order": len(shelf.get("products", [])) + 1, "placement_score": round(score, 1),
        "explanation": "Packed by storage/category/brand block; facing based on velocity/refill; golden-zone and capacity constraints applied.",
    }


def _bb_apply_place(placed: Dict[str, Any], shelf: Dict[str, Any]) -> None:
    shelf.setdefault("products", []).append(placed)
    shelf["used_width_cm"] = round(num(shelf.get("used_width_cm", shelf.get("used", 0)), 0) + num(placed.get("used_width_cm"), 0), 1)
    shelf["used"] = shelf["used_width_cm"]
    shelf["used_weight_kg"] = round(num(shelf.get("used_weight_kg"), 0) + num(placed.get("weight_kg"), 0) * inum(placed.get("facing_count"), 1), 2)


def _bb_try_place_product(p: Dict[str, Any], shelf_rows: List[Dict[str, Any]]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    storage = key(p.get("_storage"))
    same_storage = [r for r in shelf_rows if shelf_storage(r["shelf"]) == storage]
    if not same_storage:
        return False, None, f"no_{storage}_fixture"
    passes = [
        [r for r in same_storage if _bb_shelf_products(r["shelf"]) and _bb_mix_allowed(p, r["shelf"])],
        [r for r in same_storage if not _bb_shelf_products(r["shelf"])],
        [r for r in same_storage if _bb_mix_allowed(p, r["shelf"])],
    ]
    allow_flags = [False, False, True]
    best = None; best_score = -10**18; best_facing = 1; last_reason = "no_fit"
    for pass_idx, candidates in enumerate(passes):
        candidates = sorted(candidates, key=lambda r: (
            0 if _bb_shelf_products(r["shelf"]) else 1,
            abs((num(r["shelf"].get("used_width_cm"), 0) / max(num(r["shelf"].get("shelf_width_cm"), 100), 1)) - 0.65),
            route_score(r["aisle"], r["module"]),
        ))[:80]
        for r in candidates:
            shelf = r["shelf"]
            if not _bb_mix_allowed(p, shelf):
                last_reason = "block_not_compatible"; continue
            for facing in _bb_facing_options(p, shelf):
                if not _bb_fits(p, shelf, facing, allow_high_util=allow_flags[pass_idx]):
                    last_reason = "capacity_dimension_or_weight_not_fit"; continue
                sc = _bb_shelf_candidate_score(p, r["aisle"], r["module"], shelf, facing)
                if sc > best_score:
                    best = r; best_score = sc; best_facing = facing
        if best is not None:
            break
    if best is None:
        return False, None, last_reason
    placed = _bb_make_placed(p, best["aisle"], best["module"], best["shelf"], best_facing, best_score)
    _bb_apply_place(placed, best["shelf"])
    return True, placed, "ok"


def _bb_repack_low_fill(plan: Dict[str, Any]) -> Dict[str, Any]:
    rows = _bb_all_shelves(plan)
    for src in list(rows):
        shelf = src["shelf"]
        ps = list(_bb_shelf_products(shelf))
        sw = num(shelf.get("shelf_width_cm"), 100)
        util = num(shelf.get("used_width_cm", 0), 0) / max(sw, 1)
        if len(ps) != 1 or util >= 0.45:
            continue
        p0 = ps[0]
        best = None; best_score = -10**18
        for dst in rows:
            if dst is src:
                continue
            ds = dst["shelf"]
            if not _bb_shelf_products(ds):
                continue
            fake = {**p0, "_storage": p0.get("storage_type"), "_merch_group": p0.get("merch_group"), "_abc": p0.get("abc_class"), "_tier": p0.get("tier")}
            if not _bb_mix_allowed(fake, ds):
                continue
            facing = inum(p0.get("facing_count", p0.get("facing", 1)), 1)
            if not _bb_fits(fake, ds, facing, allow_high_util=True):
                continue
            sc = _bb_shelf_candidate_score(fake, dst["aisle"], dst["module"], ds, facing)
            if sc > best_score:
                best = dst; best_score = sc
        if best:
            shelf["products"] = []
            shelf["used_width_cm"] = 0; shelf["used"] = 0; shelf["used_weight_kg"] = 0
            p0["aisle"] = best["aisle"].get("aisle_id"); p0["aisle_id"] = best["aisle"].get("aisle_id")
            p0["module_id"] = best["module"].get("module_id"); p0["shelf_no"] = best["shelf"].get("shelf_no")
            p0["position_order"] = len(best["shelf"].get("products", [])) + 1
            _bb_apply_place(p0, best["shelf"])
    return recalc_plan(plan)


def _bb_summarize(plan: Dict[str, Any], total_products: int, unplaced: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_width = used_width_v = 0.0
    low = 0; single_low = 0; over = 0; capacity_warnings = []
    for r in _bb_all_shelves(plan):
        a,m,s = r["aisle"], r["module"], r["shelf"]
        sw = num(s.get("shelf_width_cm"), 100); su = num(s.get("used_width_cm", s.get("used", 0)), 0)
        total_width += sw; used_width_v += su
        util = su / max(sw, 1); pc = len(s.get("products", []))
        if util > 1: over += 1
        if pc and util < 0.35: low += 1
        if pc == 1 and util < 0.60: single_low += 1
        if util >= 0.90:
            capacity_warnings.append({"aisle": a.get("aisle_id"), "module_id": m.get("module_id"), "shelf_no": s.get("shelf_no"), "utilization_pct": round(util*100)})
    placed = total_products - len(unplaced)
    return {
        "total": total_products, "placed": placed, "unplaced": len(unplaced),
        "total_products": total_products, "placed_products": placed, "unplaced_products": len(unplaced),
        "capacity_utilization_pct": round((used_width_v / max(total_width, 1)) * 100, 2),
        "low_fill_shelf_count": low, "single_sku_low_fill_shelf_count": single_low, "overfilled_shelf_count": over,
        "capacity_warnings": capacity_warnings, "strategy": BB_VERSION,
        "target": "Block shelves to 70-88% where possible; storage hard rules; golden-zone ABC; refill-facing; repack low-fill shelves.",
    }


def generate_planogram(products: List[Dict[str, Any]], layout: Optional[Dict[str, Any]], mode: str = "HYBRID", brand_side_rules: Optional[Dict[str, str]] = None, scoring_config: Optional[Dict[str, float]] = None, allow_ai_dimensions: bool = True) -> Dict[str, Any]:
    raw_products = products or []
    plan = prepare_layout(layout or generate_default_layout())
    MAX_PRODUCTS = 15000
    raw_products = sorted(raw_products, key=lambda x: (-num(get(x, ["sales_qty_7d", "sales_7d", "sales"], 0), 0), -num(get(x, ["percent_stops", "% Stops"], 0), 0)))[:MAX_PRODUCTS]
    clean_products: List[Dict[str, Any]] = []
    unplaced: List[Dict[str, Any]] = []
    alerts = {"approval_fire_products": [], "dimension_repaired": [], "storage_leak_prevented": [], "low_coverage": []}
    for raw in raw_products:
        p = enrich_product(raw, allow_ai_dimensions=allow_ai_dimensions)
        p = _bb_repair_dimensions(p)
        if is_approval(p):
            item = {"sku": sku(p), "product_name": product_name(p), "reason": "approval_area_fire_stock"}
            unplaced.append(item); alerts["approval_fire_products"].append(item); continue
        if not sku(p):
            unplaced.append({"sku": None, "product_name": product_name(p), "reason": "missing_sku"}); continue
        if str(p.get("dimension_source")) == "rejected_dirty_dimension_ai_fallback":
            alerts["dimension_repaired"].append({"sku": sku(p), "product_name": product_name(p), "new": [p.get("width_cm"), p.get("height_cm"), p.get("depth_cm")]})
        clean_products.append(p)
    ranked = _bb_assign_abc(clean_products)
    ranked.sort(key=lambda p: ({"CHILLED": 0, "FROZEN": 1, "AMBIENT": 2}.get(key(p.get("_storage")), 9), key(p.get("_merch_group")), key(category_l1(p)), key(category_l2(p)), key(brand(p)), {"A": 0, "B": 1, "C": 2, "D": 3}.get(key(p.get("_abc")), 9), -_bb_score_raw(p)))
    shelf_rows = _bb_all_shelves(plan)
    for p in ranked:
        ok, placed, reason = _bb_try_place_product(p, shelf_rows)
        if not ok:
            if p.get("_storage") in ["CHILLED", "FROZEN"] and reason.startswith("no_"):
                alerts["storage_leak_prevented"].append({"sku": sku(p), "product_name": product_name(p), "storage_type": p.get("_storage"), "reason": reason})
            unplaced.append({"sku": sku(p), "product_name": product_name(p), "brand": brand(p), "category_l1": category_l1(p), "category_l2": category_l2(p), "storage_type": p.get("_storage"), "reason": reason, "suggested_action": "Add matching fixture/storage capacity or verify dimensions/facing rules."})
        elif placed and placed.get("coverage_days") is not None and placed.get("coverage_days") < 0.25:
            alerts["low_coverage"].append({"sku": placed.get("sku"), "product_name": placed.get("product_name"), "coverage_days": placed.get("coverage_days"), "refill_per_day": placed.get("refill_per_day")})
    plan = _bb_repack_low_fill(plan)
    summary = _bb_summarize(plan, len(raw_products), unplaced)
    diagnostics = validate_planogram(plan)
    return {
        "summary": summary, "planogram": plan, "unplaced": unplaced, "unplaced_products": unplaced, "alerts": alerts, "diagnostics": diagnostics,
        "engine_version": BB_VERSION,
        "insights": {
            "blackbelt_logic": "Products are clustered by storage → merch group → category → brand, then packed into compatible shelves before opening new shelves.",
            "packing_logic": "Empty shelf opening is penalized; compatible partially-filled shelves are rewarded to prevent one-SKU-per-shelf layouts.",
            "facing_logic": "Facing is calculated from daily sales, target coverage, shelf depth capacity and ABC class.",
            "golden_zone_logic": "A/B velocity products are biased to golden/mid shelves; heavy products are biased lower.",
            "storage_logic": "CHILLED and FROZEN products are never allowed to leak into AMBIENT shelves.",
            "speed_mode": "This endpoint is intentionally synchronous-fast; deeper ML/simulation should run after first render, not block the user.",
        },
        "recommended_actions": ["If CHILLED/FROZEN unplaced appears, add +4/-18 modules or verify storage_type in master data.", "If capacity utilization stays below target, reduce module count or increase assortment per shelf via category blocks.", "Use diagnostics.single_sku_low_fill_shelf_count to catch planogram graveyard shelves."],
        "optimized": True,
    }


def run_engine(products: List[Dict[str, Any]], layout: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    return generate_planogram(products, layout, **kwargs)

# =====================================================
# BLACKBELT v23 — TURBO 10K SYNC OVERRIDE
# Purpose: do not block UI with deep per-SKU candidate scoring.
# Processes up to 10k SKU using shelf-block indexes and O(N * small-candidate) placement.
# =====================================================

BB_VERSION = "BLACKBELT_v23_TURBO_10K_SHELF_PACKING"


def _turbo_block_keys(p: Dict[str, Any]) -> List[str]:
    st = key(p.get("_storage") or p.get("storage_type"))
    merch = key(p.get("_merch_group") or merch_group(p))
    c1 = key(category_l1(p))
    c2 = key(category_l2(p))
    b = key(brand(p))
    return [
        f"{st}|{merch}|{c1}|{c2}|{b}",
        f"{st}|{merch}|{c1}|{c2}|*",
        f"{st}|{merch}|{c1}|*|*",
        f"{st}|{merch}|*|*|*",
    ]


def _turbo_zone_pref(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    z = key(shelf.get("zone_type"))
    abc = key(p.get("_abc"))
    wt = weight(p)
    if wt >= 3:
        return 260 if z == "BOTTOM" else -400 if z in ["TOP", "EYE"] else 40
    if abc == "A":
        return 260 if z == "EYE" else 150 if z == "MID" else -180 if z == "TOP" else 20
    if abc == "B":
        return 180 if z in ["EYE", "MID"] else 60
    if abc == "D":
        return 90 if z in ["TOP", "BOTTOM"] else -80 if z == "EYE" else 20
    return 50


def _turbo_facing_options(p: Dict[str, Any], shelf: Dict[str, Any]) -> List[int]:
    # Speed-critical: try only 3 options, not every facing down to 1.
    base = _bb_facing_options(p, shelf)
    if not base:
        return [1]
    opts = []
    for v in [base[0], max(1, min(base[0] - 1, 4)), 1]:
        if v not in opts:
            opts.append(v)
    return opts


def _turbo_candidate_score(p: Dict[str, Any], row: Dict[str, Any], facing: int) -> float:
    shelf = row["shelf"]
    ps = _bb_shelf_products(shelf)
    used = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    sw = num(shelf.get("shelf_width_cm"), 100)
    after = (used + _bb_used_width_for(p, facing)) / max(sw, 1)
    sig = _bb_signature_of_shelf(shelf)
    score = 0.0
    if ps:
        score += 800
        if sig["brand"] == key(brand(p)):
            score += 420
        if sig["cat2"] == key(category_l2(p)):
            score += 360
        if sig["cat1"] == key(category_l1(p)):
            score += 180
        if sig["merch"] == key(p.get("_merch_group")):
            score += 140
    else:
        score -= 350
    if 0.62 <= after <= _bb_target_max_util(p, shelf):
        score += 320
    elif 0.40 <= after < 0.62:
        score += 110
    elif after < 0.30:
        score -= 160
    else:
        score -= 220
    score += _turbo_zone_pref(p, shelf)
    score += facing * 12
    score += max(0, 120 - route_score(row["aisle"], row["module"]) * 0.55)
    return score


def _turbo_try_rows(p: Dict[str, Any], rows: List[Dict[str, Any]], allow_high_util: bool = False) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    best = None
    best_facing = 1
    best_score = -10**18
    last_reason = "no_fit"
    for row in rows:
        shelf = row["shelf"]
        if shelf_storage(shelf) != key(p.get("_storage") or p.get("storage_type")):
            last_reason = "storage_not_fit"
            continue
        if not _bb_mix_allowed(p, shelf):
            last_reason = "block_not_compatible"
            continue
        for facing in _turbo_facing_options(p, shelf):
            if not _bb_fits(p, shelf, facing, allow_high_util=allow_high_util):
                last_reason = "capacity_dimension_or_weight_not_fit"
                continue
            score = _turbo_candidate_score(p, row, facing)
            if score > best_score:
                best = row
                best_facing = facing
                best_score = score
    if not best:
        return False, None, last_reason
    placed = _bb_make_placed(p, best["aisle"], best["module"], best["shelf"], best_facing, best_score)
    _bb_apply_place(placed, best["shelf"])
    return True, placed, "ok"


def _turbo_register_shelf(block_index: Dict[str, List[Dict[str, Any]]], p: Dict[str, Any], row: Dict[str, Any]) -> None:
    for k in _turbo_block_keys(p):
        lst = block_index.setdefault(k, [])
        if row not in lst:
            lst.append(row)
            # Keep only recent/active shelves to avoid candidate explosion.
            if len(lst) > 10:
                del lst[:-10]


def _turbo_shelf_snapshot(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _bb_all_shelves(plan)
    # Stable route order. Empty shelf selection later uses this list.
    rows.sort(key=lambda r: (shelf_storage(r["shelf"]), route_score(r["aisle"], r["module"]), num(r["shelf"].get("shelf_no"), 99)))
    return rows


def _turbo_place_product(
    p: Dict[str, Any],
    storage_rows: Dict[str, List[Dict[str, Any]]],
    block_index: Dict[str, List[Dict[str, Any]]],
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    st = key(p.get("_storage") or p.get("storage_type"))
    rows = storage_rows.get(st, [])
    if not rows:
        return False, None, f"no_{st}_fixture"

    # 1) Existing compatible block shelves. This prevents one-SKU-per-shelf.
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for bk in _turbo_block_keys(p):
        for r in reversed(block_index.get(bk, [])):
            rid = (id(r["shelf"]), id(r["module"]), id(r["aisle"]))
            if rid not in seen:
                candidates.append(r)
                seen.add(rid)
        if len(candidates) >= 18:
            break
    if candidates:
        ok, placed, reason = _turbo_try_rows(p, candidates[:24], allow_high_util=False)
        if ok:
            # Find actual row object from candidate shelf and register.
            for r in candidates:
                if r["shelf"] is not None and placed and r["shelf"].get("products") and r["shelf"].get("products")[-1].get("sku") == placed.get("sku"):
                    _turbo_register_shelf(block_index, p, r)
                    break
            return ok, placed, reason

    # 2) Open best empty shelf. Empty shelves are allowed but penalized/scored.
    empty = [r for r in rows if not _bb_shelf_products(r["shelf"])]
    if empty:
        # limit keeps it fast even in huge layouts
        empty = sorted(empty[:120], key=lambda r: (-_turbo_zone_pref(p, r["shelf"]), route_score(r["aisle"], r["module"])))[:24]
        ok, placed, reason = _turbo_try_rows(p, empty, allow_high_util=False)
        if ok:
            for r in empty:
                if r["shelf"].get("products") and r["shelf"].get("products")[-1].get("sku") == placed.get("sku"):
                    _turbo_register_shelf(block_index, p, r)
                    break
            return ok, placed, reason

    # 3) Last chance: any compatible shelf with capacity, allow slightly higher utilization.
    partial = [r for r in rows if _bb_shelf_products(r["shelf"])]
    partial = sorted(partial[:160], key=lambda r: abs((num(r["shelf"].get("used_width_cm", 0), 0) / max(num(r["shelf"].get("shelf_width_cm"), 100), 1)) - 0.72))[:32]
    ok, placed, reason = _turbo_try_rows(p, partial, allow_high_util=True)
    if ok:
        for r in partial:
            if r["shelf"].get("products") and r["shelf"].get("products")[-1].get("sku") == placed.get("sku"):
                _turbo_register_shelf(block_index, p, r)
                break
        return ok, placed, reason

    return False, None, reason


def generate_planogram(products: List[Dict[str, Any]], layout: Optional[Dict[str, Any]], mode: str = "HYBRID", brand_side_rules: Optional[Dict[str, str]] = None, scoring_config: Optional[Dict[str, float]] = None, allow_ai_dimensions: bool = True) -> Dict[str, Any]:
    import time
    start = time.time()
    raw_input_count = len(products or [])
    plan = prepare_layout(layout or generate_default_layout())

    # Synchronous UI cannot run a deep 10k x candidate optimizer.
    # This is the production rule: instant render first; deep simulation later.
    max_sync = int(os.getenv("PLONAGRAM_MAX_SYNC_PRODUCTS", "10000"))
    raw_products = sorted(
        products or [],
        key=lambda x: (
            -num(get(x, ["sales_qty_7d", "sales_7d", "sales"], 0), 0),
            -num(get(x, ["percent_stops", "% Stops"], 0), 0),
        )
    )[:max_sync]

    clean_products: List[Dict[str, Any]] = []
    unplaced: List[Dict[str, Any]] = []
    alerts = {"approval_fire_products": [], "dimension_repaired": [], "storage_leak_prevented": [], "low_coverage": [], "deferred_products": []}

    for raw in raw_products:
        p = enrich_product(raw, allow_ai_dimensions=allow_ai_dimensions)
        p = _bb_repair_dimensions(p)
        if is_approval(p):
            item = {"sku": sku(p), "product_name": product_name(p), "reason": "approval_area_fire_stock"}
            unplaced.append(item)
            alerts["approval_fire_products"].append(item)
            continue
        if not sku(p):
            unplaced.append({"sku": None, "product_name": product_name(p), "reason": "missing_sku"})
            continue
        if str(p.get("dimension_source")) == "rejected_dirty_dimension_ai_fallback":
            alerts["dimension_repaired"].append({"sku": sku(p), "product_name": product_name(p), "new": [p.get("width_cm"), p.get("height_cm"), p.get("depth_cm")]})
        clean_products.append(p)

    ranked = _bb_assign_abc(clean_products)
    ranked.sort(key=lambda p: (
        {"CHILLED": 0, "FROZEN": 1, "AMBIENT": 2}.get(key(p.get("_storage")), 9),
        key(p.get("_merch_group")), key(category_l1(p)), key(category_l2(p)), key(brand(p)),
        {"A": 0, "B": 1, "C": 2, "D": 3}.get(key(p.get("_abc")), 9),
        -_bb_score_raw(p)
    ))

    shelf_rows = _turbo_shelf_snapshot(plan)
    storage_rows: Dict[str, List[Dict[str, Any]]] = {}
    for r in shelf_rows:
        storage_rows.setdefault(shelf_storage(r["shelf"]), []).append(r)

    block_index: Dict[str, List[Dict[str, Any]]] = {}

    for p in ranked:
        ok, placed, reason = _turbo_place_product(p, storage_rows, block_index)
        if not ok:
            if p.get("_storage") in ["CHILLED", "FROZEN"] and str(reason).startswith("no_"):
                alerts["storage_leak_prevented"].append({"sku": sku(p), "product_name": product_name(p), "storage_type": p.get("_storage"), "reason": reason})
            unplaced.append({
                "sku": sku(p), "product_name": product_name(p), "brand": brand(p),
                "category_l1": category_l1(p), "category_l2": category_l2(p),
                "storage_type": p.get("_storage"), "reason": reason,
                "suggested_action": "Add matching fixture/storage capacity or verify dimensions/facing rules."
            })
        elif placed and placed.get("coverage_days") is not None and placed.get("coverage_days") < 0.25:
            alerts["low_coverage"].append({"sku": placed.get("sku"), "product_name": placed.get("product_name"), "coverage_days": placed.get("coverage_days"), "refill_per_day": placed.get("refill_per_day")})

    # Only repack if size is moderate. For 7k/10k, repack can be a background job.
    if len(ranked) <= 2500:
        plan = _bb_repack_low_fill(plan)
    else:
        recalc_plan(plan)

    summary = _bb_summarize(plan, len(raw_products), unplaced)
    summary["raw_input_products"] = raw_input_count
    summary["sync_processed_products"] = len(raw_products)
    summary["deferred_products"] = max(0, raw_input_count - len(raw_products))
    summary["runtime_sec"] = round(time.time() - start, 2)
    summary["performance_mode"] = "TURBO_10K_SYNC_FIRST_RENDER"
    summary["deep_repack_skipped"] = len(ranked) > 2500

    diagnostics = validate_planogram(plan)
    return {
        "summary": summary,
        "planogram": plan,
        "unplaced": unplaced,
        "unplaced_products": unplaced,
        "alerts": alerts,
        "diagnostics": diagnostics,
        "engine_version": BB_VERSION,
        "insights": {
            "turbo_logic": "First render uses indexed shelf blocks instead of deep SKU×candidate scoring, so 7k-10k SKU does not block the UI.",
            "packing_logic": "Existing compatible category/brand/merch shelves are tried before opening a new shelf.",
            "background_logic": "Deep repack/simulation should run after first render; it is intentionally skipped for very large assortments.",
            "storage_logic": "CHILLED and FROZEN products are never allowed to leak into AMBIENT shelves.",
        },
        "recommended_actions": [
            "For 7k-10k SKU, keep first render under seconds and move deep simulation to a background endpoint.",
            "Use summary.deep_repack_skipped to show 'Deep analysis queued' in frontend instead of blocking the user.",
            "If deferred_products > 0, increase PLONAGRAM_MAX_SYNC_PRODUCTS or run background optimization."
        ],
        "optimized": True,
    }


def run_engine(products: List[Dict[str, Any]], layout: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    return generate_planogram(products, layout, **kwargs)


# =====================================================
# BLACKBELT v24 — STOCKING PHYSICS OVERRIDE
# Purpose:
# - Shelf capacity = front facings × same-SKU depth × stack layers.
# - Different SKU behind front face is not allowed by default.
# - Case pack / stackability / crush risk / reserve depth are explicit.
# - Water/bulk/produce/fridge reality is surfaced through behavior fields.
# =====================================================

BB_VERSION = "BLACKBELT_v24_STOCKING_PHYSICS_SAME_SKU_DEPTH"


def _sp_raw_text(p: Dict[str, Any]) -> str:
    return norm(
        f"{product_name(p)} {brand(p)} {category_l1(p)} {category_l2(p)} "
        f"{get(p, ['category_l3', 'frontend_category_local', 'frontend_subcategory_local'], '')} "
        f"{get(p, ['package_type', 'stocking_behavior'], '')}"
    )


def _sp_package_type(p: Dict[str, Any]) -> str:
    explicit = norm(get(p, ["package_type", "packaging_type", "package"], ""))
    if explicit:
        return explicit

    raw = _sp_raw_text(p)

    if any(x in raw for x in ["damacana", "19 l", "19l"]):
        return "demijohn"
    if any(x in raw for x in ["6x", "6 x", "12x", "12 x", "24x", "24 x", "koli", "case", "multipack", "multi pack", "shrink"]):
        return "multipack"
    if any(x in raw for x in ["cips", "chips", "lays", "ruffles", "doritos", "popcorn", "patlamis", "patlamış"]):
        return "bag"
    if any(x in raw for x in ["cikolata", "çikolata", "gofret", "wafer", "bar"]):
        return "bar"
    if any(x in raw for x in ["makarna", "pirinc", "pirinç", "bulgur", "un ", "seker", "şeker", "bakliyat"]):
        return "pouch_or_bag"
    if any(x in raw for x in ["kavanoz", "zeytin", "tursu", "turşu", "recel", "reçel", "sos", "salca", "salça", "jar"]):
        return "jar"
    if any(x in raw for x in ["sut", "süt", "meyve suyu", "juice", "uht", "carton"]):
        return "carton"
    if any(x in raw for x in ["sise", "şişe", "cola", "kola", "fanta", "sprite", "water", "su ", "içecek", "icecek"]):
        return "bottle"
    if any(x in raw for x in ["konserve", "can", "teneke"]):
        return "can"
    if any(x in raw for x in ["yumurta", "egg"]):
        return "egg_tray"
    if any(x in raw for x in ["muz", "karpuz", "patates", "sogan", "soğan", "domates", "salatalik", "salatalık"]):
        return "produce_crate"
    if any(x in raw for x in ["dis fircasi", "diş fırçası", "toothbrush", "askili", "asılı", "hanging"]):
        return "hanging"
    if any(x in raw for x in ["deterjan", "sampuan", "şampuan", "yumusatici", "yumuşatıcı", "domestos", "temizleyici"]):
        return "bottle"
    return "unknown"


def _sp_weight_kg(p: Dict[str, Any]) -> float:
    raw_w = num(get(p, ["weight_kg", "final_weight_kg", "Weight", "agirlik", "product_weight_value"], 0.25), 0.25)
    unit = norm(get(p, ["product_weight_unit", "weight_unit"], ""))
    if unit in ["g", "gr", "gram", "grams"] and raw_w > 0:
        return max(0.001, raw_w / 1000.0)
    if unit in ["ml"] and raw_w > 0:
        return max(0.001, raw_w / 1000.0)
    if raw_w > 50:
        return raw_w / 1000.0
    return max(0.001, raw_w)


def _sp_is_bulk_floor(p: Dict[str, Any]) -> bool:
    raw = _sp_raw_text(p)
    pt = _sp_package_type(p)
    w = num(p.get("width_cm"), 10)
    h = num(p.get("height_cm"), 20)
    d = num(p.get("depth_cm"), 10)
    wt = _sp_weight_kg(p)

    if pt in ["demijohn", "produce_crate"]:
        return True
    if "damacana" in raw:
        return True
    if any(x in raw for x in ["5 l", "5l", "10 l", "10l", "19 l", "19l"]):
        return True
    if pt == "multipack" and any(x in raw for x in ["su", "water", "cola", "kola", "fanta", "sprite", "içecek", "icecek"]):
        return True
    if wt >= 6 or max(w, h, d) >= 45:
        return True
    return False


def _sp_stocking_behavior(p: Dict[str, Any]) -> str:
    explicit = key(get(p, ["stocking_behavior", "stock_behavior"], ""))
    if explicit:
        return explicit

    pt = _sp_package_type(p)

    if pt == "hanging":
        return "HANGING_DISPLAY"
    if pt == "demijohn":
        return "WATER_RACK"
    if _sp_is_bulk_floor(p):
        return "PALLET_STACK"
    if pt == "produce_crate":
        return "CRATE_STACK"
    if pt in ["egg_tray"]:
        return "FRAGILE_SINGLE_LAYER"
    if pt in ["bag"]:
        return "LIGHT_BAG_DEEP"
    if pt in ["pouch_or_bag"]:
        return "DEEP_STACKABLE_BAG"
    if pt in ["bar"]:
        return "VERTICAL_STACKABLE"
    if pt in ["jar", "can"]:
        return "HEAVY_DEEP_STACKABLE"
    if pt in ["carton"]:
        return "CASE_OR_DEEP_STACKABLE"
    if pt in ["bottle", "multipack"]:
        return "DEEP_STACKABLE"
    return "DEEP_STACKABLE"


def _sp_crush_risk(p: Dict[str, Any]) -> str:
    raw = _sp_raw_text(p)
    behavior = _sp_stocking_behavior(p)

    if behavior == "FRAGILE_SINGLE_LAYER":
        return "HIGH"
    if behavior in ["WATER_RACK", "PALLET_STACK"]:
        return "LOW"
    if any(x in raw for x in ["cips", "chips", "ekmek", "bread", "pasta", "cake", "kek"]):
        return "HIGH"
    if any(x in raw for x in ["cikolata", "çikolata", "gofret", "bar"]):
        return "LOW"
    if any(x in raw for x in ["kavanoz", "cam", "glass", "jar"]):
        return "MEDIUM"
    return "LOW"


def _sp_max_stack_layers(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    explicit = inum(get(p, ["max_stack_layers", "stack_layers"], 0), 0)
    if explicit > 0:
        return max(1, min(explicit, 12))

    behavior = _sp_stocking_behavior(p)
    if behavior in ["WATER_RACK", "PALLET_STACK", "HANGING_DISPLAY", "FRAGILE_SINGLE_LAYER", "LIGHT_BAG_DEEP"]:
        return 1
    if behavior == "VERTICAL_STACKABLE":
        return 6
    if behavior == "DEEP_STACKABLE_BAG":
        return 3
    if behavior == "HEAVY_DEEP_STACKABLE":
        return 2
    if behavior == "CASE_OR_DEEP_STACKABLE":
        return 3
    if behavior == "DEEP_STACKABLE":
        return 2
    return 2


def _sp_depth_units(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    if _sp_stocking_behavior(p) in ["HANGING_DISPLAY", "WATER_RACK", "PALLET_STACK"]:
        return 1
    shelf_depth = num(shelf.get("shelf_depth_cm"), 50)
    product_depth = max(1, num(p.get("depth_cm"), 10))
    du = int(shelf_depth // product_depth)
    # Critical field rule: depth is reserve for SAME SKU only.
    return max(1, min(du, 12))


def _sp_stack_layers(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    behavior = _sp_stocking_behavior(p)
    if behavior in ["HANGING_DISPLAY", "WATER_RACK", "PALLET_STACK"]:
        return 1

    max_layers = _sp_max_stack_layers(p, shelf)
    shelf_height = num(shelf.get("shelf_height_cm"), 35)
    product_height = max(1, num(p.get("height_cm"), 20))

    if behavior == "LIGHT_BAG_DEEP":
        return 1

    physical = max(1, int(shelf_height // product_height))
    return max(1, min(max_layers, physical))


def _sp_capacity_units(p: Dict[str, Any], shelf: Dict[str, Any], facing: int) -> int:
    return max(1, int(max(1, facing) * _sp_depth_units(p, shelf) * _sp_stack_layers(p, shelf)))


def _sp_case_pack_qty(p: Dict[str, Any]) -> int:
    explicit = get(p, ["case_pack_qty", "case_pack", "Case Pack", "units_in_pack_count"], "")
    if explicit in [None, ""]:
        return 1
    return max(1, int(case_pack(p)))


def _sp_case_equivalent(p: Dict[str, Any], shelf: Dict[str, Any], facing: int) -> float:
    return round(_sp_capacity_units(p, shelf, facing) / max(_sp_case_pack_qty(p), 1), 2)


def _sp_recommended_zone_type(p: Dict[str, Any]) -> str:
    behavior = _sp_stocking_behavior(p)
    if behavior == "WATER_RACK":
        return "WATER_RACK"
    if behavior == "PALLET_STACK":
        return "BULK_FLOOR_OR_PALLET"
    if behavior == "CRATE_STACK":
        return "PRODUCE_CRATE"
    if behavior == "HANGING_DISPLAY":
        return "HANGING_DISPLAY"
    if key(p.get("_storage") or p.get("storage_type")) == "CHILLED":
        return "CHILLED_FRIDGE"
    if key(p.get("_storage") or p.get("storage_type")) == "FROZEN":
        return "FROZEN_FREEZER"
    return "REGULAR_SHELF"


def _sp_dimension_confidence(p: Dict[str, Any]) -> float:
    return num(get(p, ["dimension_confidence", "dimension_confidence_score"], 0.70), 0.70)


def _sp_needs_measurement(p: Dict[str, Any]) -> bool:
    if str(get(p, ["needs_user_measurement"], "")).lower() in ["true", "1", "yes", "evet"]:
        return True
    if _sp_dimension_confidence(p) < 0.55:
        return True
    if get(p, ["dimension_source"], "") in ["category_package_fallback", "rejected_dirty_dimension_ai_fallback", "ai_estimated"]:
        return True
    return False


def _sp_target_coverage_days(p: Dict[str, Any]) -> float:
    behavior = _sp_stocking_behavior(p)
    abc = key(p.get("_abc"))

    if behavior in ["PALLET_STACK", "WATER_RACK"]:
        return 2.0
    if behavior == "LIGHT_BAG_DEEP":
        return 0.65 if abc == "A" else 1.0 if abc == "B" else 1.6
    if behavior in ["VERTICAL_STACKABLE", "DEEP_STACKABLE_BAG"]:
        return 1.0 if abc == "A" else 1.7 if abc == "B" else 3.0
    if behavior == "FRAGILE_SINGLE_LAYER":
        return 0.45 if abc == "A" else 0.8
    return _bb_target_coverage_days(p)


def _bb_depth_units(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    return _sp_depth_units(p, shelf)


def _bb_facing_options(p: Dict[str, Any], shelf: Dict[str, Any]) -> List[int]:
    daily = _bb_daily_sales(p)
    target_units = max(1, daily * _sp_target_coverage_days(p))
    per_facing_capacity = max(1, _sp_depth_units(p, shelf) * _sp_stack_layers(p, shelf))
    optimal = int(math.ceil(target_units / per_facing_capacity))

    abc = key(p.get("_abc"))
    behavior = _sp_stocking_behavior(p)

    if abc == "A":
        optimal = max(optimal, 3)
    elif abc == "B":
        optimal = max(optimal, 2)

    if behavior in ["PALLET_STACK", "WATER_RACK"]:
        optimal = min(optimal, 3)

    max_by_width = max(1, int(num(shelf.get("shelf_width_cm"), 100) // max(num(p.get("width_cm"), 10) * 1.08, 1)))

    if behavior == "LIGHT_BAG_DEEP":
        max_cap = 10 if abc == "A" else 7
    elif behavior == "VERTICAL_STACKABLE":
        max_cap = 8
    elif behavior in ["PALLET_STACK", "WATER_RACK"]:
        max_cap = 4
    else:
        max_cap = 12 if abc == "A" else 8

    optimal = max(1, min(max_cap, max_by_width, optimal))
    return list(range(optimal, 0, -1))


def _bb_used_width_for(p: Dict[str, Any], facing: int) -> float:
    behavior = _sp_stocking_behavior(p)
    multiplier = 1.08
    if behavior == "LIGHT_BAG_DEEP":
        multiplier = 1.14
    if behavior in ["PALLET_STACK", "WATER_RACK"]:
        multiplier = 1.02
    return round(max(3, num(p.get("width_cm"), 10)) * max(1, facing) * multiplier, 2)


def _bb_target_max_util(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    behavior = _sp_stocking_behavior(p)
    st = key(p.get("_storage"))

    if behavior == "LIGHT_BAG_DEEP":
        return 0.76
    if behavior == "FRAGILE_SINGLE_LAYER":
        return 0.68
    if behavior == "HANGING_DISPLAY":
        return 0.92
    if behavior in ["PALLET_STACK", "WATER_RACK"]:
        return 0.95
    if st == "FROZEN":
        return 0.82
    if st == "CHILLED":
        return 0.85
    if behavior == "HEAVY_DEEP_STACKABLE":
        return 0.86
    if p.get("_abc") == "A":
        return 0.90
    return 0.86


def _bb_fits(p: Dict[str, Any], shelf: Dict[str, Any], facing: int, allow_high_util: bool = False) -> bool:
    if shelf_storage(shelf) != key(p.get("_storage") or p.get("storage_type")):
        return False

    behavior = _sp_stocking_behavior(p)

    if num(p.get("height_cm"), 20) > num(shelf.get("shelf_height_cm"), 35) and behavior not in ["LIGHT_BAG_DEEP", "HANGING_DISPLAY"]:
        return False
    if num(p.get("depth_cm"), 10) > num(shelf.get("shelf_depth_cm"), 50) and behavior not in ["HANGING_DISPLAY"]:
        return False

    used = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    sw = num(shelf.get("shelf_width_cm"), 100)
    after = used + _bb_used_width_for(p, facing)
    if after > sw:
        return False

    target = _bb_target_max_util(p, shelf)
    if not allow_high_util and after / max(sw, 1) > target:
        return False

    cap_units = _sp_capacity_units(p, shelf, facing)
    added_weight = _sp_weight_kg(p) * cap_units
    if num(shelf.get("used_weight_kg"), 0) + added_weight > num(shelf.get("max_weight_kg"), 45):
        return False

    return True


def _bb_make_placed(p: Dict[str, Any], aisle: Dict[str, Any], module: Dict[str, Any], shelf: Dict[str, Any], facing: int, score: float) -> Dict[str, Any]:
    du = _sp_depth_units(p, shelf)
    stack = _sp_stack_layers(p, shelf)
    cap = _sp_capacity_units(p, shelf, facing)
    daily = _bb_daily_sales(p)
    reserve_depth_units = max(0, cap - max(1, facing))
    refill_per_day = round(daily / max(cap, 1), 2) if daily > 0 else 0
    coverage = round(cap / max(daily, 0.01), 1) if daily > 0 else None
    behavior = _sp_stocking_behavior(p)

    explanation_bits = [
        f"front={facing}",
        f"depth_same_sku={du}",
        f"stack_layers={stack}",
        f"capacity={cap}",
        "back_stock_policy=SAME_SKU_ONLY",
    ]
    if _sp_needs_measurement(p):
        explanation_bits.append("dimension_review_recommended")

    return {
        "sku": sku(p),
        "barcode": clean_text(get(p, ["barcode", "product_barcodes"], "")),
        "product_name": product_name(p),
        "brand": brand(p),
        "brand_name": brand(p),
        "category_l1": category_l1(p),
        "category_l2": category_l2(p),
        "frontend_category_local": category_l1(p),
        "frontend_subcategory_local": category_l2(p),
        "image_url": image_url(p),
        "image": image_url(p),
        "product_image_url": image_url(p),
        "storage_type": p.get("_storage"),
        "merch_group": p.get("_merch_group"),
        "abc_class": p.get("_abc"),
        "tier": p.get("_tier"),
        "front_tier": p.get("_tier"),
        "sales_qty_7d": sales_7d(p),
        "daily_sales": round(daily, 3),
        "percent_stops": percent_stops(p),
        "on_hand_qty": on_hand(p),
        "width_cm": num(p.get("width_cm"), 10),
        "height_cm": num(p.get("height_cm"), 20),
        "depth_cm": num(p.get("depth_cm"), 10),
        "weight_kg": _sp_weight_kg(p),
        "case_pack_qty": _sp_case_pack_qty(p),
        "facing": facing,
        "facing_count": facing,
        "selling_face_units": facing,
        "used_width_cm": _bb_used_width_for(p, facing),
        "stocking_behavior": behavior,
        "package_type": _sp_package_type(p),
        "crush_risk": _sp_crush_risk(p),
        "depth_units": du,
        "depth_units_same_sku": du,
        "stack_layers": stack,
        "max_stack_layers": _sp_max_stack_layers(p, shelf),
        "total_capacity_units": cap,
        "shelf_capacity_units": cap,
        "reserve_depth_units": reserve_depth_units,
        "reserve_units_same_sku": reserve_depth_units,
        "mixed_depth_allowed": False,
        "back_stock_policy": "SAME_SKU_ONLY",
        "case_equivalent_capacity": _sp_case_equivalent(p, shelf, facing),
        "recommended_zone_type": _sp_recommended_zone_type(p),
        "is_bulk_floor_candidate": _sp_is_bulk_floor(p),
        "coverage_days": coverage,
        "refill_per_day": refill_per_day,
        "refill_risk_level": "HIGH" if refill_per_day >= 2 else "MEDIUM" if refill_per_day >= 1 else "LOW",
        "dimension_source": p.get("dimension_source"),
        "dimension_confidence": p.get("dimension_confidence"),
        "dimension_reason": p.get("dimension_reason"),
        "needs_user_measurement": _sp_needs_measurement(p),
        "aisle": aisle.get("aisle_id"),
        "aisle_id": aisle.get("aisle_id"),
        "module_id": module.get("module_id"),
        "shelf_no": shelf.get("shelf_no"),
        "position_order": len(shelf.get("products", [])) + 1,
        "placement_score": round(score, 1),
        "explanation": "Stocking Physics: " + " | ".join(explanation_bits),
    }


def _bb_apply_place(placed: Dict[str, Any], shelf: Dict[str, Any]) -> None:
    shelf.setdefault("products", []).append(placed)
    shelf["used_width_cm"] = round(num(shelf.get("used_width_cm", shelf.get("used", 0)), 0) + num(placed.get("used_width_cm"), 0), 1)
    shelf["used"] = shelf["used_width_cm"]
    shelf["used_weight_kg"] = round(
        num(shelf.get("used_weight_kg"), 0) + num(placed.get("weight_kg"), 0) * inum(placed.get("total_capacity_units"), inum(placed.get("facing_count"), 1)),
        2
    )


def _sp_enrich_summary_with_stocking(plan: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    behavior_counts: Dict[str, int] = {}
    measurement_needed = 0
    same_sku_reserve_units = 0
    total_capacity = 0
    total_front = 0
    bulk_candidates = 0

    for r in _bb_all_shelves(plan):
        for p in r["shelf"].get("products", []):
            b = clean_text(p.get("stocking_behavior")) or "UNKNOWN"
            behavior_counts[b] = behavior_counts.get(b, 0) + 1
            if p.get("needs_user_measurement"):
                measurement_needed += 1
            same_sku_reserve_units += inum(p.get("reserve_units_same_sku"), 0)
            total_capacity += inum(p.get("total_capacity_units"), 0)
            total_front += inum(p.get("selling_face_units"), inum(p.get("facing_count"), 0))
            if p.get("is_bulk_floor_candidate"):
                bulk_candidates += 1

    summary["stocking_physics"] = {
        "back_stock_policy": "SAME_SKU_ONLY",
        "mixed_depth_default": False,
        "total_front_face_units": total_front,
        "total_same_sku_reserve_units": same_sku_reserve_units,
        "total_shelf_capacity_units": total_capacity,
        "measurement_needed_skus": measurement_needed,
        "bulk_floor_candidate_skus": bulk_candidates,
        "behavior_counts": behavior_counts,
    }
    summary["strategy"] = BB_VERSION
    return summary


_PRE_V24_GENERATE_PLANOGRAM = generate_planogram


def generate_planogram(products: List[Dict[str, Any]], layout: Optional[Dict[str, Any]], mode: str = "HYBRID", brand_side_rules: Optional[Dict[str, str]] = None, scoring_config: Optional[Dict[str, float]] = None, allow_ai_dimensions: bool = True) -> Dict[str, Any]:
    result = _PRE_V24_GENERATE_PLANOGRAM(
        products,
        layout,
        mode=mode,
        brand_side_rules=brand_side_rules,
        scoring_config=scoring_config,
        allow_ai_dimensions=allow_ai_dimensions,
    )

    summary = result.get("summary", {})
    plan = result.get("planogram", {})
    _sp_enrich_summary_with_stocking(plan, summary)
    result["summary"] = summary
    result["engine_version"] = BB_VERSION

    insights = result.setdefault("insights", {})
    insights["stocking_physics_logic"] = (
        "Raf derinliği sadece aynı SKU reserve stoğu için kullanılır. "
        "Farklı SKU'yu arka derinliğe koymak default olarak yasaktır; bu no-found ve yanlış ürün riskini düşürür."
    )
    insights["capacity_formula"] = (
        "shelf_capacity_units = front_facings × same_sku_depth_units × safe_stack_layers. "
        "Çikolata/bar gibi ürünlerde stack_layers devreye girer; cips gibi ezilme riski olan ürünlerde sınırlanır."
    )
    insights["case_logic"] = (
        "case_equivalent_capacity alanı, rafa sığan toplam birim kapasitesini case_pack_qty'ye bölerek kaç koli eşdeğeri stok tutulduğunu gösterir."
    )

    actions = result.setdefault("recommended_actions", [])
    actions.insert(0, "Depth reserve yalnızca aynı SKU için kullanılmalı; farklı SKU arkaya konacaksa manuel istisna/onay gerektir.")
    actions.insert(1, "Çikolata/gofret gibi stackable ürünlerde kapasiteyi stack_layers ile, cips gibi ezilen ürünlerde crush_risk ile sınırla.")
    actions.insert(2, "bulk_floor_candidate_skus yüksekse su/koli/palet alanı layout'a ayrı zone olarak eklenmeli.")

    return result


def run_engine(products: List[Dict[str, Any]], layout: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    return generate_planogram(products, layout, **kwargs)

# =====================================================
# END BLACKBELT v24
# =====================================================

# === PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_ENGINE ===
try:
    from storage_normalizer import normalize_storage_type as _plonagram_normalize_storage_type
    def storage_type(p):
        return _plonagram_normalize_storage_type(p)
except Exception as _plonagram_storage_patch_err:
    print("PLONAGRAM storage normalizer engine override devreye alınamadı:", _plonagram_storage_patch_err)
# === END PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_ENGINE ===\n\n# === PLONAGRAM_FIXTURE_CAPACITY_BALANCED_ENGINE_V3 ===
# Layout object -> real fixture capacity mapper + cold/frozen capacity expansion.
# This patch wraps generate_planogram/run_engine without deleting existing engine logic.

try:
    from fixture_capacity_mapper import expand_layout_for_product_mix as _plonagram_expand_layout_for_product_mix
    from fixture_capacity_mapper import storage_capacity as _plonagram_storage_capacity

    if "_plonagram_original_generate_planogram_v3" not in globals():
        _plonagram_original_generate_planogram_v3 = generate_planogram

    def generate_planogram(
        products,
        layout,
        mode="HYBRID",
        brand_side_rules=None,
        scoring_config=None,
        allow_ai_dimensions=True,
    ):
        raw_layout = layout or generate_default_layout()

        expanded_layout = _plonagram_expand_layout_for_product_mix(
            raw_layout,
            products or [],
            make_shelves,
        )

        result = _plonagram_original_generate_planogram_v3(
            products=products,
            layout=expanded_layout,
            mode=mode,
            brand_side_rules=brand_side_rules,
            scoring_config=scoring_config,
            allow_ai_dimensions=allow_ai_dimensions,
        )

        plan = result.get("planogram") or {}
        result["engine_patches"] = {
            **(result.get("engine_patches") or {}),
            "fixture_capacity_mapper_v3": True,
            "balanced_capacity_expansion": True,
        }
        result["fixture_capacity_summary"] = expanded_layout.get("ai_fixture_capacity_summary", {})
        result["capacity_after_generation"] = _plonagram_storage_capacity(plan)
        return result

    def run_engine(products, layout=None, **kwargs):
        return generate_planogram(products, layout, **kwargs)

except Exception as _plonagram_fixture_capacity_patch_error:
    print("PLONAGRAM fixture capacity balanced patch V3 devreye alınamadı:", _plonagram_fixture_capacity_patch_error)
# === END PLONAGRAM_FIXTURE_CAPACITY_BALANCED_ENGINE_V3 ===\n