from pathlib import Path
import json
import math
import re
import warnings
from typing import Any, Dict, Optional, Tuple

import pandas as pd
from google.cloud import bigquery
from google.auth.transport.requests import AuthorizedSession

try:
    from google.auth import default as google_default
except Exception:
    google_default = None

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except Exception:
    InstalledAppFlow = None

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


PROJECT_ID = "focal-furnace-389111"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

OUT_CSV = DATA_DIR / "master_products_cleaned.csv"
OUT_XLSX = DATA_DIR / "master_products_cleaned.xlsx"
OUT_REPORT = DATA_DIR / "master_products_cleaned_report.json"

EXTERNAL_PATH = DATA_DIR / "external_product_dimensions.csv"
OVERRIDE_PATH = DATA_DIR / "product_dimension_overrides.json"

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

# FAST + SSL FULL BYPASS VERSION
# - Catalog only
# - OAuth SSL verify disabled
# - BigQuery AuthorizedSession SSL verify disabled
# - No qc_orders scan
QUERY = r"""
WITH catalog_raw AS (
  SELECT
    CAST(sku AS STRING) AS sku,
    CAST(product_barcodes AS STRING) AS barcode,

    COALESCE(
      product_name_local,
      pim_product_name_local,
      product_name_english,
      pim_product_name_english
    ) AS product_name,

    brand_name AS brand,

    COALESCE(
      brand_owner_name_local,
      brand_owner_name_english
    ) AS supplier,

    COALESCE(frontend_category_local, frontend_category, pim_category_names.level_one) AS category_l1,
    COALESCE(frontend_subcategory_local, frontend_subcategory, pim_category_names.level_two) AS category_l2,
    COALESCE(pim_category_names.level_three, pim_category_names.level_four) AS category_l3,

    storage_type AS storage_type_raw,

    SAFE_CAST(product_width_in_cm AS FLOAT64) AS width_cm_internal,
    SAFE_CAST(product_height_in_cm AS FLOAT64) AS height_cm_internal,
    SAFE_CAST(product_length_in_cm AS FLOAT64) AS depth_cm_internal,
    SAFE_CAST(product_weight_value AS FLOAT64) AS weight_value_internal,
    product_weight_unit AS weight_unit_internal,

    CASE
      WHEN SAFE_CAST(product_width_in_cm AS FLOAT64) > 2
       AND SAFE_CAST(product_height_in_cm AS FLOAT64) > 2
       AND SAFE_CAST(product_length_in_cm AS FLOAT64) > 2
       AND SAFE_CAST(product_width_in_cm AS FLOAT64) <= 120
       AND SAFE_CAST(product_height_in_cm AS FLOAT64) <= 160
       AND SAFE_CAST(product_length_in_cm AS FLOAT64) <= 120
      THEN 1 ELSE 0
    END AS valid_dimension_flag,

    (
      COALESCE(SAFE_CAST(product_width_in_cm AS FLOAT64), 0)
      * COALESCE(SAFE_CAST(product_height_in_cm AS FLOAT64), 0)
      * COALESCE(SAFE_CAST(product_length_in_cm AS FLOAT64), 0)
    ) AS volume_cm3

  FROM `fulfillment-dwh-production.pandata_datamart.pandora__vendor_products_qcomm_catalog_details`
  WHERE global_entity_id = 'YS_TR'
    AND sku IS NOT NULL
),

catalog_best AS (
  SELECT * EXCEPT(rn)
  FROM (
    SELECT
      *,
      ROW_NUMBER() OVER (
        PARTITION BY sku
        ORDER BY
          valid_dimension_flag DESC,
          volume_cm3 DESC,
          LENGTH(COALESCE(product_name, "")) DESC
      ) AS rn
    FROM catalog_raw
  )
  WHERE rn = 1
)

SELECT
  sku,
  barcode,
  product_name,
  brand,
  supplier,
  category_l1,
  category_l2,
  category_l3,
  storage_type_raw,
  width_cm_internal,
  height_cm_internal,
  depth_cm_internal,
  weight_value_internal,
  weight_unit_internal,
  valid_dimension_flag,
  volume_cm3,
  0 AS sales_qty_7d,
  0 AS sales_qty_30d,
  0 AS sales_qty_90d,
  0 AS order_frequency_30d
FROM catalog_best
"""


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


def load_credentials():
    # First try ADC if available.
    if google_default is not None:
        try:
            credentials, _ = google_default(scopes=SCOPES)
            return credentials
        except Exception:
            pass

    # Desktop OAuth fallback.
    secret = Path("client_secret.json")
    if secret.exists() and InstalledAppFlow is not None:
        flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)

        # Local dev SSL bypass for corporate proxy / antivirus weak certificate chain.
        flow.oauth2session.verify = False

        return flow.run_local_server(port=0)

    raise RuntimeError(
        "Google credential bulunamadı. Backend klasöründe client_secret.json olmalı "
        "veya gcloud ADC kurulmalı."
    )


def make_bigquery_client(credentials):
    authed_session = AuthorizedSession(credentials)

    # Critical: OAuth geçtiyse bile BigQuery REST çağrısı ayrıca SSL doğrular.
    # Corporate proxy weak certificate hatasını burada da bypass ediyoruz.
    authed_session.verify = False

    return bigquery.Client(
        project=PROJECT_ID,
        credentials=credentials,
        _http=authed_session,
    )


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


def clean_storage(row: Dict[str, Any]) -> str:
    raw = norm(
        f"{row.get('storage_type_raw','')} {row.get('product_name','')} "
        f"{row.get('category_l1','')} {row.get('category_l2','')} {row.get('category_l3','')} {row.get('brand','')}"
    )

    frozen_kw = [
        "frozen", "donuk", "dondurma", "-18", "freezer", "ice cream",
        "algida", "la lorraine", "donmus", "dondurulmus"
    ]
    chilled_kw = [
        "chilled", "soguk", "soğuk", "+4", "fridge", "sut", "süt",
        "yogurt", "yoğurt", "peynir", "ayran", "kefir", "sushi",
        "somon", "salmon", "et", "tavuk", "hindi", "şarküteri", "sarkuteri"
    ]

    if any(k in raw for k in frozen_kw):
        return "FROZEN"
    if any(k in raw for k in chilled_kw):
        return "CHILLED"
    return "AMBIENT"


def infer_package_type(row: Dict[str, Any]) -> str:
    raw = norm(
        f"{row.get('product_name','')} {row.get('category_l1','')} {row.get('category_l2','')} {row.get('brand','')}"
    )

    if any(k in raw for k in ["cips", "chips", "doritos", "lays", "ruffles", "paket"]):
        return "bag"
    if any(k in raw for k in ["sise", "şişe", "water", "su", "cola", "kola", "fanta", "sprite", "ice tea"]):
        return "bottle"
    if any(k in raw for k in ["kutu", "can", "konserve", "ton baligi"]):
        return "can_or_box"
    if any(k in raw for k in ["sut", "süt", "meyve suyu", "juice", "carton"]):
        return "carton"
    if any(k in raw for k in ["kavanoz", "jar", "sos", "recel", "bal"]):
        return "jar"
    if any(k in raw for k in ["sushi", "salata", "tabak", "tray", "kase"]):
        return "tray"
    if any(k in raw for k in ["deterjan", "sampuan", "şampuan", "temizleyici", "domestos"]):
        return "bottle"
    if any(k in raw for k in ["cikolata", "çikolata", "gofret", "bar"]):
        return "bar"
    return "unknown"


FALLBACK_DIMS = {
    "bag": (18, 28, 6, 0.15),
    "bottle": (8, 26, 8, 1.0),
    "can_or_box": (8, 12, 8, 0.4),
    "carton": (8, 22, 8, 1.0),
    "jar": (8, 12, 8, 0.5),
    "tray": (16, 5, 12, 0.3),
    "bar": (8, 16, 2.5, 0.08),
    "unknown": (10, 18, 8, 0.25),
}


def weight_band(row: Dict[str, Any]) -> str:
    name = norm(row.get("product_name", ""))
    m = re.search(r"(\d+(?:[,.]\d+)?)\s*(kg|g|gr|ml|l|lt)\b", name)
    if not m:
        return "unknown"
    val = float(m.group(1).replace(",", "."))
    unit = m.group(2)
    if unit in ["kg", "l", "lt"]:
        val *= 1000
    if val <= 100:
        return "000-100"
    if val <= 250:
        return "101-250"
    if val <= 500:
        return "251-500"
    if val <= 1000:
        return "501-1000"
    if val <= 2500:
        return "1001-2500"
    return "2500+"


def family_key(row: Dict[str, Any]) -> str:
    return "|".join([
        norm(row.get("brand")),
        norm(row.get("category_l2")),
        clean_text(row.get("package_type")),
        weight_band(row),
    ])


def read_external() -> pd.DataFrame:
    if not EXTERNAL_PATH.exists():
        return pd.DataFrame()

    df = pd.read_csv(EXTERNAL_PATH, encoding="utf-8-sig")
    df = df.where(pd.notnull(df), None)

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
    for c in [
        "width_cm_external", "height_cm_external", "depth_cm_external",
        "weight_kg_external", "image_url_external", "external_source"
    ]:
        if c not in df.columns:
            df[c] = None

    if ext.empty:
        return df

    ext = ext.copy()
    ext["sku_key"] = ext["sku"].apply(norm) if "sku" in ext.columns else ""
    ext["barcode_key"] = ext["barcode"].apply(norm) if "barcode" in ext.columns else ""

    df["sku_key"] = df["sku"].apply(norm)
    df["barcode_key"] = df["barcode"].apply(norm)

    # merge by sku first
    ext_sku = ext[ext["sku_key"] != ""].drop_duplicates("sku_key")
    if not ext_sku.empty:
        cols = ["sku_key"] + [c for c in [
            "width_cm_external", "height_cm_external", "depth_cm_external",
            "weight_kg_external", "image_url_external", "external_source"
        ] if c in ext_sku.columns]
        df = df.merge(ext_sku[cols], on="sku_key", how="left", suffixes=("", "_sku"))
        for c in ["width_cm_external", "height_cm_external", "depth_cm_external", "weight_kg_external", "image_url_external", "external_source"]:
            cs = f"{c}_sku"
            if cs in df.columns:
                df[c] = df[c].where(df[c].notna(), df[cs])
                df = df.drop(columns=[cs])

    # then fill by barcode
    ext_bar = ext[ext["barcode_key"] != ""].drop_duplicates("barcode_key")
    if not ext_bar.empty:
        cols = ["barcode_key"] + [c for c in [
            "width_cm_external", "height_cm_external", "depth_cm_external",
            "weight_kg_external", "image_url_external", "external_source"
        ] if c in ext_bar.columns]
        df = df.merge(ext_bar[cols], on="barcode_key", how="left", suffixes=("", "_bar"))
        for c in ["width_cm_external", "height_cm_external", "depth_cm_external", "weight_kg_external", "image_url_external", "external_source"]:
            cb = f"{c}_bar"
            if cb in df.columns:
                df[c] = df[c].where(df[c].notna(), df[cb])
                df = df.drop(columns=[cb])

    return df


def choose_dimensions(row: Dict[str, Any], family_medians: Dict[str, Tuple[float, float, float]], overrides: Dict[str, Dict[str, Any]]):
    sku = clean_text(row.get("sku"))
    barcode = clean_text(row.get("barcode"))

    for k in [sku, barcode]:
        if k and k in overrides:
            ov = overrides[k]
            w, h, d = ov.get("width_cm"), ov.get("height_cm"), ov.get("depth_cm")
            if valid_dim(w, h, d):
                return (
                    to_num(w), to_num(h), to_num(d),
                    to_num(ov.get("weight_kg"), to_num(row.get("weight_value_internal"), 0.25)),
                    "user_approved", 1.00, "user_override", False,
                )

    iw, ih, id_ = row.get("width_cm_internal"), row.get("height_cm_internal"), row.get("depth_cm_internal")
    ew, eh, ed = row.get("width_cm_external"), row.get("height_cm_external"), row.get("depth_cm_external")

    internal_valid = valid_dim(iw, ih, id_)
    external_valid = valid_dim(ew, eh, ed)

    ivol = to_num(iw, 0) * to_num(ih, 0) * to_num(id_, 0) if internal_valid else 0
    evol = to_num(ew, 0) * to_num(eh, 0) * to_num(ed, 0) if external_valid else 0

    if external_valid and internal_valid:
        if evol >= ivol * 1.08 and evol <= ivol * 3.0:
            return to_num(ew), to_num(eh), to_num(ed), to_num(row.get("weight_kg_external"), to_num(row.get("weight_value_internal"), 0.25)), "external_larger_safe", 0.86, "external_bigger_than_internal", False
        if evol > ivol * 3.0:
            return to_num(iw), to_num(ih), to_num(id_), to_num(row.get("weight_value_internal"), 0.25), "internal_catalog", 0.72, "external_maybe_case_dimension", True
        return to_num(iw), to_num(ih), to_num(id_), to_num(row.get("weight_value_internal"), 0.25), "internal_catalog", 0.76, "internal_and_external_close", False

    if external_valid:
        return to_num(ew), to_num(eh), to_num(ed), to_num(row.get("weight_kg_external"), 0.25), "external", 0.82, "internal_missing_or_dirty", False

    if internal_valid:
        fk = row.get("family_key")
        if fk in family_medians:
            mw, mh, md = family_medians[fk]
            mvol = mw * mh * md
            if ivol > 0 and (ivol < mvol * 0.35 or ivol > mvol * 2.8):
                return mw, mh, md, to_num(row.get("weight_value_internal"), 0.25), "family_median_ai", 0.66, "internal_family_anomaly", True
        return to_num(iw), to_num(ih), to_num(id_), to_num(row.get("weight_value_internal"), 0.25), "internal_catalog", 0.70, "internal_valid", False

    fk = row.get("family_key")
    if fk in family_medians:
        mw, mh, md = family_medians[fk]
        return mw, mh, md, to_num(row.get("weight_value_internal"), 0.25), "family_median_ai", 0.62, "internal_missing_family_median_used", True

    pt = row.get("package_type") or "unknown"
    fw, fh, fd, fkg = FALLBACK_DIMS.get(pt, FALLBACK_DIMS["unknown"])
    return fw, fh, fd, to_num(row.get("weight_value_internal"), fkg), "category_package_fallback", 0.38, "needs_measurement_fallback", True


def build_cleaned(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.where(pd.notnull(df), None)

    df["storage_type_clean"] = df.apply(lambda r: clean_storage(r.to_dict()), axis=1)
    df["package_type"] = df.apply(lambda r: infer_package_type(r.to_dict()), axis=1)
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

    df["image_url"] = df.get("image_url_external", None)
    df["daily_sales"] = 0
    df["abc_class"] = "D"

    df["width_cm"] = df["final_width_cm"]
    df["height_cm"] = df["final_height_cm"]
    df["depth_cm"] = df["final_depth_cm"]
    df["weight_kg"] = df["final_weight_kg"]
    df["storage_type"] = df["storage_type_clean"]

    for c, fallback in [
        ("brand", "UNKNOWN"),
        ("category_l1", "GENERAL"),
        ("category_l2", "GENERAL"),
        ("category_l3", ""),
    ]:
        df[c] = df[c].fillna(fallback)

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

    return df[wanted].sort_values(["storage_type_clean", "category_l1", "category_l2", "brand", "product_name"])


def main():
    print("Google / BigQuery login kontrolü...")
    credentials = load_credentials()
    client = make_bigquery_client(credentials)

    print("FAST catalog-only query çalışıyor...")
    job_config = bigquery.QueryJobConfig(use_query_cache=True)
    job = client.query(QUERY, job_config=job_config)
    df = job.result().to_dataframe(create_bqstorage_client=False)
    print(f"Catalog satır: {len(df):,}")

    print("Product Data Quality AI temizliği çalışıyor...")
    cleaned = build_cleaned(df)

    cleaned.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    try:
        cleaned.to_excel(OUT_XLSX, index=False)
    except Exception:
        pass

    report = {
        "mode": "FAST_CATALOG_ONLY_SSL_FULL_BYPASS",
        "rows": int(len(cleaned)),
        "output_csv": str(OUT_CSV),
        "output_xlsx": str(OUT_XLSX),
        "dimension_sources": cleaned["dimension_source"].value_counts(dropna=False).to_dict(),
        "storage_types": cleaned["storage_type_clean"].value_counts(dropna=False).to_dict(),
        "needs_user_measurement_count": int(cleaned["needs_user_measurement"].sum()),
        "low_confidence_count": int((cleaned["dimension_confidence"] < 0.55).sum()),
        "note": "Sales columns are 0 in fast mode. Enrich sales later with a separate sales aggregation file.",
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Tamamlandı.")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
