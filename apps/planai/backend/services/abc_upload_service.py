from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, Iterable, List, Tuple
import re

import pandas as pd


REQUIRED_COLUMNS = [
    "Country",
    "Store",
    "Rank",
    "Category L1",
    "Category L2",
    "SKU",
    "Product Name",
    "Barcodes",
    "ABC",
    "On-Hand Qty",
    "Storage Type",
    "Product Image URL",
    "% Stops",
    "% Orders",
]

OPTIONAL_COLUMNS = [
    "Location",
    "Is A Zone",
    "Secondary Location",
]

COLUMN_ALIASES = {
    "% Orders ▼": "% Orders",
    "% Orders ▾": "% Orders",
    "% Orders ↓": "% Orders",
    "% Order": "% Orders",
    "Orders %": "% Orders",
    "Order %": "% Orders",
    "% Stops ▼": "% Stops",
    "Stops %": "% Stops",
    "Stop %": "% Stops",
    "On Hand Qty": "On-Hand Qty",
    "On-Hand Quantity": "On-Hand Qty",
    "Image URL": "Product Image URL",
    "Product Image": "Product Image URL",
    "Image": "Product Image URL",
    "Barcode": "Barcodes",
    "Storage": "Storage Type",
}


def _clean_header(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip())


def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for c in df.columns:
        clean = _clean_header(c)
        renamed[c] = COLUMN_ALIASES.get(clean, clean)
    return df.rename(columns=renamed)


def _is_empty(v: Any) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def text(v: Any, default: str = "") -> str:
    if _is_empty(v):
        return default
    return str(v).strip()


def number(v: Any, default: float = 0.0) -> float:
    if _is_empty(v):
        return default
    try:
        return float(str(v).replace("%", "").replace(",", ".").strip())
    except Exception:
        return default


def integer(v: Any, default: int = 0) -> int:
    try:
        return int(round(number(v, default)))
    except Exception:
        return default


def first_barcode(v: Any) -> str:
    raw = text(v)
    if not raw:
        return ""
    parts = re.split(r"[|;,\s]+", raw)
    return parts[0].strip() if parts else raw


def normalize_storage_hint(v: Any) -> str:
    raw = text(v, "AMBIENT").upper()
    if any(x in raw for x in ["FROZEN", "DONUK", "-18", "ICE"]):
        return "FROZEN"
    if any(x in raw for x in ["CHILLED", "COLD", "SOĞUK", "SOGUK", "+4", "FRIDGE"]):
        return "CHILLED"
    return "AMBIENT"


def read_table_from_upload(content: bytes, filename: str) -> pd.DataFrame:
    name = str(filename or "").lower()
    raw = BytesIO(content)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(raw)
    else:
        try:
            df = pd.read_csv(raw)
        except UnicodeDecodeError:
            raw.seek(0)
            df = pd.read_csv(raw, encoding="utf-8-sig")
    df = df.where(pd.notnull(df), None)
    return normalize_headers(df)


def validate_abc_columns(df: pd.DataFrame) -> Dict[str, Any]:
    columns = list(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    present_optional = [c for c in OPTIONAL_COLUMNS if c in columns]
    return {
        "valid": len(missing) == 0,
        "missing_required": missing,
        "present_optional": present_optional,
        "columns": columns,
    }


def normalize_abc_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "country": text(row.get("Country")),
        "store_name": text(row.get("Store")),
        "rank": integer(row.get("Rank"), 0),
        "category_l1": text(row.get("Category L1"), "GENERAL"),
        "category_l2": text(row.get("Category L2"), "GENERAL"),
        "sku": text(row.get("SKU")),
        "product_name": text(row.get("Product Name")),
        "barcode": first_barcode(row.get("Barcodes")),
        "barcodes_raw": text(row.get("Barcodes")),
        "abc_class": text(row.get("ABC"), "C").upper(),
        "on_hand_qty": number(row.get("On-Hand Qty"), 0),
        "storage_type_hint": normalize_storage_hint(row.get("Storage Type")),
        "image_url": text(row.get("Product Image URL")),
        "order_share_pct": number(row.get("% Orders"), 0),
        "stop_share_pct": number(row.get("% Stops"), 0),
        # Delta-only fields. These are NEVER target placement rules.
        "current_location": text(row.get("Location")),
        "secondary_location": text(row.get("Secondary Location")),
        "is_a_zone": text(row.get("Is A Zone")),
    }


def parse_abc_dataframe(df: pd.DataFrame, strict: bool = True) -> Dict[str, Any]:
    validation = validate_abc_columns(df)
    if strict and not validation["valid"]:
        return {
            "success": False,
            "validation": validation,
            "rows": [],
            "message": "ABC dosyasında zorunlu kolonlar eksik.",
        }

    rows: List[Dict[str, Any]] = []
    skipped = 0
    for raw in df.to_dict(orient="records"):
        item = normalize_abc_row(raw)
        if not item["sku"] and not item["barcode"]:
            skipped += 1
            continue
        rows.append(item)

    with_image = sum(1 for r in rows if r.get("image_url"))
    return {
        "success": True,
        "validation": validation,
        "row_count": len(rows),
        "skipped_rows": skipped,
        "with_image": with_image,
        "without_image": len(rows) - with_image,
        "rows": rows,
        "message": "ABC başarıyla normalize edildi.",
    }


def parse_abc_upload(content: bytes, filename: str, strict: bool = True) -> Dict[str, Any]:
    df = read_table_from_upload(content, filename)
    parsed = parse_abc_dataframe(df, strict=strict)
    parsed["file_name"] = filename
    return parsed
