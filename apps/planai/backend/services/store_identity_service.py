from pathlib import Path
import json
import csv
import unicodedata

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

FALLBACK_STORES = [
    {
        "dmart": "Yemeksepeti Market, Fulya (İstanbul)",
        "store_name": "Fulya (İstanbul)",
        "vendor_id": "j3a6",
    },
    {
        "dmart": "Yemeksepeti Market, Anka (İstanbul)",
        "store_name": "Anka (İstanbul)",
        "vendor_id": "u5w4",
    },
]

def norm(value):
    s = str(value or "").strip()
    s = s.replace("Yemeksepeti Market,", "").replace("Yemeksepeti Market", "")
    s = s.replace("İ", "i").replace("I", "i").replace("ı", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    for ch in [",", ";", ".", "-", "_", "(", ")", "[", "]"]:
        s = s.replace(ch, " ")
    return " ".join(s.split())

def read_store_vendor_map_csv():
    path = DATA_DIR / "store_vendor_map.csv"
    if not path.exists():
        return []

    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "dmart": r.get("dmart") or r.get("Dmart") or "",
                "store_name": r.get("store_name") or r.get("Dmart name (without Yemeksepeti Market)") or "",
                "vendor_id": r.get("vendor_id") or r.get("Vendor id") or r.get("vendor") or "",
            })
    return rows

def read_stores_master_json():
    path = DATA_DIR / "stores_master.json"
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    rows = []
    if isinstance(data, dict):
        data = list(data.values())

    for s in data or []:
        rows.append({
            "dmart": s.get("dmart") or s.get("store_name") or s.get("display_name") or "",
            "store_name": s.get("display_name") or s.get("store_name") or s.get("name") or "",
            "vendor_id": s.get("vendor_id") or s.get("store_code") or "",
        })

    return rows

def store_rows():
    rows = []
    rows.extend(read_store_vendor_map_csv())
    rows.extend(read_stores_master_json())
    rows.extend(FALLBACK_STORES)

    cleaned = []
    seen = set()

    for r in rows:
        vendor_id = str(r.get("vendor_id") or "").strip()
        store_name = str(r.get("store_name") or "").strip()
        dmart = str(r.get("dmart") or "").strip()

        if not vendor_id and not store_name and not dmart:
            continue

        key = (vendor_id.lower(), norm(store_name), norm(dmart))
        if key in seen:
            continue

        seen.add(key)
        cleaned.append({
            "vendor_id": vendor_id,
            "store_name": store_name,
            "dmart": dmart,
            "aliases": list({
                vendor_id,
                store_name,
                dmart,
                store_name.replace("Yemeksepeti Market,", "").strip(),
            }),
        })

    return cleaned

def resolve_store(store_key):
    target = norm(store_key)
    target_raw = str(store_key or "").strip().lower()

    for row in store_rows():
        aliases = row.get("aliases") or []

        if target_raw and target_raw == str(row.get("vendor_id", "")).lower():
            return row

        for alias in aliases:
            if target and target == norm(alias):
                return row

    return {
        "vendor_id": str(store_key or "").strip(),
        "store_name": str(store_key or "").strip(),
        "dmart": str(store_key or "").strip(),
        "aliases": [str(store_key or "").strip()],
        "unresolved": True,
    }
