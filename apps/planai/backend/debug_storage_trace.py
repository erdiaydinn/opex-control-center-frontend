from pathlib import Path
import pandas as pd
import sys

DATA = Path("data")

SEARCH_TERMS = [
    "YS2417",
    "Keskinoglu Baby Chicken Grill",
    "Keskinoglu",
    "Chicken Grill",
    "MRK.06583",
    "Ülker Çizivic Cheese Sandwich",
    "Cheese Sandwich Crackers",
]

storage_like = [
    "storage",
    "storage_type",
    "storage_class",
    "catalog_storage_type",
    "master_storage_type",
    "canonical_storage_type",
    "Storage Type",
]

name_like = [
    "sku",
    "SKU",
    "product_barcodes",
    "Barcodes",
    "product_name",
    "Product Name",
    "product_name_local",
    "brand",
    "brand_name",
    "frontend_category_local",
    "frontend_subcategory_local",
    "Category L1",
    "Category L2",
]

def read_file(path):
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        if path.suffix.lower() in [".xlsx", ".xls"]:
            return pd.read_excel(path, dtype=str).fillna("")
    except Exception as e:
        print(f"\n[SKIP] {path.name}: {e}")
    return None

def row_text(row):
    return " ".join(str(v) for v in row.values if v is not None).lower()

def pick(row, cols):
    out = {}
    lower_cols = {str(c).lower(): c for c in row.index}
    for c in cols:
        real = lower_cols.get(str(c).lower())
        if real is not None:
            val = str(row.get(real, "")).strip()
            if val:
                out[str(real)] = val
    return out

for path in sorted(DATA.glob("*")):
    if path.suffix.lower() not in [".csv", ".xlsx", ".xls"]:
        continue

    df = read_file(path)
    if df is None or df.empty:
        continue

    hits = []
    for _, row in df.iterrows():
        hay = row_text(row)
        if any(term.lower() in hay for term in SEARCH_TERMS):
            hits.append(row)

    if not hits:
        continue

    print("\n" + "=" * 100)
    print(f"FILE: {path}")
    print(f"ROWS MATCHED: {len(hits)}")
    print("COLUMNS:", list(df.columns))

    for i, row in enumerate(hits[:20], 1):
        print("\n--- HIT", i, "---")
        print("IDENTITY:", pick(row, name_like))
        print("STORAGE :", pick(row, storage_like))
        print("RAW SMALL:", {str(k): str(row[k]) for k in list(row.index)[:20] if str(row[k]).strip()})
