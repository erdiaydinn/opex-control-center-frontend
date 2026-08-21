from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple
from pathlib import Path
import os
import re
import math
import heapq
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

BACKEND_ROOT = Path(__file__).resolve().parent
MASTER_CSV = str(BACKEND_ROOT / "data" / "master_products.csv")
MASTER_XLSX = str(BACKEND_ROOT / "data" / "master_products.xlsx")

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


def normalize_storage(value: Any, default: str = "AMBIENT") -> str:
    """Normalize product, fixture and rule storage labels to one contract."""
    raw = norm(value)
    if not raw:
        return default

    if any(token in raw for token in ("frozen", "donuk", "dondur", "freezer", "-18", "algida")):
        return "FROZEN"
    if any(token in raw for token in ("chilled", "cold", "soguk", "+4", "dairy", "sut", "yogurt", "fridge", "cooler")):
        return "CHILLED"
    if any(token in raw for token in ("pallet", "palet")):
        return "PALLET"
    if any(token in raw for token in ("ambient", "room", "raf", "regular", "dry")):
        return "AMBIENT"
    return default


def _column_key(value: Any) -> str:
    """Turn localised CSV headers into a stable comparison key.

    Product uploads arrive from both the API and Turkish Excel exports.  The
    previous engine only compared English field names, so ``Urun``,
    ``Kategori`` and ``Marka`` silently became empty values.  That made the
    allocator treat every SKU as UNKNOWN/GENERAL and use generic dimensions.
    """
    return re.sub(r"[^a-z0-9]+", "_", norm(value)).strip("_")


INPUT_COLUMN_ALIASES = {
    "urun": "product_name",
    "urun_adi": "product_name",
    "urun_isim": "product_name",
    "product": "product_name",
    "product_name_tr": "product_name",
    "marka": "brand",
    "marka_adi": "brand",
    "kategori": "category_l1",
    "kategori_l1": "category_l1",
    "alt_kategori": "category_l2",
    "kategori_l2": "category_l2",
    "subcategory": "category_l2",
    "storage": "storage_type",
    "depo": "storage_type",
    "saklama": "storage_type",
    "sicaklik": "storage_type",
    "genislik": "width_cm",
    "genislik_cm": "width_cm",
    "yukseklik": "height_cm",
    "yukseklik_cm": "height_cm",
    "boy": "height_cm",
    "derinlik": "depth_cm",
    "derinlik_cm": "depth_cm",
    "agirlik": "weight_kg",
    "agirlik_kg": "weight_kg",
    "onyuz": "source_facing",
    "on_yuz": "source_facing",
    "mevcut_facing": "source_facing",
    "lokasyon": "current_location",
    "yeni_lokasyon": "current_location",
    "koridor": "aisle_id",
    "modul": "module_id",
    "raf": "shelf_no",
    "son_7_gun_satis": "sales_qty_7d",
    "son_7_gun_satis_adedi": "sales_qty_7d",
    "sales_7d": "sales_qty_7d",
    "haftalik_satis": "sales_qty_7d",
    "satis_7d": "sales_qty_7d",
    "stok": "on_hand_qty",
    "mevcut_stok": "on_hand_qty",
    "stok_adedi": "on_hand_qty",
    "koli_ici": "case_pack_qty",
    "koli_ici_adet": "case_pack_qty",
    "koli_adedi": "case_pack_qty",
    "urun_gorsel": "image_url",
    "urun_gorsel_url": "image_url",
    "akis_tipi": "flow_type",
    "urun_akis_tipi": "flow_type",
    "tedarik_tipi": "flow_type",
    "tedarik_modeli": "flow_type",
    "supply_model": "flow_type",
    "fulfillment_model": "flow_type",
    "replenishment_model": "flow_type",
    "distribution_type": "flow_type",
    "cdc_flag": "cdc_flag",
}


def normalize_product_row(product: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Add canonical fields while preserving the original upload columns."""
    source = dict(product or {})
    normalized = dict(source)
    for raw_key, value in source.items():
        canonical = INPUT_COLUMN_ALIASES.get(_column_key(raw_key))
        if not canonical:
            continue
        existing = normalized.get(canonical)
        if existing in (None, ""):
            normalized[canonical] = value
    return normalized


def get(p: Dict[str, Any], names: List[str], default: Any = "") -> Any:
    for n in names:
        if n in p and p[n] not in [None, ""]:
            return p[n]

    lower = {str(k).lower().lstrip("\ufeff"): k for k in p.keys()}
    for n in names:
        real = lower.get(str(n).lower())
        if real is not None and p[real] not in [None, ""]:
            return p[real]

    return default


def as_text_list(value: Any) -> List[str]:
    """Return a stable, normalized list for rule fields supplied by the UI."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = re.split(r"[,;|\n]+", clean_text(value))
    return [norm(x) for x in raw if norm(x)]


def _matches_token(value: Any, tokens: Iterable[str]) -> bool:
    candidate = norm(value)
    if not candidate:
        return False
    return any(token == candidate or token in candidate or candidate in token for token in tokens)


def rule_matches_product(p: Dict[str, Any], rule: Optional[Dict[str, Any]], include_storage: bool = True) -> bool:
    """Evaluate the complete rule contract used by modules and shelves.

    Older UI builds only sent ``brand``/``category``. Newer builds can send
    allowed/blocked category lists, storage, and merchandising groups. Keeping
    the evaluation here makes every generation and edit endpoint consistent.
    """
    if not rule:
        return True

    product_group = p.get("_merch_group") or p.get("merch_group") or merch_group(p)
    category_values = [category_l1(p), category_l2(p), product_group]
    brand_values = [brand(p), product_name(p)]

    allowed_storage = [
        normalize_storage(token, default="")
        for token in as_text_list(rule.get("allowed_storage_type") or rule.get("storage_type"))
    ]
    allowed_storage = [token for token in allowed_storage if token]
    if include_storage and allowed_storage:
        product_storage = normalize_storage(p.get("_storage") or storage_type(p))
        if product_storage not in allowed_storage:
            return False

    allowed_categories = as_text_list(rule.get("allowed_categories"))
    if allowed_categories and not any(_matches_token(value, allowed_categories) for value in category_values):
        return False

    blocked_categories = as_text_list(rule.get("blocked_categories"))
    if blocked_categories and any(_matches_token(value, blocked_categories) for value in category_values):
        return False

    allowed_groups = as_text_list(rule.get("allowed_merch_groups") or rule.get("allowed_groups"))
    if allowed_groups and not any(_matches_token(value, allowed_groups) for value in [product_group]):
        return False

    blocked_groups = as_text_list(rule.get("blocked_merch_groups") or rule.get("blocked_groups"))
    if blocked_groups and any(_matches_token(value, blocked_groups) for value in [product_group]):
        return False

    requested_brand = as_text_list(rule.get("brand") or rule.get("brands"))
    if requested_brand and not any(_matches_token(value, requested_brand) for value in brand_values):
        return False

    requested_category = as_text_list(rule.get("category") or rule.get("category_l1") or rule.get("category_l2"))
    if requested_category and not any(_matches_token(value, requested_category) for value in category_values):
        return False

    supplier = as_text_list(rule.get("supplier") or rule.get("supplier_name"))
    if supplier and not _matches_token(get(p, ["supplier_name", "vendor_name"], ""), supplier):
        return False

    return True


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
    return clean_text(get(p, ["product_name", "Product Name", "name", "Urun", "Ürün"], ""))


def sku(p: Dict[str, Any]) -> str:
    return clean_text(get(p, ["sku", "SKU", "barcode", "Stok Kodu", "Urun Kodu"], ""))


def brand(p: Dict[str, Any]) -> str:
    b = get(p, ["brand", "Brand", "brand_name", "Marka"], "")
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
        "Kategori",
    ], "GENERAL"))


def category_l2(p: Dict[str, Any]) -> str:
    return clean_text(get(p, [
        "category_l2",
        "Category L2",
        "subcategory",
        "frontend_subcategory_local",
        "pim_cat_l2",
        "Alt Kategori",
    ], "GENERAL"))


def image_url(p: Dict[str, Any]) -> str:
    return clean_text(get(p, [
        "image_url",
        "Product Image URL",
        "catalog_image_url",
        "pim_image_url",
    ], ""))


def storage_type(p: Dict[str, Any]) -> str:
    explicit = get(p, ["storage_type", "Storage Type", "Storage", "storage_raw"], "")
    explicit_storage = normalize_storage(explicit, default="")
    if explicit_storage:
        # Catalog storage is authoritative. Product names/categories are only
        # a fallback for legacy uploads where the field is absent.
        return explicit_storage

    raw = f"{product_name(p)} {category_l1(p)} {category_l2(p)}"
    return normalize_storage(raw)


def is_cdc_product(p: Dict[str, Any]) -> bool:
    """Return True only for explicit CDC/cross-dock operational markers.

    CDC assortment does not occupy a selling shelf, so it must stay outside
    the planogram instead of being silently classified as AMBIENT.
    """
    explicit_values = [
        get(p, ["flow_type", "supply_model", "fulfillment_model"], ""),
        get(p, ["replenishment_model", "distribution_type", "product_flow"], ""),
        get(p, ["cdc_flag", "is_cdc", "cross_dock", "cross_dock_flag"], ""),
        get(p, ["current_location", "secondary_location"], ""),
    ]
    for value in explicit_values:
        raw = norm(value)
        if raw in {"cdc", "true", "1", "yes", "evet", "cross dock", "cross-dock", "crossdock"}:
            return True
        if re.search(r"(?:^|[^a-z0-9])cdc(?:[^a-z0-9]|$)", raw):
            return True
        if "cross dock" in raw or "crossdock" in raw:
            return True
    return False


def requires_pallet_storage(p: Dict[str, Any]) -> bool:
    """Apply the operational 5 L rule without confusing 500 ml products."""
    if normalize_storage(get(p, ["storage_type", "Storage Type", "Storage"], ""), default="") == "PALLET":
        return True

    raw = norm(
        " ".join(
            clean_text(get(p, [field], ""))
            for field in (
                "product_name",
                "Product Name",
                "name",
                "product_contents_value",
                "product_contents_unit",
                "volume",
                "volume_unit",
            )
        )
    )
    return bool(
        re.search(r"(?:^|[^0-9])5\s*(?:l|lt|ltr|litre|liter)(?:[^a-z0-9]|$)", raw)
    )


def shelf_storage(shelf: Dict[str, Any]) -> str:
    return normalize_storage(get(shelf, [
        "allowed_storage_type",
        "storage_type",
        "storage",
        "zone",
        "zone_type",
        "temperature",
        "fixture_type",
        "module_type",
    ], "AMBIENT"))


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

    if re.search(r"\b(poset|shopping bag|carrier bag|bag)\b", raw):
        return {"width_cm": 18, "height_cm": 28, "depth_cm": 2, "weight_kg": 0.02, "confidence": 0.88, "reason": "shopping_bag"}

    multipack = re.search(r"(?:^|\s)(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\b", raw)

    # Do not use ``"su" in raw`` here: it classifies SuperFresh and many
    # unrelated Turkish words as water.  A token boundary is intentional.
    water_like = bool(re.search(r"\bwater\b", raw) or re.search(r"\bsu\b", raw))
    soda_like = any(x in raw for x in ["soda", "gazoz", "sparkling", "maden suyu", "mineral"])
    multipack_beverage = bool(multipack and any(x in raw for x in ["beverage", "icecek", "içecek", "drink", "maden", "soda", "water", "su"]))

    if soda_like or water_like or multipack_beverage:
        if multipack and inum(multipack.group(1), 1) >= 4:
            return {"width_cm": 18, "height_cm": 18, "depth_cm": 12, "weight_kg": 1.3, "confidence": 0.78, "reason": "beverage_multipack"}
        if any(x in raw for x in ["5l", "5 l", "10l", "10 l"]):
            return {"width_cm": 24, "height_cm": 36, "depth_cm": 24, "weight_kg": 5, "confidence": 0.75, "reason": "large_water"}
        if soda_like:
            return {"width_cm": 9, "height_cm": 28, "depth_cm": 9, "weight_kg": 1, "confidence": 0.70, "reason": "carbonated_beverage"}
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
    original = normalize_product_row(raw)
    original = apply_overrides_to_product(original)

    master = find_master_match(original) or {}

    merged = {**master, **original}

    p_name = first_non_empty(
        get(original, ["product_name", "Product Name", "name", "Urun", "Ürün"], ""),
        get(master, ["product_name", "product_name_local", "pim_product_name_local"], ""),
    )

    b_name = first_non_empty(
        get(original, ["brand", "Brand", "brand_name", "Marka"], ""),
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
        "storage_type": "PALLET" if requires_pallet_storage(base) else storage_type(base),
        "flow_type": first_non_empty(
            get(original, ["flow_type", "supply_model", "fulfillment_model", "replenishment_model", "distribution_type"], ""),
            get(master, ["flow_type", "supply_model", "fulfillment_model", "replenishment_model", "distribution_type"], ""),
        ),
        "is_cdc": is_cdc_product({**master, **original}),
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
        "source_facing": max(0, inum(get(original, ["source_facing", "Onyuz", "Önyüz"], 0), 0)),
        "input_quality": {
            "name_present": bool(p_name),
            "brand_present": bool(b_name and b_name != "UNKNOWN"),
            "category_present": bool(cat1 and cat1 != "GENERAL"),
            "storage_present": bool(get(original, ["storage_type", "Storage Type", "Storage", "storage_raw"], "")),
            "dimensions_present": bool(has_file_dim or has_master_dim),
        },
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
    return str(p.get("_merch_group") or p.get("merch_group") or merch_group(p)).startswith("FOOD")


def is_odor(p: Dict[str, Any]) -> bool:
    return str(p.get("_merch_group") or p.get("merch_group") or merch_group(p)) == "NON_FOOD_ODOR"


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


def oriented_width(p: Dict[str, Any]) -> float:
    return max(0.1, depth(p) if p.get("is_rotated") else width(p))


def oriented_depth(p: Dict[str, Any]) -> float:
    return max(0.1, width(p) if p.get("is_rotated") else depth(p))


def placed_facing(p: Dict[str, Any], default: Optional[int] = None) -> int:
    raw = p.get("facing_count", p.get("facing", default if default is not None else 1))
    return max(1, min(12, inum(raw, default if default is not None else 1)))


def depth_units(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    return max(1, int(num(shelf.get("shelf_depth_cm"), 50) // oriented_depth(p)))


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

    # A single SKU must not consume an entire 100 cm shelf just because a
    # sales feed is missing or a weekly total is unusually high.  The old
    # cap of 8 made the first beverage on a shelf take all usable width and
    # pushed the next Beypazarı/Soda SKU down to one facing or out of the
    # assortment.  Extra capacity can be allocated in a later optimisation
    # pass; the generation pass protects assortment breadth first.
    return max(1, min(5, base))


def max_fit_facing(p: Dict[str, Any], shelf: Dict[str, Any], include_weight: bool = True) -> int:
    """Return the physically possible facing count on the current shelf."""
    remaining = num(shelf.get("shelf_width_cm"), 100) - num(shelf.get("used_width_cm"), 0)
    unit_width = oriented_width(p) * 1.1
    by_width = int(max(0, math.floor((remaining + 1e-9) / max(unit_width, 0.1))))

    if include_weight:
        remaining_weight = num(shelf.get("max_weight_kg"), 45) - num(shelf.get("used_weight_kg"), 0)
        by_weight = int(max(0, math.floor((remaining_weight + 1e-9) / max(weight(p), 0.01))))
        return max(0, min(by_width, by_weight, 12))

    return max(0, min(by_width, 12))


def fit_facing(p: Dict[str, Any], shelf: Dict[str, Any]) -> int:
    """Shrink the requested facing to the largest safe value that fits."""
    return min(preferred_facing(p, shelf), max_fit_facing(p, shelf))


def used_width(p: Dict[str, Any], shelf: Dict[str, Any], facing: Optional[int] = None) -> float:
    f = placed_facing(p) if facing is None and ("facing" in p or "facing_count" in p) else (facing or preferred_facing(p, shelf))
    return oriented_width(p) * max(1, f) * 1.1


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


def aisle_label(index: int) -> str:
    """Return spreadsheet-style aisle IDs: A..Z, AA..AZ, BA..."""
    value = max(0, int(index)) + 1
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def generate_default_layout(
    aisle_count: int = 12,
    modules_per_aisle: int = 10,
    shelves_per_module: int = 6,
) -> Dict[str, Any]:
    """Generate the neutral store baseline.

    The baseline is exactly 12 × 10 × 6 unless callers explicitly request a
    different size. Cold/frozen fixtures are Store DNA equipment and are not
    fabricated into every depot.
    """
    aisle_count = max(1, min(int(aisle_count or 12), 200))
    modules_per_aisle = max(1, min(int(modules_per_aisle or 10), 40))
    shelves_per_module = max(1, min(int(shelves_per_module or 6), 12))
    aisles = []

    for index in range(aisle_count):
        row_index = index // 4
        position = index % 4
        direction = "LTR" if row_index % 2 == 0 else "RTL"
        visual_position = position + 1 if direction == "LTR" else 4 - position
        aid = aisle_label(index)
        aisles.append({
            "aisle_id": aid,
            "row": row_index + 1,
            "position": visual_position,
            "direction": direction,
            "distance_to_dispatch": index + 1,
            "aisle_type": "double_sided",
            "sides": ["L", "R"],
            "zone_type": "AMBIENT_ZONE",
            "modules": [
                {
                    "module_id": module_index + 1,
                    "side": "L" if module_index % 2 == 0 else "R",
                    "module_type": "regular_shelf",
                    "distance_to_dispatch": module_index + 1,
                    "module_width_cm": 100,
                    "module_depth_cm": 50,
                    "module_height_cm": 200,
                    "assignment_rule": None,
                    "shelves": make_shelves(
                        shelves_per_module, "AMBIENT", 100, 35, 50, 45
                    ),
                }
                for module_index in range(modules_per_aisle)
            ],
        })

    return {
        "store_code": "AUTO",
        "route_strategy": "S_PATTERN_DYNAMIC",
        "template": {
            "aisle_count": aisle_count,
            "modules_per_aisle": modules_per_aisle,
            "shelves_per_module": shelves_per_module,
        },
        "aisles": aisles,
    }


def prepare_layout(layout: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    plan = deepcopy(layout or generate_default_layout())

    for aisle in plan.get("aisles", []):
        modules = aisle.setdefault("modules", [])
        for module_index, module in enumerate(modules, start=1):
            module["module_id"] = inum(module.get("module_id"), module_index)

            module_width = num(
                module.get("module_width_cm") or module.get("width_cm"),
                100,
            )
            module_depth = num(
                module.get("module_depth_cm") or module.get("depth_cm"),
                50,
            )
            module_height = num(
                module.get("module_height_cm") or module.get("height_cm"),
                200,
            )
            module_type = clean_text(module.get("module_type") or module.get("fixture_type"))
            module_storage = normalize_storage(get(module, [
                "allowed_storage_type",
                "storage_type",
                "storage",
                "zone",
                "zone_type",
                "temperature",
                "fixture_type",
                "module_type",
            ], "AMBIENT"))
            module["storage_type"] = module_storage

            shelves = module.get("shelves")
            if not isinstance(shelves, list):
                shelves = []

            # A room object is a layout object, not a product-bearing shelf.
            # Standard fixture modules can safely be completed from shelf_count.
            is_room = "room" in norm(module_type)
            if not shelves and not is_room:
                shelf_count = inum(module.get("shelf_count"), 6)
                if shelf_count > 0:
                    shelves = make_shelves(
                        shelf_count,
                        module_storage,
                        module_width,
                        max(20, module_height / max(shelf_count, 1)),
                        module_depth,
                        num(module.get("max_weight_kg"), 45),
                    )

            module["shelves"] = shelves
            for shelf_index, shelf in enumerate(shelves, start=1):
                shelf["shelf_no"] = inum(shelf.get("shelf_no"), shelf_index)
                shelf["shelf_width_cm"] = num(
                    shelf.get("shelf_width_cm") or shelf.get("width_cm"),
                    module_width,
                )
                shelf["shelf_height_cm"] = num(
                    shelf.get("shelf_height_cm") or shelf.get("height_cm"),
                    35,
                )
                shelf["shelf_depth_cm"] = num(
                    shelf.get("shelf_depth_cm") or shelf.get("depth_cm"),
                    module_depth,
                )
                shelf["max_weight_kg"] = num(
                    shelf.get("max_weight_kg") or module.get("max_weight_kg"),
                    45,
                )
                shelf["allowed_storage_type"] = normalize_storage(get(shelf, [
                    "allowed_storage_type",
                    "storage_type",
                    "storage",
                    "zone",
                    "temperature",
                ], module_storage), module_storage)
                shelf.setdefault("allowed_categories", [])
                shelf.setdefault("blocked_categories", [])
                shelf.setdefault("assignment_rule", None)
                shelf["products"] = []
                shelf["used_width_cm"] = 0
                shelf["used_weight_kg"] = 0
                shelf["used"] = 0

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


def balance_score(shelf: Dict[str, Any], product: Optional[Dict[str, Any]] = None, facing: Optional[int] = None) -> float:
    used = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    width_cm = num(shelf.get("shelf_width_cm"), 100)
    if product is not None:
        used += used_width(product, shelf, facing or fit_facing(product, shelf))
    util = used / max(width_cm, 1)

    # Best-fit behavior: use an existing compatible shelf before opening a
    # new one, but leave a small refill buffer instead of creating overflow.
    if util < 0.25:
        return -45
    if util < 0.55:
        return 20
    if util <= 0.88:
        return 100
    if util <= 0.96:
        return 35
    if util <= 1.0:
        return -80
    return -1000



def coverage_score(p: Dict[str, Any], shelf: Dict[str, Any]) -> float:
    f = max(1, fit_facing(p, shelf) or 1)
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
    return rule_matches_product(p, module.get("assignment_rule"))


def existing_groups_on_aisle(aisle: Dict[str, Any]) -> set:
    groups = set()
    for m in aisle.get("modules", []):
        for s in m.get("shelves", []):
            for p in s.get("products", []):
                g = p.get("merch_group") or p.get("_merch_group")
                if g:
                    groups.add(g)
    return groups


def merch_compatible(
    p: Dict[str, Any],
    aisle: Dict[str, Any],
    cached_groups: Optional[set] = None,
    shelf: Optional[Dict[str, Any]] = None,
) -> bool:
    aid = key(aisle.get("aisle_id"))
    groups = cached_groups if cached_groups is not None else existing_groups_on_aisle(aisle)

    if aid == "A" and not is_food(p):
        return False

    # Food and cleaning products may share an aisle, but never the same shelf.
    # The previous implementation rejected the whole aisle once either group
    # appeared, which caused unnecessary unplaced SKUs and empty capacity.
    shelf_groups = set()
    for existing in (shelf or {}).get("products", []):
        group = existing.get("merch_group") or existing.get("_merch_group")
        if group:
            shelf_groups.add(group)

    product_group = str(p.get("_merch_group") or p.get("merch_group") or merch_group(p))
    if product_group.startswith("FOOD") and "NON_FOOD_ODOR" in shelf_groups:
        return False

    if product_group == "NON_FOOD_ODOR" and any(str(g).startswith("FOOD") for g in shelf_groups):
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
    score += balance_score(shelf, p, fit_facing(p, shelf)) * cfg["balance"]
    score += coverage_score(p, shelf) * cfg["coverage"]

    score += max(0, 220 - route_score(aisle, module) * 0.8) * cfg["picking"]
    score += brand_side(p, module, brand_side_rules) * cfg["brand_cluster"]

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
    if oriented_depth(p) > num(shelf.get("shelf_depth_cm"), 50):
        return False
    return True


def weight_fit(p: Dict[str, Any], shelf: Dict[str, Any], facing: Optional[int] = None) -> bool:
    current = num(shelf.get("used_weight_kg"), 0)
    add = weight(p) * (facing or fit_facing(p, shelf))
    limit = num(shelf.get("max_weight_kg"), 45)
    return current + add <= limit


def capacity_fit(p: Dict[str, Any], shelf: Dict[str, Any], facing: Optional[int] = None) -> bool:
    current = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
    f = facing or fit_facing(p, shelf)
    if f <= 0:
        return False
    return current + used_width(p, shelf, f) <= num(shelf.get("shelf_width_cm"), 100) + 1e-9


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

    module_category_rule = {
        "allowed_categories": module.get("allowed_categories", []),
        "blocked_categories": module.get("blocked_categories", []),
    }
    if not rule_matches_product(p, module_category_rule, include_storage=False):
        return False, "module_category_rule_not_match"

    shelf_rule = shelf.get("assignment_rule")
    if shelf_rule and not rule_matches_product(p, shelf_rule):
        return False, "shelf_rule_not_match"

    shelf_category_rule = {
        "allowed_categories": shelf.get("allowed_categories", []),
        "blocked_categories": shelf.get("blocked_categories", []),
    }
    if not rule_matches_product(p, shelf_category_rule, include_storage=False):
        return False, "shelf_category_rule_not_match"

    if not merch_compatible(p, aisle, aisle_groups, shelf):
        return False, "merch_not_compatible"

    if not dimension_fit(p, shelf):
        return False, "dimension_not_fit"

    facing = fit_facing(p, shelf)
    if facing <= 0:
        return False, "capacity_not_fit"

    if not capacity_fit(p, shelf, facing):
        return False, "capacity_not_fit"

    if not weight_fit(p, shelf, facing):
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
                    "pool_index": len(shelf_pool[storage]),
                })

    shelf_pool["_state"] = {
        storage: {
            "cursor": 0,
            "recent": [],
            "brand": {},
            "category": {},
            "remaining_width": sum(
                max(
                    0,
                    num(item["shelf"].get("shelf_width_cm"), 100)
                    - num(item["shelf"].get("used_width_cm"), 0),
                )
                for item in items
            ),
        }
        for storage, items in shelf_pool.items()
    }
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

    all_candidates = shelf_pool.get(storage, [])
    state = shelf_pool.get("_state", {}).setdefault(storage, {
        "cursor": 0, "recent": [], "brand": {}, "category": {},
        "remaining_width": sum(num(x["shelf"].get("shelf_width_cm"), 100) for x in all_candidates),
    })
    product_width_with_buffer = oriented_width(p) * 1.1
    product_depth = oriented_depth(p)
    product_height = height(p)
    product_weight = weight(p)

    if not all_candidates or state["remaining_width"] + 1e-9 < product_width_with_buffer:
        return False, None, "capacity_not_fit"

    product_brand = norm(brand(p))
    product_category = norm(category_l2(p))
    candidate_items = []
    seen_candidates = set()

    def add_candidate(item):
        if not item:
            return
        marker = id(item["shelf"])
        if marker in seen_candidates:
            return
        seen_candidates.add(marker)
        candidate_items.append(item)

    for item in state["brand"].get(product_brand, [])[-4:]:
        add_candidate(item)
    for item in state["category"].get(product_category, [])[-4:]:
        add_candidate(item)
    for item in state["recent"][-8:]:
        add_candidate(item)

    # Scan a bounded moving window instead of all shelves for every SKU.
    # The cursor keeps the common path O(products), while brand/category
    # indexes preserve clustering around shelves already in use.
    pool_size = len(all_candidates)
    start = int(state["cursor"]) % pool_size
    scanned = 0
    while scanned < min(pool_size, 48) and len(candidate_items) < 24:
        idx = (start + scanned) % pool_size
        add_candidate(all_candidates[idx])
        scanned += 1

    def physically_viable(item):
        shelf = item["shelf"]
        if product_height > num(shelf.get("shelf_height_cm"), 35):
            return False
        if product_depth > num(shelf.get("shelf_depth_cm"), 50):
            return False
        if num(shelf.get("shelf_width_cm"), 100) - num(shelf.get("used_width_cm"), 0) + 1e-9 < product_width_with_buffer:
            return False
        if num(shelf.get("max_weight_kg"), 45) - num(shelf.get("used_weight_kg"), 0) + 1e-9 < product_weight:
            return False
        return True

    viable = [item for item in candidate_items if physically_viable(item)]

    def candidate_priority(item):
        shelf = item["shelf"]
        products_on_shelf = shelf.get("products", [])
        same_brand = any(norm(x.get("brand")) == product_brand for x in products_on_shelf)
        same_category = any(norm(x.get("category_l2")) == product_category for x in products_on_shelf)
        used = num(shelf.get("used_width_cm"), 0)
        total = max(num(shelf.get("shelf_width_cm"), 100), 1)
        utilization = used / total
        return (
            0 if same_brand else 1 if same_category else 2 if products_on_shelf else 3,
            -utilization,
            item.get("route", 9999),
            str(item["aisle"].get("aisle_id", "")),
            inum(item["module"].get("module_id")),
            inum(shelf.get("shelf_no")),
        )

    candidates = heapq.nsmallest(8, viable, key=candidate_priority)

    best = None
    best_score = -10**18
    last_reason = "no_candidate"

    evaluated = set()

    def evaluate(items):
        nonlocal best, best_score, last_reason
        for item in items:
            marker = id(item["shelf"])
            if marker in evaluated:
                continue
            evaluated.add(marker)
            aisle, module, shelf = item["aisle"], item["module"], item["shelf"]

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

    evaluate(candidates)

    if best is None and len(evaluated) < len(viable):
        evaluate(viable)

    # Rare dimension/rule combinations may miss the moving window. Fall back
    # to a complete scan in small batches until one rule-compatible shelf is
    # found; normal high-volume placement never sorts or scores the complete
    # pool.
    if best is None:
        fallback = []
        for offset in range(pool_size):
            item = all_candidates[(start + offset) % pool_size]
            if id(item["shelf"]) in evaluated or not physically_viable(item):
                continue
            fallback.append(item)
            if len(fallback) >= 12:
                evaluate(fallback)
                fallback = []
                if best is not None:
                    break
        if best is None and fallback:
            evaluate(fallback)

    if not best:
        return False, None, last_reason

    aisle, module, shelf = best["aisle"], best["module"], best["shelf"]

    desired_facing = preferred_facing(p, shelf)
    f = fit_facing(p, shelf)
    if f <= 0:
        return False, None, "capacity_not_fit"
    u = used_width(p, shelf, f)
    cap_units = total_capacity_units(p, shelf, f)
    cov = coverage_days(p, shelf, f)
    utilization_after = (num(shelf.get("used_width_cm"), 0) + u) / max(num(shelf.get("shelf_width_cm"), 100), 1)
    brand_block_id = f"{norm(category_l1(p))}::{norm(brand(p))}".strip(":") or "unknown"

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
        "desired_facing": desired_facing,
        "facing_reduced": f < desired_facing,
        "used_width_cm": round(u, 1),
        "depth_units": depth_units(p, shelf),
        "total_capacity_units": cap_units,
        "placed_units": cap_units,
        "coverage_days": cov,
        "dimension_source": p.get("dimension_source"),
        "dimension_confidence": p.get("dimension_confidence"),
        "dimension_reason": p.get("dimension_reason"),
        "source_facing": p.get("source_facing", 0),
        "input_quality": p.get("input_quality", {}),
        "aisle": aisle.get("aisle_id"),
        "aisle_id": aisle.get("aisle_id"),
        "module_id": module.get("module_id"),
        "shelf_no": shelf.get("shelf_no"),
        "position_order": len(shelf.get("products", [])) + 1,
        "placement_score": round(best_score, 1),
        "brand_block_id": brand_block_id,
        "capacity_warning": utilization_after >= 0.90 or f < desired_facing,
        "placement_reason": {
            "storage": "storage_compatible",
            "rule": "module_and_shelf_rules_passed",
            "merchandising": "same_brand_or_category_clustered" if shelf.get("products") else "new_compatible_block",
            "facing": "reduced_to_physical_capacity" if f < desired_facing else "sales_coverage_facing",
        },
    }

    shelf.setdefault("products", []).append(placed)
    shelf["used_width_cm"] = round(num(shelf.get("used_width_cm"), 0) + u, 1)
    shelf["used"] = shelf["used_width_cm"]
    shelf["used_weight_kg"] = round(num(shelf.get("used_weight_kg"), 0) + weight(p) * f, 2)

    aisle_groups.setdefault(clean_text(aisle.get("aisle_id")), set()).add(p.get("_merch_group"))
    state["remaining_width"] = max(0, state["remaining_width"] - u)
    state["recent"].append(best)
    if len(state["recent"]) > 32:
        del state["recent"][:-32]
    if product_brand:
        state["brand"].setdefault(product_brand, []).append(best)
    if product_category:
        state["category"].setdefault(product_category, []).append(best)
    best_index = int(best.get("pool_index", 0))
    remaining = num(shelf.get("shelf_width_cm"), 100) - num(shelf.get("used_width_cm"), 0)
    state["cursor"] = best_index if remaining + 1e-9 >= product_width_with_buffer else (best_index + 1) % pool_size

    return True, placed, "ok"

# =====================================================
# SUMMARY / DIAGNOSTICS
# =====================================================

def summarize(plan: Dict[str, Any], total_products: int, unplaced: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_width = 0
    used_width = 0
    capacity_warnings = []
    capacity_by_storage: Dict[str, Dict[str, float]] = {}
    placed_items = []

    for a in plan.get("aisles", []):
        for m in a.get("modules", []):
            for s in m.get("shelves", []):
                sw = num(s.get("shelf_width_cm"), 100)
                su = num(s.get("used_width_cm", s.get("used", 0)), 0)
                total_width += sw
                used_width += su

                storage = shelf_storage(s)
                bucket = capacity_by_storage.setdefault(storage, {"shelf_width_cm": 0.0, "used_width_cm": 0.0, "shelf_count": 0})
                bucket["shelf_width_cm"] += sw
                bucket["used_width_cm"] += su
                bucket["shelf_count"] += 1
                placed_items.extend(s.get("products", []) or [])

                util = su / max(sw, 1)
                if util >= 0.90:
                    capacity_warnings.append({
                        "aisle": a.get("aisle_id"),
                        "module_id": m.get("module_id"),
                        "shelf_no": s.get("shelf_no"),
                        "utilization_pct": round(util * 100),
                    })

    placed = total_products - len(unplaced)

    for bucket in capacity_by_storage.values():
        bucket["shelf_width_cm"] = round(bucket["shelf_width_cm"], 1)
        bucket["used_width_cm"] = round(bucket["used_width_cm"], 1)
        bucket["utilization_pct"] = round((bucket["used_width_cm"] / max(bucket["shelf_width_cm"], 1)) * 100, 2)
        bucket["shelf_count"] = int(bucket["shelf_count"])

    requested_facing_total = sum(inum(p.get("desired_facing"), 0) for p in placed_items)
    placed_facing_total = sum(placed_facing(p) for p in placed_items)

    return {
        "total": total_products,
        "placed": placed,
        "unplaced": len(unplaced),
        "total_products": total_products,
        "placed_products": placed,
        "unplaced_products": len(unplaced),
        "capacity_utilization_pct": round((used_width / max(total_width, 1)) * 100),
        "capacity_warnings": capacity_warnings,
        "capacity_by_storage": capacity_by_storage,
        "requested_facing_total": requested_facing_total,
        "placed_facing_total": placed_facing_total,
        "facing_reduced_count": sum(1 for p in placed_items if p.get("facing_reduced")),
        "facing_reduction_pct": safe_pct(
            requested_facing_total - placed_facing_total,
            requested_facing_total,
        ),
        "strategy": "sales + category + storage + brand cluster + depth coverage + picking route + ergonomics + master enrichment",
    }


def validate_planogram(plan: Dict[str, Any]) -> Dict[str, Any]:
    violations = []
    empty_shelves = []
    overfilled_shelves = []
    low_fill_shelves = []
    duplicate_skus = []
    seen_skus = set()

    for aisle in plan.get("aisles", []):
        aisle_id = aisle.get("aisle_id")
        for module in aisle.get("modules", []):

            for shelf in module.get("shelves", []):
                sw = num(shelf.get("shelf_width_cm"), 100)
                expected_width = 0.0
                expected_weight = 0.0
                shelf_groups = set()

                for product in shelf.get("products", []):
                    product_facing = placed_facing(product)
                    expected_width += used_width(product, shelf, product_facing)
                    expected_weight += weight(product) * product_facing
                    group = product.get("merch_group") or merch_group(product)
                    if group:
                        shelf_groups.add(group)

                su = expected_width
                util = su / max(sw, 1)

                base = {
                    "aisle_id": aisle_id,
                    "module_id": module.get("module_id"),
                    "shelf_no": shelf.get("shelf_no"),
                    "used_width_cm": round(su, 2),
                    "shelf_width_cm": round(sw, 2),
                    "used_weight_kg": round(expected_weight, 2),
                    "utilization_pct": round(util * 100, 2),
                    "product_count": len(shelf.get("products", [])),
                    "allowed_storage_type": shelf_storage(shelf),
                }

                stored_width = num(shelf.get("used_width_cm", shelf.get("used", 0)), 0)
                if abs(stored_width - expected_width) > 0.15:
                    violations.append({
                        **base,
                        "type": "capacity_counter_stale",
                        "stored_width_cm": round(stored_width, 2),
                        "calculated_width_cm": round(expected_width, 2),
                    })

                if not shelf.get("products"):
                    empty_shelves.append(base)
                elif util > 1:
                    overfilled_shelves.append(base)
                elif util < 0.35:
                    low_fill_shelves.append(base)

                for p in shelf.get("products", []):
                    p_sku = clean_text(p.get("sku"))
                    if p_sku and p_sku in seen_skus:
                        duplicate_skus.append({**base, "sku": p_sku, "type": "duplicate_sku"})
                    if p_sku:
                        seen_skus.add(p_sku)

                    if shelf_storage(shelf) != key(p.get("storage_type") or storage_type(p)):
                        violations.append({**base, "type": "storage_violation", "sku": p.get("sku"), "product_name": p.get("product_name")})

                    if key(aisle_id) == "A" and not is_food(p):
                        violations.append({
                            **base,
                            "type": "aisle_merchandising_violation",
                            "sku": p.get("sku"),
                            "product_name": p.get("product_name"),
                            "message": "A koridoru gıda dışı ürün kabul etmez.",
                        })

                    if not module_rule_matches(p, module):
                        violations.append({**base, "type": "module_rule_violation", "sku": p.get("sku"), "product_name": p.get("product_name"), "rule": module.get("assignment_rule")})

                    if not rule_matches_product(p, {
                        "allowed_categories": module.get("allowed_categories", []),
                        "blocked_categories": module.get("blocked_categories", []),
                    }, include_storage=False):
                        violations.append({**base, "type": "module_category_rule_violation", "sku": p.get("sku"), "product_name": p.get("product_name")})

                    shelf_rule = shelf.get("assignment_rule")
                    if shelf_rule and not rule_matches_product(p, shelf_rule):
                        violations.append({**base, "type": "shelf_rule_violation", "sku": p.get("sku"), "product_name": p.get("product_name"), "rule": shelf_rule})

                    if not rule_matches_product(p, {
                        "allowed_categories": shelf.get("allowed_categories", []),
                        "blocked_categories": shelf.get("blocked_categories", []),
                    }, include_storage=False):
                        violations.append({**base, "type": "shelf_category_rule_violation", "sku": p.get("sku"), "product_name": p.get("product_name")})

                    if not dimension_fit(p, shelf):
                        violations.append({**base, "type": "dimension_violation", "sku": p.get("sku"), "product_name": p.get("product_name")})

                    if not capacity_fit(p, {**shelf, "used_width_cm": 0, "used_weight_kg": 0}, placed_facing(p)) and used_width(p, shelf, placed_facing(p)) > sw:
                        violations.append({**base, "type": "product_width_violation", "sku": p.get("sku"), "product_name": p.get("product_name")})

                if "NON_FOOD_ODOR" in shelf_groups and any(str(group).startswith("FOOD") for group in shelf_groups):
                    violations.append({
                        **base,
                        "type": "food_cleaning_same_shelf",
                        "message": "Temizlik/kokulu ürün gıda ile aynı rafta olamaz.",
                    })

                max_weight = num(shelf.get("max_weight_kg"), 45)
                if expected_weight > max_weight + 1e-9:
                    violations.append({
                        **base,
                        "type": "weight_violation",
                        "max_weight_kg": round(max_weight, 2),
                    })

    return {
        "strict_rule_violations": violations,
        "rule_violations": violations,
        "empty_shelves": empty_shelves,
        "overfilled_shelves": overfilled_shelves,
        "low_fill_shelves": low_fill_shelves,
        "duplicate_skus": duplicate_skus,
        "summary": {
            "strict_rule_violation_count": len(violations),
            "empty_shelf_count": len(empty_shelves),
            "overfilled_shelf_count": len(overfilled_shelves),
            "low_fill_shelf_count": len(low_fill_shelves),
            "duplicate_sku_count": len(duplicate_skus),
            "valid": not violations and not duplicate_skus,
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
    progress_callback=None,
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
            norm(get(x, ["sku", "SKU", "barcode"], "")),
        )
    )[:MAX_PRODUCTS]


    clean_products = []
    unplaced = []
    alerts = {
        "approval_fire_products": [],
        "cdc_products": [],
        "dimension_missing": [],
        "storage_violations": [],
        "capacity_warnings": [],
        "low_coverage": [],
        "ai_dimension_low_confidence": [],
    }
    data_quality = {
        "missing_name": 0,
        "missing_brand": 0,
        "missing_category": 0,
        "missing_storage": 0,
        "missing_dimensions": 0,
        "ai_estimated_dimensions": 0,
        "localized_rows_normalized": 0,
    }

    seen_skus = set()
    total_input = len(raw_products)
    if progress_callback:
        progress_callback(0, total_input, "normalizing")
    for input_index, raw in enumerate(raw_products, start=1):
        p = enrich_product(raw, allow_ai_dimensions=allow_ai_dimensions)

        quality = p.get("input_quality") or {}
        data_quality["missing_name"] += int(not quality.get("name_present"))
        data_quality["missing_brand"] += int(not quality.get("brand_present"))
        data_quality["missing_category"] += int(not quality.get("category_present"))
        data_quality["missing_storage"] += int(not quality.get("storage_present"))
        data_quality["missing_dimensions"] += int(not quality.get("dimensions_present"))
        data_quality["ai_estimated_dimensions"] += int(p.get("dimension_source") == "ai_estimated")
        if any(_column_key(column) in INPUT_COLUMN_ALIASES for column in (raw or {}).keys()):
            data_quality["localized_rows_normalized"] += 1

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

        if p.get("is_cdc") or is_cdc_product(p):
            item = {
                "sku": sku(p),
                "product_name": product_name(p),
                "reason": "cdc_cross_dock_not_shelf_stock",
                "constraint_reason": "cdc_product_excluded",
                "suggested_action": "CDC/cross-dock ürün satış rafına yerleştirilmez; akış alanında yönetilir.",
            }
            unplaced.append(item)
            alerts["cdc_products"].append(item)
            continue

        if not sku(p):
            unplaced.append({
                "sku": None,
                "product_name": product_name(p),
                "reason": "missing_sku",
            })
            continue

        product_key = norm(sku(p))
        if product_key in seen_skus:
            unplaced.append({
                "sku": sku(p),
                "product_name": product_name(p),
                "reason": "duplicate_sku",
                "suggested_action": "Aynı SKU yalnızca bir kez yüklenmeli; katalog mükerrerini temizle.",
            })
            continue
        seen_skus.add(product_key)

        # ``width()/height()/depth()`` deliberately return safe fallback
        # values for legacy callers. Missing-dimension validation must inspect
        # the normalized fields directly instead of those accessors.
        if (
            p.get("dimension_source") == "missing"
            or num(p.get("width_cm"), 0) <= 0
            or num(p.get("height_cm"), 0) <= 0
            or num(p.get("depth_cm"), 0) <= 0
        ):
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
        if progress_callback and (input_index == total_input or input_index % 250 == 0):
            progress_callback(input_index, total_input, "normalizing")

    ranked = classify_products(clean_products)
    mode_key = key(mode or "HYBRID")
    storage_order = {"AMBIENT": 1, "CHILLED": 2, "FROZEN": 3, "PALLET": 4}

    def generation_order(p):
        storage_rank = storage_order.get(p.get("_storage"), 9)
        if "CATEGORY" in mode_key and "HYBRID" not in mode_key:
            return storage_rank, norm(category_l1(p)), norm(category_l2(p)), -p.get("_score", 0), norm(sku(p))
        if "ABC" in mode_key and "HYBRID" not in mode_key:
            return storage_rank, norm(p.get("_abc")), -p.get("_score", 0), norm(sku(p))
        if "BRAND" in mode_key and "HYBRID" not in mode_key:
            return storage_rank, norm(brand(p)), norm(category_l2(p)), -p.get("_score", 0), norm(sku(p))
        return storage_rank, -p.get("_score", 0), norm(category_l1(p)), norm(brand(p)), norm(sku(p))

    ranked = sorted(ranked, key=generation_order)

    shelf_pool, aisle_groups = build_shelf_index(plan)

    total_ranked = len(ranked)
    for placement_index, p in enumerate(ranked, start=1):
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
        if progress_callback and (placement_index == total_ranked or placement_index % 100 == 0):
            progress_callback(placement_index, total_ranked, "placing")

    summary = summarize(plan, len(raw_products), unplaced)
    alerts["capacity_warnings"] = summary["capacity_warnings"]

    diagnostics = validate_planogram(plan)
    if progress_callback:
        progress_callback(total_ranked, total_ranked, "finalizing")
    summary["strict_rule_violation_count"] = diagnostics["summary"]["strict_rule_violation_count"]
    summary["empty_shelf_count"] = diagnostics["summary"]["empty_shelf_count"]
    summary["unplaced_reason_counts"] = {
        reason: sum(1 for item in unplaced if item.get("reason") == reason or item.get("constraint_reason") == reason)
        for reason in sorted({item.get("reason") or item.get("constraint_reason") or "unknown" for item in unplaced})
    }
    summary["data_quality"] = data_quality

    return {
        "engine_version": "deterministic-best-fit-v4.2",
        "single_source_of_truth": True,
        "summary": summary,
        "planogram": plan,
        "unplaced": unplaced,
        "unplaced_products": unplaced,
        "alerts": alerts,
        "diagnostics": diagnostics,
        "insights": {
            "sales_optimization": "Yüksek satış ve yüksek stop oranlı ürünler ön koridorlara ve ergonomik raflara taşındı.",
            "category_logic": "Kategori ve marka blokları aynı raf/modül çevresinde tutulmaya çalışıldı.",
            "storage_logic": "CHILLED/FROZEN yalnızca uygun dolapta, 5 L ürünler yalnızca PALLET alanında tutuldu; CDC ürünler satış rafından çıkarıldı.",
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
                for position, p in enumerate(shelf.get("products", []), start=1):
                    fake = {**p, "_storage": p.get("storage_type"), "_tier": p.get("front_tier"), "_abc": p.get("abc_class")}
                    facing = placed_facing(fake)
                    desired_facing = preferred_facing(fake, shelf)
                    item_width = used_width(fake, shelf, facing)
                    su += item_width
                    sw += weight(fake) * facing
                    p["facing"] = facing
                    p["facing_count"] = facing
                    p["desired_facing"] = desired_facing
                    p["facing_reduced"] = facing < desired_facing
                    p["used_width_cm"] = round(item_width, 1)
                    p["placed_units"] = depth_units(fake, shelf) * facing
                    p["total_capacity_units"] = p["placed_units"]
                    p["position_order"] = position
                    p["capacity_warning"] = (su / max(num(shelf.get("shelf_width_cm"), 100), 1)) >= 0.90 or p["facing_reduced"]

                shelf["used_width_cm"] = round(su, 1)
                shelf["used"] = shelf["used_width_cm"]
                shelf["used_weight_kg"] = round(sw, 2)
                shelf_utilization = su / max(num(shelf.get("shelf_width_cm"), 100), 1)
                for p in shelf.get("products", []):
                    p["capacity_warning"] = bool(p.get("capacity_warning")) or shelf_utilization >= 0.90

    return plan


def add_product_to_shelf(plan: Dict[str, Any], product: Dict[str, Any], aisle_id: str, module_id: int, shelf_no: int, force: bool = False) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    p = enrich_product(product)

    aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)
    if not shelf:
        # Validate the destination before removing an existing SKU. A failed
        # drag/drop must never make a product disappear from the planogram.
        return {"status": "error", "message": "target_shelf_not_found", "planogram": next_plan}

    original_product = None
    original_location = None
    target_sku = clean_text(sku(p))
    if target_sku:
        for source_aisle in next_plan.get("aisles", []):
            for source_module in source_aisle.get("modules", []):
                for source_shelf in source_module.get("shelves", []):
                    for candidate in source_shelf.get("products", []):
                        if clean_text(candidate.get("sku")) == target_sku:
                            original_product = deepcopy(candidate)
                            original_location = (
                                source_aisle.get("aisle_id"),
                                source_module.get("module_id"),
                                source_shelf.get("shelf_no"),
                            )
                            break
                    if original_product:
                        break
                if original_product:
                    break
            if original_product:
                break

    if original_product:
        remove_product_from_plan(next_plan, target_sku)
        aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)

    def restore_original() -> None:
        if not original_product or not original_location:
            return
        old_aisle, old_module, old_shelf = original_location
        old_target = find_shelf(next_plan, old_aisle, old_module, old_shelf)
        if old_target[2] is not None and not find_product(next_plan, target_sku):
            old_target[2].setdefault("products", []).append(deepcopy(original_product))
            recalc_plan(next_plan)

    p = classify_products([p])[0]

    ok, reason = can_place(p, aisle, module, shelf, existing_groups_on_aisle(aisle))
    if not ok and not force:
        restore_original()
        return {
            "status": "error",
            "message": "product_cannot_fit_target_shelf",
            "reason": reason,
            "product": p,
            "planogram": next_plan,
        }

    desired_facing = preferred_facing(p, shelf)
    f = fit_facing(p, shelf)
    forced_warning = None
    if f <= 0 and force:
        f = max(1, min(12, desired_facing))
        forced_warning = reason
    elif f <= 0:
        restore_original()
        return {
            "status": "error",
            "message": "product_cannot_fit_target_shelf",
            "reason": "capacity_not_fit",
            "product": p,
            "planogram": next_plan,
        }

    u = used_width(p, shelf, f)
    utilization_after = (num(shelf.get("used_width_cm"), 0) + u) / max(num(shelf.get("shelf_width_cm"), 100), 1)
    brand_block_id = f"{norm(category_l1(p))}::{norm(brand(p))}".strip(":") or "unknown"

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
        "desired_facing": desired_facing,
        "facing_reduced": f < desired_facing,
        "used_width_cm": round(u, 1),
        "placed_units": depth_units(p, shelf) * f,
        "total_capacity_units": depth_units(p, shelf) * f,
        "aisle_id": aisle.get("aisle_id"),
        "module_id": module.get("module_id"),
        "shelf_no": shelf.get("shelf_no"),
        "position_order": len(shelf.get("products", [])) + 1,
        "brand_block_id": brand_block_id,
        "forced": bool(force and (not ok or forced_warning)),
        "capacity_warning": bool(forced_warning) or utilization_after >= 0.90 or f < desired_facing,
        "placement_reason": forced_warning or ("manual_target_with_rules_passed" if ok else "manual_target_forced"),
    }

    shelf.setdefault("products", []).append(placed)
    recalc_plan(next_plan)

    return {"status": "success", "planogram": next_plan, "product": placed}


def update_facing(plan: Dict[str, Any], target_sku: str, delta: int) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    p = find_product(next_plan, target_sku)

    if not p:
        return {"status": "error", "message": "sku_not_found", "planogram": next_plan}

    target_shelf = None
    for aisle in next_plan.get("aisles", []):
        for module in aisle.get("modules", []):
            for shelf in module.get("shelves", []):
                if p in shelf.get("products", []):
                    target_shelf = shelf
                    break
            if target_shelf:
                break
        if target_shelf:
            break

    old_facing = placed_facing(p)
    new_facing = max(1, min(12, old_facing + inum(delta)))
    if not target_shelf or new_facing == old_facing:
        return {"status": "success", "planogram": next_plan, "product": p}

    current_width = used_width(p, target_shelf, old_facing)
    current_weight = weight(p) * old_facing
    available_width = num(target_shelf.get("shelf_width_cm"), 100) - num(target_shelf.get("used_width_cm"), 0) + current_width
    available_weight = num(target_shelf.get("max_weight_kg"), 45) - num(target_shelf.get("used_weight_kg"), 0) + current_weight
    new_width = used_width(p, target_shelf, new_facing)
    new_weight = weight(p) * new_facing

    if new_width > available_width + 1e-9:
        return {"status": "error", "message": "facing_capacity_not_fit", "reason": "capacity_not_fit", "planogram": next_plan, "product": p}
    if new_weight > available_weight + 1e-9:
        return {"status": "error", "message": "facing_weight_not_fit", "reason": "weight_not_fit", "planogram": next_plan, "product": p}

    p["facing_count"] = new_facing
    p["facing"] = new_facing

    recalc_plan(next_plan)
    return {"status": "success", "planogram": next_plan, "product": p}


def rotate_product(plan: Dict[str, Any], target_sku: str) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    p = find_product(next_plan, target_sku)

    if not p:
        return {"status": "error", "message": "sku_not_found", "planogram": next_plan}

    previous = bool(p.get("is_rotated"))
    p["is_rotated"] = not previous
    recalc_plan(next_plan)

    diagnostics = validate_planogram(next_plan)
    if any(v.get("sku") == target_sku and v.get("type") in {"dimension_violation", "product_width_violation", "capacity_counter_stale"} for v in diagnostics.get("strict_rule_violations", [])):
        p["is_rotated"] = previous
        recalc_plan(next_plan)
        return {"status": "error", "message": "rotated_product_does_not_fit", "planogram": next_plan, "product": p}

    return {"status": "success", "planogram": next_plan, "product": p}


def move_product(plan: Dict[str, Any], target_sku: str, aisle_id: str, module_id: int, shelf_no: int, force: bool = False) -> Dict[str, Any]:
    next_plan = deepcopy(plan)
    removed = remove_product_from_plan(next_plan, target_sku)

    if not removed:
        return {"status": "error", "message": "sku_not_found", "planogram": next_plan}

    result = add_product_to_shelf(next_plan, removed, aisle_id, module_id, shelf_no, force=force)
    if result.get("status") == "success":
        return result

    # A failed move must never make the SKU disappear from the plan.
    source = find_shelf(
        next_plan,
        removed.get("aisle_id"),
        removed.get("module_id"),
        removed.get("shelf_no"),
    )
    if source[2] is not None:
        source[2].setdefault("products", []).append(removed)
        recalc_plan(next_plan)
    result["planogram"] = next_plan
    result["restored_original_location"] = True
    return result


def apply_module_rule(layout: Dict[str, Any], aisle_id: str, module_id: int, rule: Dict[str, Any]) -> Dict[str, Any]:
    next_layout = deepcopy(layout)
    normalized_rule = deepcopy(rule or {})

    for aisle in next_layout.get("aisles", []):
        if clean_text(aisle.get("aisle_id")) != clean_text(aisle_id):
            continue
        for module in aisle.get("modules", []):
            if inum(module.get("module_id")) == inum(module_id):
                module["assignment_rule"] = normalized_rule
                if "allowed_categories" in normalized_rule:
                    module["allowed_categories"] = normalized_rule.get("allowed_categories") or []
                if "blocked_categories" in normalized_rule:
                    module["blocked_categories"] = normalized_rule.get("blocked_categories") or []

    return next_layout


def apply_shelf_rule(layout: Dict[str, Any], aisle_id: str, module_id: int, shelf_no: int, rule: Dict[str, Any]) -> Dict[str, Any]:
    next_layout = deepcopy(layout)
    _, _, shelf = find_shelf(next_layout, aisle_id, module_id, shelf_no)

    if shelf:
        normalized_rule = deepcopy(rule or {})
        shelf["assignment_rule"] = normalized_rule
        if normalized_rule.get("allowed_storage_type"):
            shelf["allowed_storage_type"] = normalized_rule["allowed_storage_type"]
        if "allowed_categories" in normalized_rule:
            shelf["allowed_categories"] = normalized_rule.get("allowed_categories") or []
        if "blocked_categories" in normalized_rule:
            shelf["blocked_categories"] = normalized_rule.get("blocked_categories") or []

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

        f = fit_facing(p, shelf)
        usage = used_width(p, shelf, f) if f > 0 else 0

        if f <= 0 or usage > remaining:
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
            "desired_facing": preferred_facing(p, shelf),
            "facing_reduced": f < preferred_facing(p, shelf),
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
    original_plan = deepcopy(plan)
    next_plan = deepcopy(plan)
    aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)

    if not shelf:
        return {"status": "error", "message": "shelf_not_found", "planogram": next_plan}

    # Build transactionally. Block Studio must use the same hard-rule checks
    # as normal placement and must never leave a partially rebuilt shelf.
    shelf["products"] = []
    shelf["used_width_cm"] = 0
    shelf["used_weight_kg"] = 0
    shelf["used"] = 0
    recalc_plan(next_plan)
    aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)

    shelf_width = num(shelf.get("shelf_width_cm"), 100)
    block_results = []
    rejected_total = []
    seen_block_skus = set()

    for block in blocks:
        block_width = shelf_width * max(0, num(block.get("width_pct"), 0)) / 100
        block_products = [classify_products([enrich_product(p)])[0] for p in block.get("products", [])]
        block_products.sort(key=product_score, reverse=True)

        used = 0
        accepted = []
        rejected = []

        for p in block_products:
            product_sku = clean_text(sku(p))
            if product_sku in seen_block_skus:
                rejected.append({
                    "sku": product_sku,
                    "product_name": product_name(p),
                    "reason": "duplicate_sku_in_blocks",
                })
                continue
            seen_block_skus.add(product_sku)

            aisle, module, shelf = find_shelf(next_plan, aisle_id, module_id, shelf_no)
            ok, rule_reason = can_place(p, aisle, module, shelf, existing_groups_on_aisle(aisle))
            f = fit_facing(p, shelf)
            usage = used_width(p, shelf, f) if f > 0 else 0

            if not ok or f <= 0 or used + usage > block_width:
                rejected.append({
                    "sku": sku(p),
                    "product_name": product_name(p),
                    "reason": rule_reason if not ok else "block_capacity_not_enough",
                    "needed_width_cm": round(usage, 2),
                    "block_remaining_cm": round(block_width - used, 2),
                })
                continue

            result = add_product_to_shelf(next_plan, p, aisle_id, module_id, shelf_no, force=False)
            if result.get("status") != "success":
                rejected.append({
                    "sku": sku(p),
                    "product_name": product_name(p),
                    "reason": result.get("reason") or result.get("message") or "product_cannot_fit_target_shelf",
                })
                continue

            placed = result["product"]
            placed["block_name"] = block.get("name")
            accepted.append(placed)
            used += num(placed.get("used_width_cm"), usage)

        block_results.append({
            "block_name": block.get("name"),
            "block_width_cm": round(block_width, 2),
            "used_width_cm": round(used, 2),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejected": rejected,
        })
        rejected_total.extend(rejected)

    if rejected_total:
        return {
            "status": "error",
            "message": "block_commit_rejected",
            "reason": "Block içindeki tüm SKU'lar hard rule ve kapasite kontrollerini geçmelidir.",
            "planogram": original_plan,
            "block_results": block_results,
            "rejected": rejected_total,
            "committed": False,
        }

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
