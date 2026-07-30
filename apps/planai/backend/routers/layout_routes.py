from fastapi import APIRouter, Body, HTTPException
from ._storage_v1 import read_json, write_json, now_iso

router = APIRouter(prefix="/core/layouts", tags=["core-layouts"])

EMPTY_LAYOUT = {
    "version": "core_v1",
    "warehouse": {},
    "floors": [{"floor_id": "GROUND", "label": "Ana Kat", "level": 0}],
    "fixtures": [],
    "placements": [],
    "zones": [],
    "metadata": {}
}

@router.get("/{store_code}")
def get_layout(store_code: str):
    key = store_code.lower().strip()
    data = read_json("layouts.json", {})
    layout = data.get(key)
    if not layout:
        return {"success": True, "exists": False, "store_code": key, "layout": {**EMPTY_LAYOUT, "warehouse": {"store_code": key}}}
    return {"success": True, "exists": True, "store_code": key, "layout": layout}

@router.post("/{store_code}")
def save_layout(store_code: str, payload: dict = Body(...)):
    key = store_code.lower().strip()
    if not key:
        raise HTTPException(status_code=400, detail="store_code zorunlu.")
    data = read_json("layouts.json", {})
    history = read_json("layout_history.json", [])
    layout = payload.get("layout") if "layout" in payload else payload
    layout.setdefault("version", "core_v1")
    layout.setdefault("metadata", {})
    layout["metadata"]["updated_at"] = now_iso()
    layout["metadata"]["store_code"] = key
    data[key] = layout
    history.append({"store_code": key, "saved_at": now_iso(), "summary": {
        "fixtures": len(layout.get("fixtures", [])),
        "placements": len(layout.get("placements", [])),
        "floors": len(layout.get("floors", []))
    }})
    write_json("layouts.json", data)
    write_json("layout_history.json", history[-500:])
    return {"success": True, "store_code": key, "layout": layout}