from pathlib import Path
import math
import re
import json
import pandas as pd

DATA_DIR = Path("data")
IN_PATH = DATA_DIR / "master_products.csv"
BACKUP_PATH = DATA_DIR / "master_products_before_storage_zone_hotfix.csv"
ALL_PATH = DATA_DIR / "master_products_with_excluded_bundles.csv"
OUT_PATH = DATA_DIR / "master_products.csv"
REPORT_PATH = DATA_DIR / "master_storage_zone_hotfix_report.json"

def clean_text(v):
    if v is None:
        return ""
    try:
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    return str(v).strip()

def norm(v):
    return (
        clean_text(v).lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )

def col(df, name, default=""):
    if name in df.columns:
        return df[name].fillna("").astype(str)
    return pd.Series([default] * len(df), index=df.index)

def contains_any(text, terms):
    return any(t in text for t in terms)

def is_virtual_bundle_row(row):
    name = norm(row.get("product_name"))
    cat1 = norm(row.get("category_l1"))
    cat2 = norm(row.get("category_l2"))
    brand = norm(row.get("brand"))

    # Online combo / campaign SKUs. These should not be physical planogram SKUs.
    if ("paketi" in name or "seti" in name) and (" & " in clean_text(row.get("product_name")) or " + " in clean_text(row.get("product_name"))):
        return True

    if cat1 in ["cok al az ode", "çok al az öde"]:
        return True

    # Unknown brand + multiple product names is usually virtual bundle.
    if brand == "unknown" and ("paketi" in name or "seti" in name) and any(x in name for x in ["coca", "pepsi", "superfresh", "ariste", "maret", "apikoglu", "eker"]):
        return True

    return False

def infer_storage(row):
    name = norm(row.get("product_name"))
    brand = norm(row.get("brand"))
    cat1 = norm(row.get("category_l1"))
    cat2 = norm(row.get("category_l2"))
    cat3 = norm(row.get("category_l3"))
    raw = norm(row.get("storage_type_raw"))
    hay = f"{name} {brand} {cat1} {cat2} {cat3} {raw}"

    # 1) Hard frozen from category first
    frozen_terms = [
        "dondurulmus", "dondurulmuş", "dondurulmus gida", "dondurulmuş gida",
        "donuk", "frozen", "ice cream", "dondurma"
    ]
    if contains_any(hay, frozen_terms):
        return "FROZEN"

    # Brand alone is not enough, but known frozen product names with SuperFresh are.
    if contains_any(hay, ["superfresh", "super fresh"]):
        if contains_any(name, [
            "pizza", "patates", "mantı", "manti", "köfte", "kofte", "falafel",
            "poğaça", "pogaca", "börek", "borek", "milföy", "milfoy",
            "garnitür", "garnitur", "bezelye", "mısır", "misir", "sebze",
            "nugget", "schnitzel", "burger"
        ]):
            return "FROZEN"

    # 2) Canned/ambient exceptions
    ambient_terms = [
        "ton baligi", "ton balığı", "konserve", "canned", "salca", "salça",
        "makarna", "pirinc", "pirinç", "bulgur", "un ", "seker", "şeker",
        "sutlu cikolata", "sütlü çikolata", "peynirli cips", "peynir aromali", "peynir aromalı",
        "ice tea", "soguk cay", "soğuk çay"
    ]
    if contains_any(hay, ambient_terms):
        return "AMBIENT"

    # 3) Hard chilled categories / products
    chilled_cat_terms = [
        "sut urunleri", "süt ürünleri", "dairy", "yoğurt", "yogurt", "ayran", "kefir",
        "peynir", "sarkuteri", "şarküteri", "fresh meat", "taze et", "tavuk", "hindi",
        "sushi", "somon", "salmon"
    ]
    if contains_any(hay, chilled_cat_terms):
        # avoid false positive
        if not contains_any(hay, ambient_terms):
            return "CHILLED"

    # 4) Raw storage if reliable
    if raw in ["frozen", "-18", "freezer"]:
        return "FROZEN"
    if raw in ["chilled", "+4", "cold", "fridge"]:
        return "CHILLED"

    return "AMBIENT"

def infer_zone(row, storage):
    name = norm(row.get("product_name"))
    cat1 = norm(row.get("category_l1"))
    cat2 = norm(row.get("category_l2"))
    package_type = norm(row.get("package_type"))

    if row.get("exclude_from_planogram") is True:
        return "VIRTUAL_BUNDLE_EXCLUDE"
    if storage == "FROZEN":
        return "FROZEN_FREEZER"
    if storage == "CHILLED":
        return "CHILLED_FRIDGE"
    if "produce" in cat1 or "meyve" in cat1 or "sebze" in cat1 or "fruit" in cat2 or "vegetable" in cat2:
        return "PRODUCE_CRATE"
    if package_type in ["demijohn"]:
        return "WATER_RACK"
    if package_type in ["case_pack"] or contains_any(name, ["6x", "12x", "24x", "koli", "damacana", "5 l", "5l"]):
        return "BULK_FLOOR"
    if package_type == "hanging" or contains_any(name, ["diş fırçası", "dis fircasi"]):
        return "HANGING_DISPLAY"
    return "REGULAR_SHELF"

def infer_merch_group(row, storage, zone):
    name = norm(row.get("product_name"))
    cat1 = norm(row.get("category_l1"))
    cat2 = norm(row.get("category_l2"))
    package_type = norm(row.get("package_type"))

    if zone == "VIRTUAL_BUNDLE_EXCLUDE":
        return "VIRTUAL_BUNDLE"
    if storage == "FROZEN":
        return "FROZEN"
    if storage == "CHILLED":
        return "CHILLED"
    if zone in ["WATER_RACK", "BULK_FLOOR"] and contains_any(name + " " + cat2, ["su", "water", "içecek", "icecek", "cola", "kola"]):
        return "BEVERAGE_BULK"
    if contains_any(name + " " + cat2, ["cips", "chips", "kraker", "snack"]):
        return "SNACK_BAG"
    if contains_any(name + " " + cat2, ["air wick", "oda kokusu", "koku", "freshmatic"]):
        return "NON_FOOD_ODOR"
    if contains_any(name + " " + cat2, ["power strip", "priz", "kablo", "elektrik"]):
        return "ELECTRONICS"
    if contains_any(name + " " + cat2, ["şampuan", "sampuan", "deodorant", "diş", "dis", "kişisel", "kisisel"]):
        return "PERSONAL_CARE"
    if contains_any(name + " " + cat2, ["ton baligi", "ton balığı", "konserve"]):
        return "CANNED_FOOD"
    return "FOOD_AMBIENT"

def main():
    if not IN_PATH.exists():
        raise FileNotFoundError(f"{IN_PATH} bulunamadı.")

    df = pd.read_csv(IN_PATH, low_memory=False)
    if not BACKUP_PATH.exists():
        df.to_csv(BACKUP_PATH, index=False, encoding="utf-8-sig")

    records = df.where(pd.notnull(df), None).to_dict(orient="records")

    exclude_flags = []
    storages = []
    zones = []
    merch_groups = []

    for r in records:
        exclude = is_virtual_bundle_row(r)
        r["exclude_from_planogram"] = exclude
        storage = infer_storage(r)
        zone = infer_zone(r, storage)
        merch = infer_merch_group(r, storage, zone)

        exclude_flags.append(exclude)
        storages.append(storage)
        zones.append(zone)
        merch_groups.append(merch)

    df["exclude_from_planogram"] = exclude_flags
    df["storage_type_clean"] = storages
    df["storage_type"] = storages
    df["recommended_zone_type"] = zones
    df["merch_group"] = merch_groups

    # Keep a full audit file, then remove virtual bundles from master used by engine.
    df.to_csv(ALL_PATH, index=False, encoding="utf-8-sig")

    engine_df = df[df["exclude_from_planogram"] != True].copy()
    engine_df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    report = {
        "mode": "MASTER_STORAGE_ZONE_HOTFIX_V1",
        "input": str(IN_PATH),
        "backup": str(BACKUP_PATH),
        "full_audit_output": str(ALL_PATH),
        "engine_output": str(OUT_PATH),
        "rows_before": int(len(df)),
        "rows_after_excluding_virtual_bundles": int(len(engine_df)),
        "excluded_virtual_bundle_count": int(df["exclude_from_planogram"].sum()),
        "storage_counts": engine_df["storage_type"].value_counts(dropna=False).to_dict(),
        "zone_counts": engine_df["recommended_zone_type"].value_counts(dropna=False).to_dict(),
        "merch_group_counts": engine_df["merch_group"].value_counts(dropna=False).head(30).to_dict(),
        "superfresh_sample": engine_df[engine_df.astype(str).apply(lambda c: c.str.contains("SuperFresh|Super Fresh", case=False, na=False)).any(axis=1)][
            [c for c in ["sku","product_name","category_l1","category_l2","category_l3","storage_type","recommended_zone_type","merch_group"] if c in engine_df.columns]
        ].head(30).to_dict(orient="records"),
    }

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Tamamlandı.")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
