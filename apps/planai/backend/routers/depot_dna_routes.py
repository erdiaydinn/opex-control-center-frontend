from fastapi import APIRouter, Body, HTTPException
from ._storage_v1 import read_json, write_json, now_iso

router = APIRouter(prefix="/core/depot-dna", tags=["core-depot-dna"])

DEFAULT_DNA = {
    "physical": {
        "floors": 1,
        "has_basement": False,
        "basement_usage": [],
        "total_area_m2": None,
        "picking_area_m2": None,
        "backroom_area_m2": None,
        "ceiling_height_cm": None,
        "avg_aisle_width_cm": 120,
        "main_aisle_width_cm": 150,
        "narrow_aisle_count": 0
    },
    "operations": {
        "avg_daily_orders": None,
        "peak_hours": [],
        "receiving_hours": "",
        "receiving_after_16_preferred": False,
        "receiving_after_16_risk": True,
        "replenishment_model": "mixed",
        "peak_picker_count": None,
        "frozen_pick_last": True,
        "heavy_pick_rule": "bottom_or_late",
        "priority_mode": "operational"
    },
    "fixture_defaults": {
        "main_rack_type": "steel_rack",
        "main_rack_width_cm": 93,
        "main_rack_depth_cm": 43,
        "main_rack_height_cm": 200,
        "main_rack_levels": 6,
        "has_new_gen_steel_rack": False,
        "new_gen_rack_width_cm": 100,
        "new_gen_rack_depth_cm": 60,
        "new_gen_rack_height_cm": 250,
        "new_gen_rack_levels": 6
    },
    "cold_rooms": {
        "has_chilled_room": False,
        "chilled_room_area_m2": 0,
        "chilled_room_clear_height_cm": 220,
        "chilled_room_storage_type": "mixed",
        "chilled_room_picker_enters": True,
        "has_frozen_room": False,
        "frozen_room_area_m2": 0,
        "frozen_room_clear_height_cm": 220,
        "frozen_room_storage_type": "mixed",
        "frozen_room_picker_enters": False
    },
    "object_inventory": {
        "steel_rack_count": 0,
        "steel_rack_new_gen_count": 0,
        "hdr_heavy_rack_count": 0,
        "martek_plus4_count": 0,
        "martek_frozen_minus18_count": 0,
        "algida_chest_freezer_count": 0,
        "ugur_vertical_chiller_count": 0,
        "buffer_rack_count": 0,
        "pallet_zone_count": 0
    }
}

def deep_merge(a, b):
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

@router.get("/{store_code}")
def get_depot_dna(store_code: str):
    data = read_json("depot_dna.json", {})
    key = store_code.lower().strip()
    dna = data.get(key)
    if not dna:
        return {"success": True, "exists": False, "store_code": key, "dna": DEFAULT_DNA}
    return {"success": True, "exists": True, "store_code": key, "dna": deep_merge(DEFAULT_DNA, dna)}

@router.post("/{store_code}")
def save_depot_dna(store_code: str, payload: dict = Body(...)):
    key = store_code.lower().strip()
    if not key:
        raise HTTPException(status_code=400, detail="store_code zorunlu.")
    data = read_json("depot_dna.json", {})
    dna = deep_merge(DEFAULT_DNA, payload or {})
    dna["store_code"] = key
    dna["updated_at"] = now_iso()
    data[key] = dna
    write_json("depot_dna.json", data)
    return {"success": True, "store_code": key, "dna": dna}
