from pathlib import Path
import json
import math
import re
from typing import Any, Optional, Tuple, Dict

import pandas as pd

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

INPUT_CANDIDATES = [
    DATA_DIR / "master_products_cleaned.csv",
    DATA_DIR / "catalog_export.csv",
    DATA_DIR / "master_products.csv",
]

OUT_EXTERNAL = DATA_DIR / "external_product_dimensions.csv"
OUT_REPORT = DATA_DIR / "ai_catalog_dimension_enrichment_report.json"


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
    raise FileNotFoundError("Input yok: data/master_products_cleaned.csv veya data/catalog_export.csv bekleniyor.")


def extract_primary_barcode(v: Any) -> str:
    s = clean_text(v)
    candidates = re.findall(r"\d{8,14}", s)
    if not candidates:
        return ""
    # Keep first clean GTIN, but remove a leading 0 only if 14 digits and Turkish EAN-like.
    c = candidates[0]
    if len(c) == 14 and c.startswith("0"):
        return c[1:]
    return c


def parse_quantity(name: str) -> Tuple[Optional[float], str, int]:
    """
    Returns normalized amount in kg/liter equivalent, unit_family, multipack_count.
    """
    n = norm(name)
    count = 1

    mpack = re.search(r"(\d+)\s*[x×]\s*(\d+(?:[,.]\d+)?)\s*(kg|g|gr|ml|l|lt)\b", n)
    if mpack:
        count = int(mpack.group(1))
        val = float(mpack.group(2).replace(",", "."))
        unit = mpack.group(3)
        if unit in ["kg", "l", "lt"]:
            return count * val, unit, count
        return count * val / 1000, unit, count

    # Turkish pattern: 3'lü / 4 lü etc
    mcount = re.search(r"(\d+)\s*['’]?\s*l[üu]\b", n)
    if mcount:
        count = int(mcount.group(1))

    matches = re.findall(r"(\d+(?:[,.]\d+)?)\s*(kg|g|gr|ml|l|lt)\b", n)
    if not matches:
        return None, "", count

    # Take last explicit size often nearest product package size; if multipack count exists multiply.
    raw, unit = matches[-1]
    val = float(raw.replace(",", "."))
    if unit in ["kg", "l", "lt"]:
        amount = val
    else:
        amount = val / 1000
    return amount * count, unit, count


def package_type(name: str, cat1: str, cat2: str, brand: str) -> str:
    raw = norm(f"{name} {cat1} {cat2} {brand}")

    if any(k in raw for k in ["damacana"]):
        return "demijohn"
    if re.search(r"\b(4|6|8|10|12|24)\s*[x×]\b", raw) or any(k in raw for k in ["koli", "multipack", "shrink"]):
        return "case_pack"
    if any(k in raw for k in ["cips", "chips", "doritos", "lays", "ruffles", "kuruyemis", "kuruyemiş", "kraker", "paket"]):
        return "bag"
    if any(k in raw for k in ["cikolata", "çikolata", "gofret", "bar", "protein bar"]):
        return "bar"
    if any(k in raw for k in ["sise", "şişe", "kola", "cola", "fanta", "sprite", "ice tea", "gazoz", "su ", "ayran"]):
        return "bottle"
    if any(k in raw for k in ["sut", "süt", "meyve suyu", "juice", "uht"]):
        return "carton"
    if any(k in raw for k in ["konserve", "ton baligi", "ton balığı", "kutu"]):
        return "can_or_box"
    if any(k in raw for k in ["kavanoz", "sos", "recel", "reçel", "bal", "zeytin", "tursu", "turşu", "salca", "salça"]):
        return "jar"
    if any(k in raw for k in ["sushi", "salata", "kase", "tabak", "hazir yemek", "hazır yemek"]):
        return "tray"
    if any(k in raw for k in ["yumurta"]):
        return "egg_pack"
    if any(k in raw for k in ["pecete", "peçete", "tuvalet kagidi", "tuvalet kağıdı", "havlu", "kagit", "kağıt"]):
        return "paper_bulky"
    if any(k in raw for k in ["dis fircasi", "diş fırçası", "askili", "askılı"]):
        return "hanging"
    if any(k in raw for k in ["deterjan", "sampuan", "şampuan", "temizleyici", "domestos", "yumusatici", "yumuşatıcı"]):
        return "bottle"
    return "unknown"


def estimate_dim(pt: str, amount: Optional[float], name: str) -> Tuple[float, float, float, float, str, float]:
    q = amount or 0
    n = norm(name)

    if pt == "demijohn":
        return 28, 48, 28, 19.0, "ai_demijohn_expected", 0.74
    if pt == "case_pack":
        # 6x330ml / 6x1.5L / koli
        if q >= 6:
            return 42, 28, 28, q, "ai_case_pack_large_expected", 0.70
        return 34, 24, 24, max(q, 3.0), "ai_case_pack_expected", 0.68
    if pt == "bag":
        if q >= 0.3:
            return 24, 34, 8, q, "ai_bag_large_expected", 0.72
        if q >= 0.15:
            return 20, 30, 7, q, "ai_bag_medium_expected", 0.72
        return 16, 24, 5, max(q, 0.08), "ai_bag_small_expected", 0.70
    if pt == "bar":
        if q >= 0.15:
            return 12, 20, 3, q, "ai_bar_large_expected", 0.73
        return 8, 16, 2.5, max(q, 0.04), "ai_bar_expected", 0.72
    if pt == "bottle":
        if q >= 5:
            return 16, 34, 16, q, "ai_bottle_5l_expected", 0.76
        if q >= 1.5:
            return 10, 34, 10, q, "ai_bottle_large_expected", 0.75
        if q >= 1:
            return 8, 28, 8, q, "ai_bottle_1l_expected", 0.75
        if q >= 0.5:
            return 7, 22, 7, q, "ai_bottle_500ml_expected", 0.75
        return 6, 16, 6, max(q, 0.25), "ai_bottle_small_expected", 0.70
    if pt == "carton":
        if q >= 1:
            return 8, 22, 8, q, "ai_carton_1l_expected", 0.75
        return 6, 14, 5, max(q, 0.2), "ai_carton_small_expected", 0.70
    if pt == "can_or_box":
        if "ton" in n or "konserve" in n:
            return 8, 5, 8, max(q, 0.16), "ai_can_expected", 0.72
        return 8, 14, 6, max(q, 0.25), "ai_box_expected", 0.68
    if pt == "jar":
        if q >= 1:
            return 10, 16, 10, q, "ai_jar_large_expected", 0.74
        return 8, 12, 8, max(q, 0.35), "ai_jar_expected", 0.74
    if pt == "tray":
        return 16, 5, 12, max(q, 0.25), "ai_tray_expected", 0.68
    if pt == "egg_pack":
        return 15, 7, 11, max(q, 0.5), "ai_egg_pack_expected", 0.76
    if pt == "paper_bulky":
        return 20, 28, 12, max(q, 0.25), "ai_paper_bulky_expected", 0.66
    if pt == "hanging":
        return 8, 22, 3, max(q, 0.05), "ai_hanging_expected", 0.70

    return 10, 18, 8, max(q, 0.25), "ai_unknown_package_expected", 0.45


def storage_hint(name: str, cat1: str, cat2: str, existing: str) -> str:
    raw = norm(f"{name} {cat1} {cat2} {existing}")
    if any(k in raw for k in ["dondurma", "donuk", "frozen", "la lorraine", "algida"]):
        return "FROZEN"
    if any(k in raw for k in ["sushi", "somon", "salmon", "yoğurt", "yogurt", "ayran", "kefir", "peynir", "tavuk", "et "]):
        if not any(fp in raw for fp in ["peynirli cips", "sütlü çikolata", "sutlu cikolata"]):
            return "CHILLED"
    return clean_text(existing) or "AMBIENT"


def main():
    inp = find_input_file()
    print(f"Input okunuyor: {inp}")
    df = read_csv_any(inp)
    rows = df.where(pd.notnull(df), None).to_dict(orient="records")

    out = []
    for r in rows:
        sku = clean_text(first(r, ["sku", "SKU"]))
        barcode = extract_primary_barcode(first(r, ["barcode", "product_barcodes", "barcodes", "gtin", "ean"]))
        name = clean_text(first(r, ["product_name", "name", "product_name_local"]))
        brand = clean_text(first(r, ["brand", "brand_name"]))
        cat1 = clean_text(first(r, ["category_l1", "frontend_category_local"]))
        cat2 = clean_text(first(r, ["category_l2", "frontend_subcategory_local"]))
        existing_storage = clean_text(first(r, ["storage_type", "storage_type_clean", "storage_type_raw"]))

        pt = package_type(name, cat1, cat2, brand)
        amount, unit, count = parse_quantity(name)
        w, h, d, kg, detail, conf = estimate_dim(pt, amount, name)

        # Confidence tuning
        if amount:
            conf += 0.04
        if barcode:
            conf += 0.02
        if pt != "unknown":
            conf += 0.04
        conf = min(round(conf, 2), 0.86)

        out.append({
            "sku": sku,
            "barcode": barcode,
            "product_name_external": name,
            "brand_external": brand,
            "category_external": f"{cat1} > {cat2}".strip(" >"),
            "quantity_external": amount if amount is not None else "",
            "package_type_external": pt,
            "storage_type_external_hint": storage_hint(name, cat1, cat2, existing_storage),
            "width_cm": w,
            "height_cm": h,
            "depth_cm": d,
            "weight_kg": round(kg, 3),
            "image_url": clean_text(first(r, ["image_url", "product_image_url", "catalog_image_url"])),
            "source": "ai_catalog_text_expected_dimension",
            "dimension_source_detail": detail,
            "dimension_confidence_external": conf,
            "needs_user_measurement": conf < 0.75,
            "public_match_found": False,
        })

    out_df = pd.DataFrame(out)
    out_df = out_df[out_df["sku"].astype(str).str.len() > 0]
    out_df.to_csv(OUT_EXTERNAL, index=False, encoding="utf-8-sig")

    report = {
        "mode": "AI_CATALOG_TEXT_EXPECTED_DIMENSION_NO_API",
        "input": str(inp),
        "rows_input": int(len(df)),
        "rows_output": int(len(out_df)),
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
