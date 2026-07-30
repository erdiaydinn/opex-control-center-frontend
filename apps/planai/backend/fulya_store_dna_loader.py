
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Callable
from collections import Counter
import json

DATA_PATH = Path(__file__).resolve().parent / "data" / "fulya_depo_layout.json"

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()

def _n(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).replace(",", "."))
    except Exception:
        return default

def _i(v: Any, default: int = 0) -> int:
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(str(v).replace(",", ".")))
    except Exception:
        return default

def load_fulya_dna(path: Path = DATA_PATH) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Fulya DNA file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def _storage(template: Dict[str, Any], fallback: str = "AMBIENT") -> str:
    st = _s(template.get("storage_type") or fallback).upper()
    if "FROZEN" in st or "-18" in st:
        return "FROZEN"
    if "CHILLED" in st or "+4" in st:
        return "CHILLED"
    return "AMBIENT"

def _make_shelves(make_shelves: Callable | None, count: int, storage: str, width: float, height: float, depth: float):
    count = max(1, int(count or 1))
    shelf_h = round((height or 200) / count, 2)
    max_w = 70 if storage == "FROZEN" else 60 if storage == "CHILLED" else 45
    if make_shelves:
        try:
            return make_shelves(count, storage, width, shelf_h, depth, max_w)
        except TypeError:
            try:
                return make_shelves(storage, count, width, depth, height, shelf_h)
            except Exception:
                pass
    return [
        {
            "shelf_no": i + 1,
            "shelf_width_cm": width,
            "shelf_height_cm": shelf_h,
            "shelf_depth_cm": depth,
            "max_weight_kg": max_w,
            "zone_type": "bottom" if i == 0 else "top" if i == count - 1 else "eye" if i in [count//2, max(0, count//2-1)] else "mid",
            "allowed_storage_type": storage,
            "products": [],
            "used_width_cm": 0,
            "used_weight_kg": 0,
            "used": 0,
        }
        for i in range(count)
    ]

def _module(module_id, side, template, make_shelves, source="fulya_store_dna"):
    storage = _storage(template)
    width = _n(template.get("width_cm"), 100)
    depth = _n(template.get("depth_cm"), 50)
    height = _n(template.get("height_cm"), 210)
    count = _i(template.get("shelf_count"), 6)
    mtype = _s(template.get("fixture_type") or ("freezer" if storage == "FROZEN" else "fridge" if storage == "CHILLED" else "regular_shelf"))
    return {
        "module_id": module_id,
        "module_no": module_id,
        "side": side,
        "module_type": mtype,
        "fixture_type": mtype,
        "storage_type": storage,
        "module_width_cm": width,
        "module_depth_cm": depth,
        "module_height_cm": height,
        "assignment_rule": None,
        "source": source,
        "shelves": _make_shelves(make_shelves, count, storage, width, height, depth),
    }

def _aisle(aisle_id, modules, row, position, zone_type="AMBIENT_ZONE", source="fulya_store_dna"):
    return {
        "aisle_id": aisle_id,
        "row": row,
        "position": position,
        "direction": "LTR" if row % 2 else "RTL",
        "distance_to_dispatch": row * 10 + position,
        "aisle_type": "fulya_store_dna",
        "zone_type": zone_type,
        "source": source,
        "layout_position": {"grid_x": position * 8, "grid_y": row * 6, "rotation": 0},
        "modules": modules,
    }

def build_fulya_layout(make_shelves: Callable | None = None, path: Path = DATA_PATH) -> Dict[str, Any]:
    dna = load_fulya_dna(path)
    templates = dna.get("fixture_templates") or {}
    aisles = []
    row = 1
    pos = 1

    # Ambient aisles: keep every real aisle as its own UI/engine aisle.
    for item in dna.get("ambient_layout") or []:
        aid = _s(item.get("aisle_id"))
        modules = []
        mid = 1
        for face in item.get("faces") or []:
            t = templates.get(_s(face.get("template_id")), {})
            side_raw = _s(face.get("side")).lower()
            side = "L" if side_raw in ["left", "l", "sol"] else "R" if side_raw in ["right", "r", "sağ", "sag"] else side_raw.upper() or "L"
            for _ in range(_i(face.get("module_count"), 0)):
                m = _module(mid, side, t, make_shelves, source=f"fulya_{_s(face.get('face_id'))}")
                m["face_id"] = _s(face.get("face_id"))
                modules.append(m)
                mid += 1
        if modules:
            aisles.append(_aisle(aid, modules, row, pos, "AMBIENT_ZONE"))
            pos += 1
            if pos > 4:
                row += 1
                pos = 1

    cold = dna.get("cold_and_frozen_assets") or {}

    # +4 room
    cr = cold.get("chilled_room_plus_4") or {}
    internal = cr.get("internal_racks") or {}
    if internal:
        t = dict(templates.get(_s(internal.get("template_id")), {}))
        t["storage_type"] = "CHILLED"
        t["shelf_count"] = _i(internal.get("shelf_count_per_module"), _i(t.get("shelf_count"), 6))
        mods = [_module(i+1, "INTERNAL", t, make_shelves, source="fulya_chilled_room") for i in range(_i(internal.get("module_count"), 0))]
        aisles.append(_aisle("PLUS4_ROOM", mods, row+1, 1, "COLD_ZONE"))

    # Martek coolers grouped by storage so UI has meaningful corridors.
    mc = cold.get("market_coolers") or {}
    if mc:
        tbase = templates.get(_s(mc.get("template_id")), {})
        for part in mc.get("breakdown") or []:
            st = _storage(part)
            t = dict(tbase)
            t["storage_type"] = st
            t["fixture_type"] = "market_cooler" if st == "CHILLED" else "market_freezer"
            t["shelf_count"] = 5 if st == "CHILLED" else 4
            count = _i(part.get("count"), 0)
            mods = [_module(i+1, "DOOR", t, make_shelves, source="fulya_martek") for i in range(count)]
            if mods:
                aisles.append(_aisle("MARTEK+4" if st == "CHILLED" else "MARTEK-18", mods, row+1, 2 if st == "CHILLED" else 3, "COLD_ZONE" if st == "CHILLED" else "FROZEN_ZONE"))

    # Frozen rooms
    fr_idx = 1
    for room in cold.get("frozen_rooms_minus_18") or []:
        internal = room.get("internal_racks_or_pallet_positions") or {}
        t = dict(templates.get(_s(internal.get("template_id")), {}))
        t["storage_type"] = "FROZEN"
        t["fixture_type"] = t.get("fixture_type") or "freezer_room_rack"
        t["shelf_count"] = _i(t.get("shelf_count"), 4) or 4
        count = _i(internal.get("count"), 0)
        mods = [_module(i+1, "INTERNAL", t, make_shelves, source="fulya_frozen_room") for i in range(count)]
        if mods:
            aisles.append(_aisle(_s(room.get("fixture_id")) or f"FROZEN_ROOM_{fr_idx}", mods, row+2, fr_idx, "FROZEN_ZONE"))
            fr_idx += 1

    # Fruit veg
    fv = cold.get("fruit_vegetable_rack") or {}
    if fv:
        t = dict(templates.get(_s(fv.get("template_id")), {}))
        t["storage_type"] = "AMBIENT"
        t["fixture_type"] = "fruit_vegetable_rack"
        t["shelf_count"] = _i(fv.get("shelf_count_per_module"), _i(t.get("shelf_count"), 4))
        mods = [_module(i+1, "PRODUCE", t, make_shelves, source="fulya_fruit_veg") for i in range(_i(fv.get("module_count"), 0))]
        if mods:
            aisles.append(_aisle("FRUIT_VEG", mods, row+3, 1, "PRODUCE_ZONE"))

    # Algida
    alg = cold.get("algida_cabinets") or {}
    if alg:
        t = {"fixture_type":"algida_freezer", "storage_type":"FROZEN", "width_cm":100, "depth_cm":70, "height_cm":120, "shelf_count":3}
        mods = [_module(i+1, "DOOR", t, make_shelves, source="fulya_algida") for i in range(_i(alg.get("count"), 0))]
        if mods:
            aisles.append(_aisle("ALGIDA", mods, row+3, 2, "FROZEN_ZONE"))

    summary = capacity_summary_from_aisles(aisles)
    return {
        "store_code": dna.get("store_code", "FULYA"),
        "store_name": dna.get("store_name", "Fulya (İstanbul)"),
        "source": "fulya_store_dna_v2_aisles",
        "route_strategy": "FULYA_STORE_DNA_REAL_FIXTURE_CAPACITY",
        "aisles": aisles,
        "layout_objects": [],
        "fixture_capacity_summary": summary,
        "fulya_original_capacity_summary": dna.get("capacity_summary", {}),
    }

def capacity_summary_from_aisles(aisles):
    by_storage = Counter()
    shelves_by_storage = Counter()
    modules_by_aisle = {}
    for a in aisles:
        modules_by_aisle[a.get("aisle_id")] = len(a.get("modules") or [])
        for m in a.get("modules") or []:
            st = _storage(m, "AMBIENT")
            by_storage[st] += 1
            shelves_by_storage[st] += len(m.get("shelves") or [])
    return {
        "aisle_count": len(aisles),
        "module_count": sum(modules_by_aisle.values()),
        "modules_by_storage": dict(by_storage),
        "shelves_by_storage": dict(shelves_by_storage),
        "modules_by_aisle": modules_by_aisle,
    }

def is_fulya_layout_request(layout: Dict[str, Any] | None) -> bool:
    if not layout:
        return False
    txt = " ".join(_s(layout.get(k)) for k in ["store_code", "store_name", "dmart", "depot", "active_depot"]).lower()
    return "fulya" in txt

def should_use_fulya_layout(layout: Dict[str, Any] | None) -> bool:
    return is_fulya_layout_request(layout)
