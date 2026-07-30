import os
import re
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


# =====================================================
# PLONAGRAM CLEAN MASTER BUILDER
# Input : data/master_products.csv OR data/master_products.xlsx
# Output: data/master_products_cleaned.csv
#
# Goal:
# - Ham catalog'u doğrudan engine'e vermemek
# - Bundle / inactive / ölçüsüz / storage belirsiz ürünleri işaretlemek
# - Aynı ürün/same SKU varyasyonlarını daha güvenilir tek kayda indirmek
# - Planogram motoruna "operational product master" üretmek
# =====================================================

DATA_DIR = Path(__file__).resolve().parent / "data"
INPUT_CSV = DATA_DIR / "master_products.csv"
INPUT_XLSX = DATA_DIR / "master_products.xlsx"
OUTPUT_CSV = DATA_DIR / "master_products_cleaned.csv"
QUALITY_REPORT_CSV = DATA_DIR / "master_products_quality_report.csv"


def clean_text(v: Any) -> str:
    if v is None:
        return ""
    try:
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    return str(v).strip()


def norm(v: Any) -> str:
    s = clean_text(v).lower()
    tr_map = str.maketrans({
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
        "İ": "i",
    })
    s = s.translate(tr_map)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def key(v: Any) -> str:
    return norm(v).upper()


def num(v: Any, d: float = 0.0) -> float:
    try:
        if v is None:
            return d
        s = clean_text(v)
        if not s:
            return d
        return float(s.replace(",", ".").replace("%", ""))
    except Exception:
        return d


def boolish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = norm(v)
    return s in {"true", "1", "yes", "y", "evet", "aktif", "active"}


def first_non_empty(*values: Any) -> str:
    for v in values:
        s = clean_text(v)
        if s:
            return s
    return ""


def get(row: Dict[str, Any], names: List[str], default: Any = "") -> Any:
    for n in names:
        if n in row and clean_text(row.get(n)):
            return row.get(n)

    lower = {str(k).lower(): k for k in row.keys()}
    for n in names:
        real = lower.get(str(n).lower())
        if real is not None and clean_text(row.get(real)):
            return row.get(real)

    return default


def first_barcode(v: Any) -> str:
    raw = clean_text(v)
    if not raw:
        return ""
    parts = re.split(r"[|;, ]+", raw)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[0] if parts else ""


def infer_brand(product_name: str, brand_name: str) -> Tuple[str, int, str]:
    b = clean_text(brand_name)
    if b:
        return b, 100, "catalog_brand"

    name = clean_text(product_name)
    if not name:
        return "UNKNOWN", 0, "missing_brand"

    # Basit ama pratik: ilk kelime çoğu FMCG'de marka sinyali verir.
    # İleride brand dictionary ile güçlendirilebilir.
    candidate = name.split(" ")[0].strip(" -_/|")
    if len(candidate) >= 2:
        return candidate, 45, "name_first_token_inferred"

    return "UNKNOWN", 0, "missing_brand"


def infer_category(row: Dict[str, Any]) -> Tuple[str, str, int, str]:
    c1 = first_non_empty(
        get(row, ["frontend_category_local"], ""),
        get(row, ["frontend_category"], ""),
        get(row, ["pim_cat_l1"], ""),
        get(row, ["category_l1"], ""),
        "GENERAL",
    )
    c2 = first_non_empty(
        get(row, ["frontend_subcategory_local"], ""),
        get(row, ["frontend_subcategory"], ""),
        get(row, ["pim_cat_l2"], ""),
        get(row, ["category_l2"], ""),
        "GENERAL",
    )

    if c1 != "GENERAL" and c2 != "GENERAL":
        return c1, c2, 100, "catalog_category"
    if c1 != "GENERAL" or c2 != "GENERAL":
        return c1, c2, 65, "partial_category"
    return c1, c2, 20, "missing_category"


def infer_storage(row: Dict[str, Any], product_name: str, category_l1: str, category_l2: str, brand: str) -> Tuple[str, int, str]:
    raw_storage = key(get(row, ["storage_type", "Storage Type", "Storage"], ""))

    if raw_storage in {"AMBIENT", "CHILLED", "FROZEN"}:
        return raw_storage, 100, "catalog_storage"

    hay = key(f"{product_name} {category_l1} {category_l2} {brand}")

    frozen_tokens = [
        "FROZEN", "DONUK", "-18", "DONDUR", "DONDURMA", "ICE CREAM",
        "FREEZER", "ALGIDA", "PIZZA DONUK"
    ]
    chilled_tokens = [
        "CHILLED", "COLD", "+4", "SOGUK", "SOĞUK", "SUT", "SÜT",
        "YOGURT", "YOĞURT", "PEYNIR", "PEYNİR", "ET", "TAVUK",
        "SARKUTERI", "ŞARKÜTERİ", "FRIDGE", "AYRAN", "KEFIR", "KEFİR"
    ]
    bakery_tokens = [
        "LA LORRAINE", "FIRIN", "BAKERY", "EKMEK", "KRUASAN", "CROISSANT"
    ]

    if any(t in hay for t in frozen_tokens):
        return "FROZEN", 80, "keyword_frozen"
    if any(t in hay for t in chilled_tokens):
        return "CHILLED", 75, "keyword_chilled"
    if any(t in hay for t in bakery_tokens):
        # Bakery flow ayrı karar motoruna sinyal; storage olarak çoğu operasyon ambient/frozen karışabilir.
        # Bu yüzden AMBIENT verip tag ile ayrıştırıyoruz.
        return "AMBIENT", 55, "keyword_bakery_flow"
    return "AMBIENT", 45, "default_ambient"


def estimate_dimensions(product_name: str, category_l1: str, category_l2: str, brand: str, storage: str) -> Tuple[float, float, float, float, int, str]:
    hay = norm(f"{product_name} {category_l1} {category_l2} {brand}")

    # width, height, depth, weight_kg, confidence, reason
    if any(x in hay for x in ["poset", "poşet", "shopping bag", "bag"]):
        return 18, 28, 2, 0.02, 70, "estimated_shopping_bag"

    if "su" in hay or "water" in hay:
        if any(x in hay for x in ["5l", "5 l", "10l", "10 l"]):
            return 24, 36, 24, 5.0, 65, "estimated_large_water"
        return 8, 28, 8, 1.0, 60, "estimated_water_bottle"

    if any(x in hay for x in ["cola", "kola", "fanta", "sprite", "icecek", "içecek", "beverage"]):
        return 9, 28, 9, 1.0, 55, "estimated_beverage"

    if any(x in hay for x in ["cips", "chips", "ruffles", "lays", "doritos"]):
        return 18, 25, 6, 0.12, 55, "estimated_chips_bag"

    if any(x in hay for x in ["cikolata", "çikolata", "chocolate"]):
        return 8, 16, 2, 0.08, 55, "estimated_chocolate_bar"

    if storage == "CHILLED":
        return 10, 18, 10, 0.5, 45, "estimated_chilled_generic"

    if storage == "FROZEN":
        return 14, 16, 12, 0.5, 40, "estimated_frozen_generic"

    return 10, 20, 10, 0.3, 30, "estimated_generic"


def normalize_weight_kg(value: Any, unit: Any) -> Tuple[float, str]:
    v = num(value, 0)
    u = key(unit)

    if v <= 0:
        return 0.0, "missing_weight"

    if u in {"KG", "KILOGRAM", "KILOGRAMS"}:
        return round(v, 4), "catalog_weight_kg"

    if u in {"G", "GR", "GRAM", "GRAMS", "GRAMME"}:
        return round(v / 1000, 4), "catalog_weight_g_to_kg"

    # Catalog bazen unit boşken değer gram gibi gelebiliyor.
    if v > 50:
        return round(v / 1000, 4), "assumed_gram_to_kg"

    return round(v, 4), "assumed_kg"


def dimension_quality(w: float, h: float, d: float, source: str, estimate_conf: int = 0) -> Tuple[int, str]:
    present = sum(1 for x in [w, h, d] if x and x > 0)

    if source == "catalog_dimensions" and present == 3:
        # Aşırı uçları yakala.
        if w > 300 or h > 300 or d > 300:
            return 55, "catalog_dimensions_outlier_check"
        return 100, "catalog_dimensions_complete"

    if source == "partial_catalog_plus_estimate":
        return 65, "partial_catalog_dimensions"

    if present == 3 and source.startswith("estimated"):
        return estimate_conf, source

    return 0, "missing_dimensions"


def derive_merch_flags(product_name: str, category_l1: str, category_l2: str, brand: str, storage: str) -> Dict[str, Any]:
    hay = key(f"{product_name} {category_l1} {category_l2} {brand}")

    is_bakery_flow = any(x in hay for x in ["LA LORRAINE", "FIRIN", "BAKERY", "KRUASAN", "CROISSANT"])
    is_water = bool(re.search(r"(^|\s)SU(\s|$)", hay)) or "WATER" in hay
    is_dispatch_supply = any(x in hay for x in ["POSET", "POŞET", "BAG", "SHOPPING BAG"])
    is_odor = any(x in hay for x in [
        "DOMESTOS", "DETERJAN", "TEMIZ", "TEMİZ", "BLEACH", "ÇAMAŞIR", "CAMASIR",
        "YUMUSATICI", "YUMUŞATICI", "CLEANING", "SOAP", "ŞAMPUAN", "SHAMPOO",
        "TUVALET", "BANYO", "MUTFAK", "KIREC", "KİREÇ"
    ])
    is_nonfood_neutral = any(x in hay for x in [
        "DISPOSABLE", "PET", "HOME", "PEÇETE", "PECETE", "KAĞIT", "KAGIT", "FOIL", "STREÇ", "STREC"
    ])

    if storage == "CHILLED":
        merch_group = "FOOD_CHILLED"
    elif storage == "FROZEN":
        merch_group = "FOOD_FROZEN"
    elif is_odor:
        merch_group = "NON_FOOD_ODOR"
    elif is_nonfood_neutral or is_dispatch_supply:
        merch_group = "NON_FOOD_NEUTRAL"
    else:
        merch_group = "FOOD_AMBIENT"

    return {
        "is_bakery_flow": is_bakery_flow,
        "is_water": is_water,
        "is_dispatch_supply": is_dispatch_supply,
        "is_odor": is_odor,
        "merch_group": merch_group,
    }


def load_raw() -> pd.DataFrame:
    if INPUT_XLSX.exists():
        return pd.read_excel(INPUT_XLSX)
    if INPUT_CSV.exists():
        try:
            return pd.read_csv(INPUT_CSV)
        except UnicodeDecodeError:
            return pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    raise FileNotFoundError(f"Master bulunamadı: {INPUT_CSV} veya {INPUT_XLSX}")


def choose_best_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aynı planogram_product_key içinde en iyi kaydı seçer.
    Öncelik:
    - aktif
    - bundle değil
    - ölçü dolu
    - kategori/storage dolu
    - güncel
    """
    work = df.copy()
    work = work.where(pd.notnull(work), None)

    def score_row(r: pd.Series) -> float:
        row = r.to_dict()
        active = boolish(get(row, ["is_vendor_product_active"], False))
        bundle = boolish(get(row, ["is_bundle"], False))

        w = num(get(row, ["product_width_in_cm", "width_cm"], 0), 0)
        h = num(get(row, ["product_height_in_cm", "height_cm"], 0), 0)
        d = num(get(row, ["product_length_in_cm", "depth_cm"], 0), 0)
        dim_score = sum(1 for x in [w, h, d] if x > 0) * 20

        cat_score = 15 if clean_text(get(row, ["frontend_category_local", "pim_cat_l1"], "")) else 0
        st_score = 15 if clean_text(get(row, ["storage_type"], "")) else 0
        image_score = 5 if clean_text(get(row, ["image_url", "catalog_image_url", "pim_image_url"], "")) else 0

        price = num(get(row, ["catalog_price_local"], 0), 0)
        price_score = 3 if price > 0 else 0

        return (
            (100 if active else 0)
            + (-80 if bundle else 0)
            + dim_score
            + cat_score
            + st_score
            + image_score
            + price_score
        )

    if "planogram_product_key" not in work.columns:
        work["planogram_product_key"] = work.apply(lambda r: fallback_product_key(r.to_dict()), axis=1)

    work["_quality_pick_score"] = work.apply(score_row, axis=1)
    if "product_updated_date_local" in work.columns:
        work["_updated_sort"] = pd.to_datetime(work["product_updated_date_local"], errors="coerce")
    else:
        work["_updated_sort"] = pd.NaT

    work = work.sort_values(
        by=["planogram_product_key", "_quality_pick_score", "_updated_sort"],
        ascending=[True, False, False],
    )

    return work.groupby("planogram_product_key", as_index=False).head(1).drop(columns=["_quality_pick_score", "_updated_sort"], errors="ignore")


def fallback_product_key(row: Dict[str, Any]) -> str:
    product_name = norm(first_non_empty(
        get(row, ["product_name", "product_name_local", "pim_product_name_local", "product_name_english"], ""),
        get(row, ["sku"], ""),
    ))
    brand = norm(get(row, ["brand_name", "brand"], ""))
    c1 = norm(get(row, ["frontend_category_local", "pim_cat_l1", "category_l1"], ""))
    c2 = norm(get(row, ["frontend_subcategory_local", "pim_cat_l2", "category_l2"], ""))
    contents = norm(get(row, ["product_contents_value", "product_weight_value"], ""))
    unit = norm(get(row, ["product_contents_unit", "product_weight_unit"], ""))
    return f"{product_name}|{brand}|{contents}|{unit}|{c1}|{c2}"


def clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
    sku = clean_text(get(row, ["sku", "SKU"], ""))
    product_name = first_non_empty(
        get(row, ["product_name"], ""),
        get(row, ["product_name_local"], ""),
        get(row, ["pim_product_name_local"], ""),
        get(row, ["product_name_english"], ""),
        get(row, ["pim_product_name_english"], ""),
        sku,
    )

    brand, brand_conf, brand_source = infer_brand(product_name, get(row, ["brand_name", "brand"], ""))
    category_l1, category_l2, category_conf, category_source = infer_category(row)
    storage, storage_conf, storage_source = infer_storage(row, product_name, category_l1, category_l2, brand)

    raw_w = num(get(row, ["product_width_in_cm", "width_cm"], 0), 0)
    raw_h = num(get(row, ["product_height_in_cm", "height_cm"], 0), 0)
    raw_d = num(get(row, ["product_length_in_cm", "depth_cm"], 0), 0)

    weight_kg, weight_source = normalize_weight_kg(
        get(row, ["product_weight_value", "weight_kg"], 0),
        get(row, ["product_weight_unit"], ""),
    )

    est_w, est_h, est_d, est_weight, est_conf, est_reason = estimate_dimensions(
        product_name,
        category_l1,
        category_l2,
        brand,
        storage,
    )

    if raw_w > 0 and raw_h > 0 and raw_d > 0:
        w, h, d = raw_w, raw_h, raw_d
        dim_source = "catalog_dimensions"
        dim_conf, dim_reason = dimension_quality(w, h, d, dim_source)
    elif raw_w > 0 or raw_h > 0 or raw_d > 0:
        w = raw_w if raw_w > 0 else est_w
        h = raw_h if raw_h > 0 else est_h
        d = raw_d if raw_d > 0 else est_d
        dim_source = "partial_catalog_plus_estimate"
        dim_conf, dim_reason = dimension_quality(w, h, d, dim_source, est_conf)
    else:
        w, h, d = est_w, est_h, est_d
        dim_source = est_reason
        dim_conf, dim_reason = dimension_quality(w, h, d, dim_source, est_conf)

    if weight_kg <= 0:
        weight_kg = est_weight
        weight_source = "estimated_weight"

    volume_cm3 = round(w * h * d, 2) if w and h and d else 0

    is_bundle = boolish(get(row, ["is_bundle"], False))
    is_active = boolish(get(row, ["is_vendor_product_active"], False))
    vendor_status = clean_text(get(row, ["vendor_product_status"], ""))
    is_deleted_like = key(vendor_status) in {"DELETED", "BLOCKED"} and not is_active

    flags = derive_merch_flags(product_name, category_l1, category_l2, brand, storage)

    is_planogram_eligible = (
        bool(sku)
        and not is_bundle
        and is_active
        and dim_conf >= 30
        and storage in {"AMBIENT", "CHILLED", "FROZEN"}
    )

    # Genel güven skoru: engine bu skora göre AI tahmini riskini bilir.
    confidence = round(
        dim_conf * 0.40
        + storage_conf * 0.25
        + category_conf * 0.15
        + brand_conf * 0.10
        + (100 if is_planogram_eligible else 20) * 0.10,
        1,
    )

    risk_notes = []
    if is_bundle:
        risk_notes.append("bundle_excluded")
    if not is_active:
        risk_notes.append("inactive")
    if dim_conf < 60:
        risk_notes.append("low_dimension_confidence")
    if storage_conf < 60:
        risk_notes.append("low_storage_confidence")
    if category_conf < 60:
        risk_notes.append("low_category_confidence")
    if is_deleted_like:
        risk_notes.append("blocked_or_deleted_status")

    return {
        "sku": sku,
        "barcode": first_barcode(get(row, ["product_barcodes", "barcode", "Barcode"], "")),
        "product_barcodes": clean_text(get(row, ["product_barcodes", "barcode", "Barcode"], "")),
        "pim_product_id": clean_text(get(row, ["pim_product_id"], "")),
        "catalog_global_product_id": clean_text(get(row, ["catalog_global_product_id"], "")),
        "planogram_product_key": clean_text(get(row, ["planogram_product_key"], "")) or fallback_product_key(row),

        "product_name": product_name,
        "product_name_local": clean_text(get(row, ["product_name_local"], "")),
        "product_name_english": clean_text(get(row, ["product_name_english"], "")),

        "brand": brand,
        "brand_name": brand,
        "brand_owner_name_local": clean_text(get(row, ["brand_owner_name_local"], "")),
        "brand_confidence_score": brand_conf,
        "brand_source": brand_source,

        "category_l1": category_l1,
        "category_l2": category_l2,
        "frontend_category_local": category_l1,
        "frontend_subcategory_local": category_l2,
        "pim_cat_l1": clean_text(get(row, ["pim_cat_l1"], "")),
        "pim_cat_l2": clean_text(get(row, ["pim_cat_l2"], "")),
        "pim_cat_l3": clean_text(get(row, ["pim_cat_l3"], "")),
        "category_confidence_score": category_conf,
        "category_source": category_source,

        "storage_type": storage,
        "canonical_storage_type": storage,
        "storage_confidence_score": storage_conf,
        "storage_source": storage_source,

        "width_cm": round(w, 2),
        "height_cm": round(h, 2),
        "depth_cm": round(d, 2),
        "product_width_in_cm": round(w, 2),
        "product_height_in_cm": round(h, 2),
        "product_length_in_cm": round(d, 2),
        "product_volume_cm3": volume_cm3,
        "weight_kg": round(weight_kg, 4),
        "product_weight_value": round(weight_kg, 4),
        "product_weight_unit": "kg",
        "weight_source": weight_source,
        "dimension_confidence_score": dim_conf,
        "dimension_source": dim_source,
        "dimension_reason": dim_reason,

        "case_pack_qty": max(1, num(get(row, ["units_in_pack_count", "case_pack_qty", "case_pack"], 12), 12)),
        "units_in_pack_count": max(1, num(get(row, ["units_in_pack_count"], 12), 12)),

        "image_url": first_non_empty(
            get(row, ["image_url"], ""),
            get(row, ["catalog_image_url"], ""),
            get(row, ["pim_image_url"], ""),
        ),
        "catalog_price_local": num(get(row, ["catalog_price_local"], 0), 0),
        "catalog_original_price_local": num(get(row, ["catalog_original_price_local"], 0), 0),
        "vat_rate": num(get(row, ["vat_rate"], 0), 0),

        "is_fresh_product": boolish(get(row, ["is_fresh_product"], False)),
        "is_ultrafresh_product": boolish(get(row, ["is_ultrafresh_product"], False)),
        "is_weightable": boolish(get(row, ["is_weightable"], False)),
        "is_sold_by_weight": boolish(get(row, ["is_sold_by_weight"], False)),
        "is_sold_by_piece": boolish(get(row, ["is_sold_by_piece"], False)),
        "is_bundle": is_bundle,
        "bundle_name": clean_text(get(row, ["bundle_name"], "")),
        "is_vendor_product_active": is_active,
        "vendor_product_status": vendor_status,

        **flags,

        "is_planogram_eligible": is_planogram_eligible,
        "master_confidence_score": confidence,
        "risk_notes": "|".join(risk_notes),
        "merged_row_count": num(get(row, ["merged_row_count"], 1), 1),
        "merged_sku_count": num(get(row, ["merged_sku_count"], 1), 1),
        "product_created_date_local": clean_text(get(row, ["product_created_date_local"], "")),
        "product_updated_date_local": clean_text(get(row, ["product_updated_date_local"], "")),
    }


def build_quality_report(cleaned: pd.DataFrame, raw_count: int, picked_count: int) -> pd.DataFrame:
    rows = []

    def add(metric: str, value: Any):
        rows.append({"metric": metric, "value": value})

    add("raw_rows", raw_count)
    add("deduped_rows", picked_count)
    add("cleaned_rows", len(cleaned))
    add("eligible_rows", int(cleaned["is_planogram_eligible"].sum()))
    add("inactive_rows", int((cleaned["is_vendor_product_active"] == False).sum()))
    add("bundle_rows", int(cleaned["is_bundle"].sum()))
    add("low_dimension_confidence_lt_60", int((cleaned["dimension_confidence_score"] < 60).sum()))
    add("low_storage_confidence_lt_60", int((cleaned["storage_confidence_score"] < 60).sum()))
    add("missing_brand_unknown", int((cleaned["brand"] == "UNKNOWN").sum()))
    add("ambient_count", int((cleaned["storage_type"] == "AMBIENT").sum()))
    add("chilled_count", int((cleaned["storage_type"] == "CHILLED").sum()))
    add("frozen_count", int((cleaned["storage_type"] == "FROZEN").sum()))
    add("non_food_odor_count", int((cleaned["merch_group"] == "NON_FOOD_ODOR").sum()))
    add("water_count", int(cleaned["is_water"].sum()))
    add("bakery_flow_count", int(cleaned["is_bakery_flow"].sum()))
    add("avg_master_confidence_score", round(float(cleaned["master_confidence_score"].mean()), 2) if len(cleaned) else 0)

    return pd.DataFrame(rows)


def main():
    DATA_DIR.mkdir(exist_ok=True)

    raw = load_raw()
    raw = raw.where(pd.notnull(raw), None)

    best = choose_best_rows(raw)

    cleaned_rows = [clean_row(r) for r in best.to_dict(orient="records")]
    cleaned = pd.DataFrame(cleaned_rows)

    # Engine default master olarak bu dosyayı kullanacağı için en uygun kayıtlar üstte olsun.
    cleaned = cleaned.sort_values(
        by=["is_planogram_eligible", "master_confidence_score", "storage_type", "category_l1", "category_l2", "brand", "product_name"],
        ascending=[False, False, True, True, True, True, True],
    )

    cleaned.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    report = build_quality_report(cleaned, raw_count=len(raw), picked_count=len(best))
    report.to_csv(QUALITY_REPORT_CSV, index=False, encoding="utf-8-sig")

    print("✅ Plonagram clean master hazır.")
    print(f"Input rows       : {len(raw):,}")
    print(f"Deduped rows     : {len(best):,}")
    print(f"Output           : {OUTPUT_CSV}")
    print(f"Quality report   : {QUALITY_REPORT_CSV}")
    print("")
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
