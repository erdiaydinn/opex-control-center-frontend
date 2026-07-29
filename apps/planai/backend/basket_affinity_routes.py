from fastapi import APIRouter, Query
from pathlib import Path
import pandas as pd

from services.store_identity_service import resolve_store, norm

router = APIRouter(prefix="/basket-affinity", tags=["basket-affinity"])

DATA_DIR = Path(__file__).resolve().parent / "data"
AFFINITY_CSV = DATA_DIR / "basket_affinity_top.csv"

def read_affinity():
    if not AFFINITY_CSV.exists():
        return None

    try:
        return pd.read_csv(AFFINITY_CSV, dtype=str, encoding="utf-8-sig").fillna("")
    except UnicodeDecodeError:
        return pd.read_csv(AFFINITY_CSV, dtype=str).fillna("")

def find_col(df, candidates):
    lower = {str(c).lower().strip(): c for c in df.columns}

    for c in candidates:
        hit = lower.get(str(c).lower().strip())
        if hit is not None:
            return hit

    normalized = {norm(c): c for c in df.columns}
    for c in candidates:
        hit = normalized.get(norm(c))
        if hit is not None:
            return hit

    return None

def number(value, default=1.0):
    try:
        return float(str(value or "").replace(",", ".").replace("%", "").strip())
    except Exception:
        return default

@router.get("/resolve-store")
def resolve_store_endpoint(store_key: str = Query(...)):
    identity = resolve_store(store_key)
    return {
        "success": True,
        "input": store_key,
        "resolved": identity,
    }

@router.get("/debug")
def debug_affinity():
    df = read_affinity()
    if df is None:
        return {
            "success": False,
            "message": f"basket_affinity_top.csv bulunamadı: {AFFINITY_CSV}",
        }

    return {
        "success": True,
        "path": str(AFFINITY_CSV),
        "rows": len(df),
        "columns": list(df.columns),
        "sample": df.head(5).to_dict(orient="records"),
    }

@router.get("/map")
def basket_affinity_map(
    store_key: str = Query(...),
    limit: int = Query(5000, ge=1, le=100000),
):
    df = read_affinity()
    if df is None:
        return {
            "success": False,
            "message": f"basket_affinity_top.csv bulunamadı: {AFFINITY_CSV}",
            "affinity_map": {},
        }

    identity = resolve_store(store_key)

    store_col = find_col(df, [
        "vendor_id",
        "vendor id",
        "vendor",
        "vendor_code",
        "store_code",
        "store",
        "dmart",
        "warehouse_id",
        "warehouse",
    ])

    sku_a_col = find_col(df, [
        "sku_a",
        "source_sku",
        "anchor_sku",
        "base_sku",
        "product_sku",
        "sku_1",
        "sku1",
        "left_sku",
    ])

    sku_b_col = find_col(df, [
        "sku_b",
        "target_sku",
        "related_sku",
        "pair_sku",
        "affinity_sku",
        "sku_2",
        "sku2",
        "right_sku",
    ])

    score_col = find_col(df, [
        "score",
        "affinity_score",
        "confidence",
        "lift",
        "support",
        "orders",
        "co_count",
        "pair_count",
    ])

    if not sku_a_col or not sku_b_col:
        return {
            "success": False,
            "message": "Affinity dosyasında SKU pair kolonları bulunamadı.",
            "columns": list(df.columns),
            "expected_any_of": {
                "sku_a": ["sku_a", "source_sku", "anchor_sku", "base_sku", "sku_1"],
                "sku_b": ["sku_b", "target_sku", "related_sku", "pair_sku", "sku_2"],
            },
            "affinity_map": {},
        }

    aliases = set()
    for a in identity.get("aliases", []):
        if a:
            aliases.add(norm(a))
            aliases.add(str(a).strip().lower())

    if identity.get("vendor_id"):
        aliases.add(norm(identity["vendor_id"]))
        aliases.add(str(identity["vendor_id"]).strip().lower())

    filtered = df

    if store_col:
        filtered = df[df[store_col].map(lambda x: norm(x) in aliases or str(x).strip().lower() in aliases)]

    matched_rows = len(filtered)

    affinity_map = {}
    pair_count = 0

    for _, row in filtered.head(limit).iterrows():
        a = str(row.get(sku_a_col, "")).strip()
        b = str(row.get(sku_b_col, "")).strip()

        if not a or not b or a == b:
            continue

        score = number(row.get(score_col, 1.0), 1.0) if score_col else 1.0

        affinity_map.setdefault(a, []).append({
            "sku": b,
            "score": score,
            "source": "basket_affinity_top.csv",
            "store_vendor_id": identity.get("vendor_id"),
        })

        affinity_map.setdefault(b, []).append({
            "sku": a,
            "score": score,
            "source": "basket_affinity_top.csv",
            "store_vendor_id": identity.get("vendor_id"),
        })

        pair_count += 1

    for sku, partners in affinity_map.items():
        partners.sort(key=lambda x: x.get("score", 0), reverse=True)
        affinity_map[sku] = partners[:20]

    return {
        "success": True,
        "input_store_key": store_key,
        "resolved_store": identity,
        "store_column": store_col,
        "sku_a_column": sku_a_col,
        "sku_b_column": sku_b_col,
        "score_column": score_col,
        "matched_rows": matched_rows,
        "pair_count": pair_count,
        "sku_count": len(affinity_map),
        "affinity_map": affinity_map,
    }
