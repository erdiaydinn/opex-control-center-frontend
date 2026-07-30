from pathlib import Path
import json
import math
import re
import time
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

INPUT_CANDIDATES = [
    DATA_DIR / "master_products_cleaned.csv",
    DATA_DIR / "catalog_export.csv",
    DATA_DIR / "master_products.csv",
]

CACHE_PATH = DATA_DIR / "openfoodfacts_cache.json"
OUT_EXTERNAL = DATA_DIR / "external_product_dimensions.csv"
OUT_REPORT = DATA_DIR / "public_barcode_enrichment_report.json"

# Open Food Facts resmi API v2 barcode endpoint.
# Fiziksel ölçü çoğu üründe yoktur; burada OFF'u kimlik/görsel/quantity/packaging için kullanıyoruz.
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"

FIELDS = ",".join([
    "code",
    "product_name",
    "product_name_tr",
    "generic_name",
    "brands",
    "categories",
    "categories_tags",
    "quantity",
    "packaging",
    "packaging_tags",
    "image_url",
    "image_front_url",
    "stores",
    "countries_tags",
])

REQUEST_TIMEOUT = 12
SLEEP_SECONDS = 0.25
MAX_PRODUCTS = None  # Test için 500 yazabilirsin. Tam çalışma için None.


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


def read_csv_any(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="utf-8", low_memory=False)


def find_input_file() -> Path:
    for p in INPUT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Input bulunamadı. data/master_products_cleaned.csv veya data/catalog_export.csv bekleniyor."
    )


def extract_primary_barcode(v: Any) -> str:
    s = clean_text(v)
    if not s:
        return ""

    # product_barcodes alanı bazen "['...']", "123,456", "123|456" gibi gelebilir.
    candidates = re.findall(r"\d{8,14}", s)
    if not candidates:
        return ""

    # GTIN/EAN için genelde 13 hane iyi adaydır; yoksa en uzun makul kod.
    candidates = sorted(set(candidates), key=lambda x: (len(x) == 13, len(x)), reverse=True)
    return candidates[0]


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


def parse_quantity_to_kg_liter(quantity: str) -> Optional[float]:
    q = norm(quantity)
    if not q:
        return None

    # multipack: 6 x 330 ml
    m = re.search(r"(\d+)\s*[x×]\s*(\d+(?:[,.]\d+)?)\s*(ml|cl|l|lt|g|gr|kg)", q)
    if m:
        count = float(m.group(1))
        val = float(m.group(2).replace(",", "."))
        unit = m.group(3)
        if unit == "cl":
            val = val * 10
            unit = "ml"
        if unit in ["ml"]:
            return count * val / 1000
        if unit in ["l", "lt", "kg"]:
            return count * val
        if unit in ["g", "gr"]:
            return count * val / 1000

    m = re.search(r"(\d+(?:[,.]\d+)?)\s*(ml|cl|l|lt|g|gr|kg)", q)
    if not m:
        return None

    val = float(m.group(1).replace(",", "."))
    unit = m.group(2)
    if unit == "cl":
        return val * 10 / 1000
    if unit == "ml":
        return val / 1000
    if unit in ["l", "lt", "kg"]:
        return val
    if unit in ["g", "gr"]:
        return val / 1000
    return None


def infer_package_type(text: str, quantity: str = "", packaging: str = "") -> str:
    raw = norm(f"{text} {quantity} {packaging}")

    if "damacana" in raw or "demijohn" in raw:
        return "demijohn"
    if re.search(r"\b(6|8|10|12|24)\s*[x×]\b", raw) or any(k in raw for k in ["multipack", "multi-pack", "shrink", "koli", "case"]):
        return "case_pack"
    if any(k in raw for k in ["chips", "cips", "doritos", "lays", "ruffles", "bag", "poşet", "poset", "paket"]):
        return "bag"
    if any(k in raw for k in ["bottle", "şişe", "sise", "cola", "kola", "water", "su", "fanta", "sprite", "ice tea", "gazoz"]):
        return "bottle"
    if any(k in raw for k in ["can", "tin", "konserve", "kutu"]):
        return "can_or_box"
    if any(k in raw for k in ["carton", "tetra", "süt", "sut", "juice", "meyve suyu"]):
        return "carton"
    if any(k in raw for k in ["jar", "kavanoz", "sos", "reçel", "recel", "bal", "turşu", "tursu", "zeytin"]):
        return "jar"
    if any(k in raw for k in ["tray", "tabak", "sushi", "salata", "kase"]):
        return "tray"
    if any(k in raw for k in ["bar", "çikolata", "cikolata", "gofret"]):
        return "bar"
    return "unknown"


def estimate_dimension(package_type: str, qty_kg_l: Optional[float], name: str = "") -> Tuple[float, float, float, float, str]:
    """
    OFF fiziksel ölçü vermediği için makul raf ölçüsü bandından tek fallback seçiyoruz.
    Bu ölçü 'resmi' değil; Product Data Quality AI tahmini.
    """
    n = norm(name)
    q = qty_kg_l or 0

    if package_type == "demijohn":
        return 28, 48, 28, 19.0, "ai_demijohn_expected"
    if package_type == "case_pack":
        # multipack beverage / koli
        return 34, 24, 24, max(q, 4.0), "ai_case_pack_expected"
    if package_type == "bag":
        if q >= 0.3:
            return 24, 34, 8, q, "ai_bag_large_expected"
        if q >= 0.15:
            return 20, 30, 7, q, "ai_bag_medium_expected"
        return 16, 24, 5, max(q, 0.08), "ai_bag_small_expected"
    if package_type == "bottle":
        if q >= 5:
            return 16, 34, 16, q, "ai_bottle_5l_expected"
        if q >= 1.5:
            return 10, 34, 10, q, "ai_bottle_large_expected"
        if q >= 1:
            return 8, 28, 8, q, "ai_bottle_1l_expected"
        if q >= 0.5:
            return 7, 22, 7, q, "ai_bottle_500ml_expected"
        return 6, 16, 6, max(q, 0.25), "ai_bottle_small_expected"
    if package_type == "carton":
        if q >= 1:
            return 8, 22, 8, q, "ai_carton_1l_expected"
        return 6, 14, 5, max(q, 0.2), "ai_carton_small_expected"
    if package_type == "can_or_box":
        if "konserve" in n or "ton" in n:
            return 8, 5, 8, max(q, 0.16), "ai_can_expected"
        return 8, 14, 6, max(q, 0.25), "ai_box_expected"
    if package_type == "jar":
        if q >= 1:
            return 10, 16, 10, q, "ai_jar_large_expected"
        return 8, 12, 8, max(q, 0.35), "ai_jar_expected"
    if package_type == "tray":
        return 16, 5, 12, max(q, 0.25), "ai_tray_expected"
    if package_type == "bar":
        if q >= 0.2:
            return 12, 20, 3, q, "ai_bar_large_expected"
        return 8, 16, 2.5, max(q, 0.04), "ai_bar_expected"

    return 10, 18, 8, max(q, 0.25), "ai_unknown_package_expected"


def clean_storage_from_off(row: Dict[str, Any], existing_storage: str = "") -> str:
    # OFF genelde storage vermez; product text ile sadece güçlü sinyaller.
    raw = norm(
        f"{row.get('product_name','')} {row.get('categories','')} {row.get('brands','')}"
    )
    if any(k in raw for k in ["frozen", "donuk", "dondurma", "algida"]):
        return "FROZEN"
    if any(k in raw for k in ["sushi", "yogurt", "yoğurt", "ayran", "kefir", "peynir", "dairy"]):
        return "CHILLED"
    return existing_storage or ""


def load_cache() -> Dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: Dict[str, Any]) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_off(barcode: str, cache: Dict[str, Any]) -> Dict[str, Any]:
    if barcode in cache:
        return cache[barcode]

    url = OFF_URL.format(barcode=barcode)
    try:
        r = requests.get(
            url,
            params={"fields": FIELDS},
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "PlonagramDataQualityAI/1.0 (local enrichment)",
                "Accept": "application/json",
            },
        )
        if r.status_code != 200:
            data = {"status": "http_error", "http_status": r.status_code}
        else:
            data = r.json()
    except Exception as err:
        data = {"status": "request_error", "error": str(err)}

    cache[barcode] = data

    if len(cache) % 100 == 0:
        save_cache(cache)

    time.sleep(SLEEP_SECONDS)
    return data


def main():
    inp = find_input_file()
    print(f"Input okunuyor: {inp}")
    df = read_csv_any(inp)
    rows = df.where(pd.notnull(df), None).to_dict(orient="records")

    cache = load_cache()
    out = []

    total = len(rows) if MAX_PRODUCTS is None else min(MAX_PRODUCTS, len(rows))
    print(f"Public barcode enrichment başlıyor. Ürün: {total:,}")

    processed = 0
    found = 0

    for idx, r in enumerate(rows):
        if MAX_PRODUCTS is not None and processed >= MAX_PRODUCTS:
            break

        sku = clean_text(first(r, ["sku", "SKU"]))
        barcode_raw = first(r, ["barcode", "product_barcodes", "barcodes", "gtin", "ean"])
        barcode = extract_primary_barcode(barcode_raw)

        # Barcode yoksa da AI fallback row üretebiliriz ama external enrichment için anlamlı değil.
        if not barcode:
            continue

        existing_name = clean_text(first(r, ["product_name", "name"]))
        existing_brand = clean_text(first(r, ["brand", "brand_name"]))
        existing_cat1 = clean_text(first(r, ["category_l1", "frontend_category_local"]))
        existing_cat2 = clean_text(first(r, ["category_l2", "frontend_subcategory_local"]))
        existing_storage = clean_text(first(r, ["storage_type", "storage_type_clean", "storage_type_raw"]))

        data = fetch_off(barcode, cache)
        processed += 1

        product = {}
        status = str(data.get("status", ""))

        if status in ["1", "found"] or data.get("product"):
            product = data.get("product") or {}
            found += 1

        off_name = clean_text(
            product.get("product_name_tr")
            or product.get("product_name")
            or product.get("generic_name")
        )
        name = off_name or existing_name

        brand = clean_text(product.get("brands")) or existing_brand
        quantity = clean_text(product.get("quantity"))
        packaging = clean_text(product.get("packaging"))
        categories = clean_text(product.get("categories"))
        image_url = clean_text(product.get("image_front_url") or product.get("image_url"))

        package_type = infer_package_type(
            f"{name} {brand} {existing_cat1} {existing_cat2} {categories}",
            quantity=quantity,
            packaging=packaging,
        )

        qty_kg_l = parse_quantity_to_kg_liter(quantity)
        if qty_kg_l is None:
            qty_kg_l = parse_quantity_to_kg_liter(existing_name)

        width, height, depth, weight, dim_source = estimate_dimension(package_type, qty_kg_l, name)
        storage_hint = clean_storage_from_off(
            {
                "product_name": name,
                "categories": categories,
                "brands": brand,
            },
            existing_storage=existing_storage,
        )

        confidence = 0.58
        if product:
            confidence += 0.10
        if image_url:
            confidence += 0.07
        if quantity:
            confidence += 0.07
        if package_type != "unknown":
            confidence += 0.08
        confidence = min(round(confidence, 2), 0.86)

        out.append({
            "sku": sku,
            "barcode": barcode,
            "product_name_external": name,
            "brand_external": brand,
            "category_external": categories,
            "quantity_external": quantity,
            "packaging_external": packaging,
            "package_type_external": package_type,
            "storage_type_external_hint": storage_hint,
            "width_cm": width,
            "height_cm": height,
            "depth_cm": depth,
            "weight_kg": round(weight, 3),
            "image_url": image_url,
            "source": "openfoodfacts_ai_expected_dimension" if product else "ai_expected_dimension_no_public_match",
            "dimension_source_detail": dim_source,
            "dimension_confidence_external": confidence,
            "needs_user_measurement": confidence < 0.75,
            "public_match_found": bool(product),
        })

        if processed % 50 == 0:
            print(f"İşlenen: {processed:,}/{total:,} | OFF match: {found:,} | Cache: {len(cache):,}")
            save_cache(cache)

    save_cache(cache)

    out_df = pd.DataFrame(out)
    if out_df.empty:
        print("Hiç barcode bulunamadı veya external çıktı oluşmadı.")
        return

    # Dedup by sku/barcode
    out_df = out_df.sort_values(["public_match_found", "dimension_confidence_external"], ascending=[False, False])
    out_df = out_df.drop_duplicates(["sku", "barcode"], keep="first")
    out_df.to_csv(OUT_EXTERNAL, index=False, encoding="utf-8-sig")

    report = {
        "mode": "PUBLIC_BARCODE_ENRICHMENT_OPENFOODFACTS",
        "input": str(inp),
        "rows_input": len(df),
        "rows_output": len(out_df),
        "processed_barcodes": processed,
        "openfoodfacts_matches": found,
        "output": str(OUT_EXTERNAL),
        "package_types": out_df["package_type_external"].value_counts(dropna=False).to_dict(),
        "confidence_distribution": {
            "high_0_75_plus": int((out_df["dimension_confidence_external"] >= 0.75).sum()),
            "mid_0_60_0_74": int(((out_df["dimension_confidence_external"] >= 0.60) & (out_df["dimension_confidence_external"] < 0.75)).sum()),
            "low_under_0_60": int((out_df["dimension_confidence_external"] < 0.60).sum()),
        },
    }

    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Tamamlandı.")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
