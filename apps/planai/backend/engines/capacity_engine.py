from typing import Dict, Any

def n(v, d=0.0):
    try:
        if v is None or str(v).strip() == "":
            return d
        return float(str(v).replace(",", "."))
    except Exception:
        return d

def fixture_volume_cm3(f: Dict[str, Any]) -> float:
    # Area based objects: cold rooms, frozen rooms, basement/backroom areas.
    if (f.get("capacity_model") == "area_based") or str(f.get("type", "")).endswith("_room"):
        area_m2 = n(f.get("area_m2") or f.get("room_area_m2"), 0)
        clear_height_cm = n(f.get("clear_height_cm") or f.get("height_cm"), 220)
        return area_m2 * 10000 * clear_height_cm

    dims = f.get("dimensions_cm") or {}
    return n(dims.get("width") or f.get("width_cm"), 0) * n(dims.get("depth") or f.get("depth_cm"), 0) * n(dims.get("height") or f.get("height_cm"), 0)

def room_from_dna(store_code: str, dna: Dict[str, Any]):
    cold = dna.get("cold_rooms") or {}
    rooms = []
    if cold.get("has_chilled_room"):
        rooms.append({
            "id": f"{store_code}-CHILLED-ROOM",
            "type": "chilled_room",
            "zone": "CHILLED",
            "capacity_model": "area_based",
            "area_m2": n(cold.get("chilled_room_area_m2"), 0),
            "clear_height_cm": n(cold.get("chilled_room_clear_height_cm"), 220),
            "usable_capacity_pct": 0.68,
            "storage_type": cold.get("chilled_room_storage_type") or "mixed",
            "picker_enters": bool(cold.get("chilled_room_picker_enters", True)),
        })
    if cold.get("has_frozen_room"):
        rooms.append({
            "id": f"{store_code}-FROZEN-ROOM",
            "type": "frozen_room",
            "zone": "FROZEN",
            "capacity_model": "area_based",
            "area_m2": n(cold.get("frozen_room_area_m2"), 0),
            "clear_height_cm": n(cold.get("frozen_room_clear_height_cm"), 220),
            "usable_capacity_pct": 0.62,
            "storage_type": cold.get("frozen_room_storage_type") or "mixed",
            "picker_enters": bool(cold.get("frozen_room_picker_enters", False)),
        })
    return rooms

def score_capacity(layout: Dict[str, Any], dna: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fixtures = list(layout.get("fixtures", []) or [])
    store_code = str(layout.get("store_code") or (dna or {}).get("store_code") or "STORE").upper()
    if dna:
        fixtures.extend(room_from_dna(store_code, dna))

    placements = layout.get("placements", []) or []
    by_fixture = {}
    total_volume = 0
    usable_volume = 0

    for f in fixtures:
        fid = str(f.get("id"))
        volume = fixture_volume_cm3(f)
        usable_pct = n(f.get("usable_capacity_pct"), 0.9)
        item = {
            "fixture_id": fid,
            "type": f.get("type"),
            "zone": f.get("zone") or f.get("storage_zone"),
            "capacity_model": f.get("capacity_model") or "fixture_volume",
            "gross_volume_l": round(volume / 1000, 1),
            "usable_volume_l": round(volume * usable_pct / 1000, 1),
            "placement_count": 0,
            "estimated_used_l": 0,
            "utilization_pct": 0,
        }
        if f.get("capacity_model") == "area_based":
            item["area_m2"] = n(f.get("area_m2"), 0)
            item["storage_type"] = f.get("storage_type")
            item["picker_enters"] = f.get("picker_enters")
        by_fixture[fid] = item
        total_volume += volume
        usable_volume += volume * usable_pct

    for p in placements:
        fid = str(p.get("fixture_id"))
        qty = n(p.get("front_count"), 1) * max(1, n(p.get("depth_count"), 1)) * max(1, n(p.get("stack_count"), 1))
        product_volume = n(p.get("product_volume_cm3"), 0)
        used_l = qty * product_volume / 1000
        if fid in by_fixture:
            by_fixture[fid]["placement_count"] += 1
            by_fixture[fid]["estimated_used_l"] += used_l

    for item in by_fixture.values():
        usable = item["usable_volume_l"] or 1
        item["estimated_used_l"] = round(item["estimated_used_l"], 1)
        item["utilization_pct"] = round(min(999, item["estimated_used_l"] / usable * 100), 1)

    cold_rooms = [x for x in by_fixture.values() if x.get("capacity_model") == "area_based"]
    return {
        "total_gross_volume_l": round(total_volume / 1000, 1),
        "total_usable_volume_l": round(usable_volume / 1000, 1),
        "fixtures": list(by_fixture.values()),
        "cold_rooms": cold_rooms,
        "critical": [x for x in by_fixture.values() if x["utilization_pct"] >= 90],
        "warnings": [x for x in by_fixture.values() if 80 <= x["utilization_pct"] < 90],
    }
