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



VALID_STORAGE_TYPES = {"AMBIENT", "CHILLED", "FROZEN", "PALLET"}

def canonical_storage_value(value: Any) -> str:
    raw = key(value)

    if raw in VALID_STORAGE_TYPES:
        return raw

    chilled_tokens = [
        "DOLAP", "+4", "SO?UK", "SOGUK", "CHILL", "CHILLED",
        "COLD", "FRIDGE", "FOOD CHILLED", "CHILLED GENERAL"
    ]
    frozen_tokens = [
        "-18", "DONUK", "FROZEN", "FREEZER", "ICE CREAM",
        "DONDURMA", "ALGIDA", "FOOD FROZEN", "FROZEN GENERAL"
    ]

    if any(t in raw for t in frozen_tokens):
        return "FROZEN"

    if any(t in raw for t in chilled_tokens):
        return "CHILLED"

    return ""

def infer_storage_from_text(p: Dict[str, Any]) -> str:
    raw = key(
        f"{product_name(p)} "
        f"{category_l1(p)} "
        f"{category_l2(p)} "
        f"{brand(p)}"
    )

    if any(x in raw for x in ["FROZEN", "DONUK", "-18", "DONDUR", "ICE CREAM", "FREEZER", "ALGIDA"]):
        return "FROZEN"

    if any(x in raw for x in ["CHILLED", "COLD", "+4", "S?T", "SUT", "DAIRY", "YO?URT", "YOGURT", "FRIDGE", "TAVUK", "P?L??", "PILIC", "MEAT", "ET "]):
        return "CHILLED"

    return "AMBIENT"

def fixture_domain_for_storage(storage: str) -> str:
    st = canonical_storage_value(storage) or "AMBIENT"

    if st == "CHILLED":
        return "CHILLED_DOLAP"

    if st == "FROZEN":
        return "FROZEN_DOLAP"

    if st == "PALLET":
        return "PALLET_AREA"

    return "AMBIENT_RAF"

def resolve_canonical_storage(master: Dict[str, Any], original: Dict[str, Any], base: Dict[str, Any]) -> Tuple[str, str, str]:
    # Kritik karar:
    # 1) Master catalog kazan?r.
    # 2) Upload / ABC sadece master bo?sa kullan?l?r.
    # 3) ?simden tahmin en son ?are.
    master_raw = first_non_empty(
        get(master, ["catalog_storage_type"], ""),
        get(master, ["master_storage_type"], ""),
        get(master, ["storage_type"], ""),
        get(master, ["Storage Type"], ""),
        get(master, ["storage"], ""),
        get(master, ["storage_type_raw"], ""),
        get(master, ["storage_type_clean"], ""),
        get(master, ["recommended_zone_type"], ""),
        get(master, ["package_type"], ""),
    )

    original_raw = first_non_empty(
        get(original, ["catalog_storage_type"], ""),
        get(original, ["master_storage_type"], ""),
        get(original, ["storage_type"], ""),
        get(original, ["Storage Type"], ""),
        get(original, ["Storage"], ""),
        get(original, ["storage"], ""),
        get(original, ["recommended_zone_type"], ""),
    )

    master_storage = canonical_storage_value(master_raw)
    if master_storage:
        return master_storage, "master_catalog", clean_text(master_raw)

    original_storage = canonical_storage_value(original_raw)
    if original_storage:
        return original_storage, "upload_or_abc", clean_text(original_raw)

    inferred = infer_storage_from_text(base)
    return inferred, "name_category_inferred", ""


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
    direct = canonical_storage_value(first_non_empty(
        get(p, ["catalog_storage_type"], ""),
        get(p, ["master_storage_type"], ""),
        get(p, ["storage_type"], ""),
        get(p, ["Storage Type"], ""),
        get(p, ["Storage"], ""),
        get(p, ["storage"], ""),
        get(p, ["recommended_zone_type"], ""),
    ))

    if direct:
        return direct

    return infer_storage_from_text(p)


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

    canonical_storage, storage_source, storage_raw_value = resolve_canonical_storage(master, original, base)
    base["storage_type"] = canonical_storage
    base["catalog_storage_type"] = canonical_storage
    base["storage_type_source"] = storage_source
    base["storage_type_raw_value"] = storage_raw_value

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
        "storage_type": canonical_storage,
        "catalog_storage_type": canonical_storage,
        "storage_type_source": storage_source,
        "storage_type_raw_value": storage_raw_value,
        "fixture_domain": fixture_domain_for_storage(canonical_storage),
        "placement_domain": fixture_domain_for_storage(canonical_storage),
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
    MAX_PRODUCTS = 15000

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