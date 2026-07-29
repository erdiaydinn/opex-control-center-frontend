from pathlib import Path
import json
import math
import re
from typing import Any, Dict, Optional, Tuple

import pandas as pd

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

INPUT_CANDIDATES = [
    DATA_DIR / "catalog_export.csv",
    DATA_DIR / "master_products_raw.csv",
    DATA_DIR / "master_products.csv",
]

EXTERNAL_PATH = DATA_DIR / "external_product_dimensions.csv"
OVERRIDE_PATH = DATA_DIR / "product_dimension_overrides.json"

OUT_CSV = DATA_DIR / "master_products_cleaned.csv"
OUT_XLSX = DATA_DIR / "master_products_cleaned.xlsx"
OUT_REPORT = DATA_DIR / "master_products_cleaned_report.json"


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
    return (
        clean_text(v)
        .lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def to_num(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or clean_text(v) == "":
            return default
        x = float(str(v).replace(",", ".").replace("%", "").strip())
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def first(row: Dict[str, Any], names, default=""):
    lower = {str(k).lower().strip(): k for k in row.keys()}
    for n in names:
        if n in row and clean_text(row.get(n)):
            return row.get(n)
        real = lower.get(str(n).lower().strip())
        if real is not None and clean_text(row.get(real)):
            return row.get(real)
    return default


def valid_dim(w, h, d) -> bool:
    w, h, d = to_num(w), to_num(h), to_num(d)
    if w is None or h is None or d is None:
        return False
    if min(w, h, d) <= 2:
        return False
    if w > 120 or h > 160 or d > 120:
        return False
    vol = w * h * d
    if vol < 30 or vol > 250000:
        return False
    return True


def parse_weight_from_name_kg(name: str) -> Optional[float]:
    n = norm(name)
    # Take the biggest explicit package size, not "2'li" count.
    matches = re.findall(r"(\d+(?:[,.]\d+)?)\s*(kg|g|gr|ml|l|lt)\b", n)
    if not matches:
        return None
    vals = []
    for raw, unit in matches:
        val = float(raw.replace(",", "."))
        if unit in ["kg", "l", "lt"]:
            vals.append(val)
        elif unit in ["g", "gr", "ml"]:
            vals.append(val / 1000)
    return max(vals) if vals else None


def normalize_weight_kg(value, unit, name, package_type):
    parsed = parse_weight_from_name_kg(name)
    if parsed and 0 < parsed <= 30:
        return round(parsed, 3)

    v = to_num(value)
    u = norm(unit)
    if v is not None and v > 0:
        if u in ["g", "gr", "gram"]:
            return round(v / 1000, 3)
        if u in ["ml"]:
            return round(v / 1000, 3)
        if u in ["kg", "l", "lt"]:
            return round(v, 3)
        # If unit absent and value looks like gram/ml, convert.
        if v > 30:
            return round(v / 1000, 3)
        return round(v, 3)

    return FALLBACK_DIMS.get(package_type, FALLBACK_DIMS["unknown"])[3]


def clean_storage(row: Dict[str, Any]) -> str:
    """
    v3: preclean kolonunu bilerek kullanmıyoruz.
    Çünkü SQL preclean 'sütlü çikolata' / 'soğuk çay' gibi false positive üretiyor.
    """
    raw_storage = norm(row.get("storage_type_raw"))
    name = norm(row.get("product_name"))
    cat1 = norm(row.get("category_l1"))
    cat2 = norm(row.get("category_l2"))
    cat3 = norm(row.get("category_l3"))
    brand = norm(row.get("brand"))
    cat = f"{cat1} {cat2} {cat3}"
    hay = f"{raw_storage} {name} {cat} {brand}"

    if raw_storage in ["frozen", "freeze", "freezer", "-18"]:
        return "FROZEN"
    if raw_storage in ["chilled", "cold", "+4", "fridge"]:
        return "CHILLED"
    if raw_storage == "ambient":
        return "AMBIENT"

    # Strong frozen category/name signals
    if any(k in cat for k in ["dondurulmus", "dondurulmuş", "donuk", "dondurma", "frozen"]):
        return "FROZEN"
    if any(k in name for k in ["dondurma", "donuk", "dondurulmus", "dondurulmuş", "frozen", "algida", "la lorraine"]):
        # Prevent false-positive: buzdolabı poşeti etc.
        if "buzdolabi poseti" not in name and "buzdolabı poşeti" not in name:
            return "FROZEN"

    # Strong chilled categories
    chilled_cat_keywords = [
        "sut & sut", "süt & süt", "sut urun", "süt ürün",
        "ayran", "kefir", "yogurt", "yoğurt", "peynir",
        "et & balik", "et & balık", "sarkuteri", "şarküteri",
        "tavuk", "hindi", "balik", "balık"
    ]
    if any(k in cat for k in chilled_cat_keywords):
        return "CHILLED"

    # Strong chilled product names only when category is food/chilled-like.
    chilled_name_keywords = [
        "ayran", "kefir", "yogurt", "yoğurt", "labne",
        "beyaz peynir", "kasar", "kaşar", "tereyagi", "tereyağı",
        "sushi", "somon", "salmon", "tavuk", "hindi", "kofte", "köfte"
    ]
    if any(k in name for k in chilled_name_keywords):
        false_positive_terms = [
            "peynirli cips", "peynirli kraker", "peynir aromali", "peynir aromalı",
            "sütlü çikolata", "sutlu cikolata", "sutlu", "sütlü",
            "soğuk çay", "soguk cay", "iced tea", "ice tea",
            "buzdolabi poseti", "buzdolabı poşeti"
        ]
        if not any(fp in name for fp in false_positive_terms):
            return "CHILLED"

    return "AMBIENT"


def infer_package_type(row: Dict[str, Any]) -> str:
    raw = norm(
        f"{row.get('product_name','')} {row.get('category_l1','')} "
        f"{row.get('category_l2','')} {row.get('brand','')}"
    )
    if "damacana" in raw:
        return "demijohn"
    if any(k in raw for k in ["koli", "6x", "12x", "24x", "6 x", "12 x"]):
        return "case_pack"
    if any(k in raw for k in ["cips", "chips", "doritos", "lays", "ruffles", "paket"]):
        return "bag"
    if any(k in raw for k in ["sise", "şişe", "water", "su ", "cola", "kola", "fanta", "sprite", "ice tea", "gazoz", "ayran"]):
        return "bottle"
    if any(k in raw for k in ["kutu", "can", "konserve", "ton baligi"]):
        return "can_or_box"
    if any(k in raw for k in ["sut", "süt", "meyve suyu", "juice", "carton"]):
        return "carton"
    if any(k in raw for k in ["kavanoz", "jar", "sos", "recel", "bal", "zeytin", "tursu", "turşu"]):
        return "jar"
    if any(k in raw for k in ["sushi", "salata", "tabak", "tray", "kase"]):
        return "tray"
    if any(k in raw for k in ["deterjan", "sampuan", "şampuan", "temizleyici", "domestos"]):
        return "bottle"
    if any(k in raw for k in ["cikolata", "çikolata", "gofret", "bar"]):
        return "bar"
    if any(k in raw for k in ["dis fircasi", "diş fırçası", "askili", "hanging"]):
        return "hanging"
    return "unknown"


FALLBACK_DIMS = {
    "bag": (20, 30, 7, 0.18),
    "bottle": (8, 27, 8, 1.0),
    "case_pack": (34, 24, 24, 5.0),
    "demijohn": (28, 48, 28, 19.0),
    "can_or_box": (8, 12, 8, 0.4),
    "carton": (8, 22, 8, 1.0),
    "jar": (8, 12, 8, 0.5),
    "tray": (16, 5, 12, 0.3),
    "bar": (8, 16, 2.5, 0.08),
    "hanging": (8, 22, 3, 0.05),
    "unknown": (10, 18, 8, 0.25),
}


def weight_band(row: Dict[str, Any]) -> str:
    kg = normalize_weight_kg(row.get("weight_value_internal"), row.get("weight_unit_internal"), row.get("product_name"), row.get("package_type"))
    if kg <= 0.1:
        return "000-100"
    if kg <= 0.25:
        return "101-250"
    if kg <= 0.5:
        return "251-500"
    if kg <= 1:
        return "501-1000"
    if kg <= 2.5:
        return "1001-2500"
    return "2500+"


def family_key(row: Dict[str, Any]) -> str:
    return "|".join([
        norm(row.get("brand")),
        norm(row.get("category_l2")),
        clean_text(row.get("package_type")),
        weight_band(row),
    ])


def find_input_file() -> Path:
    for p in INPUT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Input yok: data/catalog_export.csv bekleniyor.")


def read_csv_any(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="utf-8", low_memory=False)


def normalize_catalog(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.where(pd.notnull(df), None).to_dict(orient="records")
    out = []
    for r in rows:
        sku = first(r, ["sku", "SKU", "product_sku", "item_sku"])
        barcode = first(r, ["barcode", "barcodes", "product_barcodes", "gtin", "ean"])
        name = first(r, ["product_name", "product_name_local", "pim_product_name_local", "product_name_english", "pim_product_name_english", "name"])
        brand = first(r, ["brand", "brand_name", "Brand"], "UNKNOWN")
        supplier = first(r, ["supplier", "supplier_name", "brand_owner_name_local", "brand_owner_name_english"])
        cat1 = first(r, ["category_l1", "frontend_category_local", "frontend_category", "pim_cat_l1", "level_one"], "GENERAL")
        cat2 = first(r, ["category_l2", "frontend_subcategory_local", "frontend_subcategory", "pim_cat_l2", "level_two"], "GENERAL")
        cat3 = first(r, ["category_l3", "pim_cat_l3", "level_three"])

        # CRITICAL: use raw catalog storage only; ignore storage_type_preclean alias.
        storage_raw = first(r, ["storage_type_raw"], "")
        if not storage_raw:
            storage_raw = first(r, ["storage_type"], "")

        width_i = first(r, ["width_cm_internal", "product_width_in_cm", "width_cm", "Width", "en"])
        height_i = first(r, ["height_cm_internal", "product_height_in_cm", "height_cm", "Height", "boy"])
        depth_i = first(r, ["depth_cm_internal", "product_length_in_cm", "depth_cm", "length_cm", "Depth", "derinlik"])
        weight_i = first(r, ["weight_value_internal", "product_weight_value", "weight_kg", "Weight", "agirlik", "ağırlık"])
        weight_unit = first(r, ["weight_unit_internal", "product_weight_unit", "weight_unit"], "")

        sales7 = first(r, ["sales_qty_7d", "sales_7d", "sales", "Sales 7D"], 0)
        sales30 = first(r, ["sales_qty_30d", "sales_30d"], 0)
        sales90 = first(r, ["sales_qty_90d", "sales_90d"], 0)
        freq30 = first(r, ["order_frequency_30d", "frequency_30d"], 0)

        out.append({
            **r,
            "sku": clean_text(sku),
            "barcode": clean_text(barcode),
            "product_name": clean_text(name),
            "brand": clean_text(brand) or "UNKNOWN",
            "supplier": clean_text(supplier),
            "category_l1": clean_text(cat1) or "GENERAL",
            "category_l2": clean_text(cat2) or "GENERAL",
            "category_l3": clean_text(cat3),
            "storage_type_raw": clean_text(storage_raw),
            "width_cm_internal": to_num(width_i),
            "height_cm_internal": to_num(height_i),
            "depth_cm_internal": to_num(depth_i),
            "weight_value_internal": to_num(weight_i),
            "weight_unit_internal": clean_text(weight_unit),
            "sales_qty_7d": to_num(sales7, 0) or 0,
            "sales_qty_30d": to_num(sales30, 0) or 0,
            "sales_qty_90d": to_num(sales90, 0) or 0,
            "order_frequency_30d": to_num(freq30, 0) or 0,
            "image_url": first(r, ["image_url", "catalog_image_url", "pim_image_url", "product_image_url"]),
        })

    nd = pd.DataFrame(out)
    nd["valid_dimension_flag"] = nd.apply(lambda x: 1 if valid_dim(x["width_cm_internal"], x["height_cm_internal"], x["depth_cm_internal"]) else 0, axis=1)
    nd["volume_cm3"] = nd.apply(lambda x: (to_num(x["width_cm_internal"], 0) or 0) * (to_num(x["height_cm_internal"], 0) or 0) * (to_num(x["depth_cm_internal"], 0) or 0), axis=1)
    nd = nd.sort_values(["sku", "valid_dimension_flag", "volume_cm3"], ascending=[True, False, False])
    nd = nd.drop_duplicates("sku", keep="first")
    nd = nd[nd["sku"].astype(str).str.len() > 0]
    return nd


def read_external() -> pd.DataFrame:
    if not EXTERNAL_PATH.exists():
        return pd.DataFrame()
    df = read_csv_any(EXTERNAL_PATH).where(pd.notnull(read_csv_any(EXTERNAL_PATH)), None)
    rename_map = {}
    for c in df.columns:
        cl = c.lower().strip()
        if cl in ["gtin", "ean", "barcode", "barcodes"]:
            rename_map[c] = "barcode"
        elif cl == "sku":
            rename_map[c] = "sku"
        elif cl in ["width", "width_cm", "en"]:
            rename_map[c] = "width_cm_external"
        elif cl in ["height", "height_cm", "boy"]:
            rename_map[c] = "height_cm_external"
        elif cl in ["depth", "depth_cm", "length", "length_cm", "derinlik"]:
            rename_map[c] = "depth_cm_external"
        elif cl in ["weight", "weight_kg", "agirlik", "ağırlık"]:
            rename_map[c] = "weight_kg_external"
        elif cl in ["image", "image_url", "product_image_url"]:
            rename_map[c] = "image_url_external"
        elif cl in ["source", "data_source"]:
            rename_map[c] = "external_source"
    return df.rename(columns=rename_map)


def read_overrides() -> Dict[str, Dict[str, Any]]:
    if not OVERRIDE_PATH.exists():
        return {}
    try:
        return json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def merge_external(df: pd.DataFrame, ext: pd.DataFrame) -> pd.DataFrame:
    for c in ["width_cm_external", "height_cm_external", "depth_cm_external", "weight_kg_external", "image_url_external", "external_source"]:
        if c not in df.columns:
            df[c] = None
    if ext.empty:
        return df

    ext = ext.copy()
    ext["sku_key"] = ext["sku"].apply(norm) if "sku" in ext.columns else ""
    ext["barcode_key"] = ext["barcode"].apply(norm) if "barcode" in ext.columns else ""
    df["sku_key"] = df["sku"].apply(norm)
    df["barcode_key"] = df["barcode"].apply(norm)

    for key in ["sku_key", "barcode_key"]:
        ext_key = ext[ext[key] != ""].drop_duplicates(key)
        if ext_key.empty:
            continue
        cols = [key] + [c for c in ["width_cm_external", "height_cm_external", "depth_cm_external", "weight_kg_external", "image_url_external", "external_source"] if c in ext_key.columns]
        df = df.merge(ext_key[cols], on=key, how="left", suffixes=("", f"_{key}"))
        for c in ["width_cm_external", "height_cm_external", "depth_cm_external", "weight_kg_external", "image_url_external", "external_source"]:
            cs = f"{c}_{key}"
            if cs in df.columns:
                df[c] = df[c].where(df[c].notna(), df[cs])
                df = df.drop(columns=[cs])
    return df


def choose_dimensions(row: Dict[str, Any], family_medians: Dict[str, Tuple[float, float, float]], overrides: Dict[str, Dict[str, Any]]):
    sku = clean_text(row.get("sku"))
    barcode = clean_text(row.get("barcode"))

    for k in [sku, barcode]:
        if k and k in overrides:
            ov = overrides[k]
            w, h, d = ov.get("width_cm"), ov.get("height_cm"), ov.get("depth_cm")
            if valid_dim(w, h, d):
                return (to_num(w), to_num(h), to_num(d), to_num(ov.get("weight_kg"), 0.25), "user_approved", 1.00, "user_override", False)

    iw, ih, id_ = row.get("width_cm_internal"), row.get("height_cm_internal"), row.get("depth_cm_internal")
    ew, eh, ed = row.get("width_cm_external"), row.get("height_cm_external"), row.get("depth_cm_external")
    internal_valid = valid_dim(iw, ih, id_)
    external_valid = valid_dim(ew, eh, ed)
    ivol = to_num(iw, 0) * to_num(ih, 0) * to_num(id_, 0) if internal_valid else 0
    evol = to_num(ew, 0) * to_num(eh, 0) * to_num(ed, 0) if external_valid else 0

    weight_kg = normalize_weight_kg(row.get("weight_value_internal"), row.get("weight_unit_internal"), row.get("product_name"), row.get("package_type"))

    if external_valid and internal_valid:
        if evol >= ivol * 1.08 and evol <= ivol * 3.0:
            return to_num(ew), to_num(eh), to_num(ed), weight_kg, "external_larger_safe", 0.86, "external_bigger_than_internal", False
        if evol > ivol * 3.0:
            return to_num(iw), to_num(ih), to_num(id_), weight_kg, "internal_catalog", 0.72, "external_maybe_case_dimension", True
        return to_num(iw), to_num(ih), to_num(id_), weight_kg, "internal_catalog", 0.76, "internal_and_external_close", False

    if external_valid:
        return to_num(ew), to_num(eh), to_num(ed), weight_kg, "external", 0.82, "internal_missing_or_dirty", False

    if internal_valid:
        fk = row.get("family_key")
        if fk in family_medians:
            mw, mh, md = family_medians[fk]
            mvol = mw * mh * md
            if ivol > 0 and (ivol < mvol * 0.35 or ivol > mvol * 2.8):
                return mw, mh, md, weight_kg, "family_median_ai", 0.66, "internal_family_anomaly", True
        return to_num(iw), to_num(ih), to_num(id_), weight_kg, "internal_catalog", 0.70, "internal_valid", False

    fk = row.get("family_key")
    if fk in family_medians:
        mw, mh, md = family_medians[fk]
        return mw, mh, md, weight_kg, "family_median_ai", 0.62, "internal_missing_family_median_used", True

    pt = row.get("package_type") or "unknown"
    fw, fh, fd, _ = FALLBACK_DIMS.get(pt, FALLBACK_DIMS["unknown"])
    return fw, fh, fd, weight_kg, "category_package_fallback", 0.38, "needs_measurement_fallback", True


def abc_class(df: pd.DataFrame) -> pd.Series:
    score = (
        df["sales_qty_7d"].fillna(0).astype(float) * 0.50 +
        (df["sales_qty_30d"].fillna(0).astype(float) / 30 * 7) * 0.35 +
        (df["sales_qty_90d"].fillna(0).astype(float) / 90 * 7) * 0.15 +
        df["order_frequency_30d"].fillna(0).astype(float) * 0.05
    )
    if score.sum() <= 0:
        return pd.Series(["D"] * len(df), index=df.index)
    ranks = score.rank(method="first", ascending=False, pct=True)
    return ranks.apply(lambda r: "A" if r <= 0.15 else "B" if r <= 0.50 else "C" if r <= 0.90 else "D")


def build_cleaned(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["package_type"] = df.apply(lambda r: infer_package_type(r.to_dict()), axis=1)
    df["storage_type_clean"] = df.apply(lambda r: clean_storage(r.to_dict()), axis=1)
    df["family_key"] = df.apply(lambda r: family_key(r.to_dict()), axis=1)

    ext = read_external()
    df = merge_external(df, ext)
    overrides = read_overrides()

    valid = df[df.apply(lambda r: valid_dim(r.get("width_cm_internal"), r.get("height_cm_internal"), r.get("depth_cm_internal")), axis=1)].copy()
    family_medians = {}
    if not valid.empty:
        for fk, g in valid.groupby("family_key"):
            if clean_text(fk) and len(g) >= 3:
                family_medians[fk] = (
                    float(g["width_cm_internal"].median()),
                    float(g["height_cm_internal"].median()),
                    float(g["depth_cm_internal"].median()),
                )

    choices = df.apply(lambda r: choose_dimensions(r.to_dict(), family_medians, overrides), axis=1)
    df["final_width_cm"] = choices.apply(lambda x: round(float(x[0]), 2))
    df["final_height_cm"] = choices.apply(lambda x: round(float(x[1]), 2))
    df["final_depth_cm"] = choices.apply(lambda x: round(float(x[2]), 2))
    df["final_weight_kg"] = choices.apply(lambda x: round(float(x[3] or 0.25), 3))
    df["dimension_source"] = choices.apply(lambda x: x[4])
    df["dimension_confidence"] = choices.apply(lambda x: round(float(x[5]), 2))
    df["dimension_issue"] = choices.apply(lambda x: x[6])
    df["needs_user_measurement"] = choices.apply(lambda x: bool(x[7]))

    df["daily_sales"] = (
        df["sales_qty_7d"].fillna(0).astype(float) / 7 * 0.50 +
        df["sales_qty_30d"].fillna(0).astype(float) / 30 * 0.35 +
        df["sales_qty_90d"].fillna(0).astype(float) / 90 * 0.15
    ).round(3)
    df["abc_class"] = abc_class(df)

    df["width_cm"] = df["final_width_cm"]
    df["height_cm"] = df["final_height_cm"]
    df["depth_cm"] = df["final_depth_cm"]
    df["weight_kg"] = df["final_weight_kg"]
    df["storage_type"] = df["storage_type_clean"]

    if "image_url_external" in df.columns:
        df["image_url"] = df["image_url"].where(df["image_url"].notna() & (df["image_url"].astype(str) != ""), df["image_url_external"])

    wanted = [
        "sku", "barcode", "product_name", "brand", "supplier",
        "category_l1", "category_l2", "category_l3",
        "storage_type_raw", "storage_type_clean", "storage_type",
        "package_type", "family_key",
        "width_cm_internal", "height_cm_internal", "depth_cm_internal",
        "width_cm_external", "height_cm_external", "depth_cm_external",
        "final_width_cm", "final_height_cm", "final_depth_cm",
        "width_cm", "height_cm", "depth_cm",
        "weight_value_internal", "weight_unit_internal", "final_weight_kg", "weight_kg",
        "dimension_source", "dimension_confidence", "dimension_issue", "needs_user_measurement",
        "image_url",
        "sales_qty_7d", "sales_qty_30d", "sales_qty_90d", "order_frequency_30d",
        "daily_sales", "abc_class",
    ]
    for c in wanted:
        if c not in df.columns:
            df[c] = None
    return df[wanted].sort_values(["abc_class", "daily_sales", "storage_type_clean"], ascending=[True, False, True])


def main():
    inp = find_input_file()
    print(f"Input okunuyor: {inp}")
    raw = read_csv_any(inp)
    print(f"Raw satır: {len(raw):,}")

    print("Catalog normalize/dedup çalışıyor...")
    catalog = normalize_catalog(raw)
    print(f"SKU tekil satır: {len(catalog):,}")

    print("Product Data Quality AI v3 temizliği çalışıyor...")
    cleaned = build_cleaned(catalog)

    cleaned.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    try:
        cleaned.to_excel(OUT_XLSX, index=False)
    except Exception:
        pass

    report = {
        "mode": "LOCAL_ONLY_V3_STORAGE_WEIGHT_FIX",
        "input": str(inp),
        "raw_rows": int(len(raw)),
        "rows": int(len(cleaned)),
        "output_csv": str(OUT_CSV),
        "output_xlsx": str(OUT_XLSX),
        "dimension_sources": cleaned["dimension_source"].value_counts(dropna=False).to_dict(),
        "storage_types": cleaned["storage_type_clean"].value_counts(dropna=False).to_dict(),
        "needs_user_measurement_count": int(cleaned["needs_user_measurement"].sum()),
        "low_confidence_count": int((cleaned["dimension_confidence"] < 0.55).sum()),
        "abc": cleaned["abc_class"].value_counts(dropna=False).to_dict(),
        "important_note": "Catalog physical dimension columns are not reliable: mostly 0/1 or content grams/ml. Fallback dimensions used until external/user measurements are loaded.",
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Tamamlandı.")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
