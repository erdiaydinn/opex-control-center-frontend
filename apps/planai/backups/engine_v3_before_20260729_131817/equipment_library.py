"""Canonical fixture/equipment catalog shared by layout, 2D and 3D clients."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


EQUIPMENT: List[Dict[str, Any]] = [
    {
        "equipment_id": "FX-10060",
        "name": "Yeni nesil çelik raf",
        "name_en": "Steel shelf",
        "type": "steel_shelf",
        "storage_type": "AMBIENT",
        "module_width_cm": 100,
        "module_depth_cm": 60,
        "module_height_cm": 250,
        "shelf_count": 6,
        "shelf_height_cm": 35,
        "max_weight_kg": 45,
        "supported_depots": ["ANKA", "FULYA"],
    },
    {
        "equipment_id": "FX-ALGIDA-4D",
        "name": "Algida 4 kapaklı dondurucu",
        "name_en": "Algida four-door freezer",
        "type": "algida_fridge",
        "storage_type": "FROZEN",
        "module_width_cm": 300,
        "module_depth_cm": 90,
        "module_height_cm": 210,
        "shelf_count": 4,
        "shelf_height_cm": 40,
        "max_weight_kg": 70,
        "supported_depots": ["ANKA", "GUVEN_FR"],
    },
    {
        "equipment_id": "FX-HZ-150",
        "name": "Yatay donuk/soğuk dolap",
        "name_en": "Horizontal frozen/chilled cabinet",
        "type": "horizontal_fridge",
        "storage_type": "FROZEN",
        "module_width_cm": 150,
        "module_depth_cm": 90,
        "module_height_cm": 110,
        "shelf_count": 2,
        "shelf_height_cm": 45,
        "max_weight_kg": 70,
        "supported_depots": ["ANKA"],
    },
    {
        "equipment_id": "FX-MS-120",
        "name": "Meyve sebze 120x60 raf",
        "name_en": "Produce shelf",
        "type": "produce_shelf",
        "storage_type": "AMBIENT",
        "module_width_cm": 120,
        "module_depth_cm": 60,
        "module_height_cm": 180,
        "shelf_count": 4,
        "shelf_height_cm": 40,
        "max_weight_kg": 60,
        "supported_depots": ["ANKA", "SUKRUPASA"],
    },
    {
        "equipment_id": "FX-ROOM-C4",
        "name": "+4 soğuk oda",
        "name_en": "+4 chilled room",
        "type": "chilled_room",
        "storage_type": "CHILLED",
        "module_width_cm": 2000,
        "module_depth_cm": 1200,
        "module_height_cm": 320,
        "shelf_count": 0,
        "shelf_height_cm": 0,
        "max_weight_kg": 0,
        "supported_depots": ["ANKA", "FULYA", "GUVEN_FR"],
    },
    {
        "equipment_id": "FX-ROOM-F18",
        "name": "-18 donuk oda",
        "name_en": "-18 frozen room",
        "type": "frozen_room",
        "storage_type": "FROZEN",
        "module_width_cm": 2000,
        "module_depth_cm": 1200,
        "module_height_cm": 320,
        "shelf_count": 0,
        "shelf_height_cm": 0,
        "max_weight_kg": 0,
        "supported_depots": ["ANKA", "FULYA"],
    },
    {
        "equipment_id": "FX-MARTEK-C4",
        "name": "Martek +4 modül",
        "name_en": "Martek +4 cooler module",
        "type": "martek_chilled",
        "storage_type": "CHILLED",
        "module_width_cm": 150,
        "module_depth_cm": 60,
        "module_height_cm": 200,
        "shelf_count": 5,
        "shelf_height_cm": 35,
        "max_weight_kg": 60,
        "supported_depots": ["ANKA", "FULYA"],
    },
    {
        "equipment_id": "FX-MARTEK-F18",
        "name": "Martek -18 modül",
        "name_en": "Martek -18 freezer module",
        "type": "martek_frozen",
        "storage_type": "FROZEN",
        "module_width_cm": 150,
        "module_depth_cm": 65,
        "module_height_cm": 200,
        "shelf_count": 4,
        "shelf_height_cm": 40,
        "max_weight_kg": 70,
        "supported_depots": ["ANKA", "FULYA"],
    },
    {
        "equipment_id": "FX-DISPATCH-HDR",
        "name": "Sevkiyat HDR rafı",
        "name_en": "Dispatch HDR rack",
        "type": "dispatch_hdr",
        "storage_type": "AMBIENT",
        "module_width_cm": 90,
        "module_depth_cm": 60,
        "module_height_cm": 250,
        "shelf_count": 6,
        "shelf_height_cm": 35,
        "max_weight_kg": 60,
        "supported_depots": ["ALL"],
    },
]


def list_equipment(query: str = "", storage_type: str = "") -> List[Dict[str, Any]]:
    q = str(query or "").strip().casefold()
    storage = str(storage_type or "").strip().upper()
    rows = []
    for item in EQUIPMENT:
        hay = " ".join(str(item.get(k, "")) for k in ("equipment_id", "name", "name_en", "type", "storage_type")).casefold()
        if q and q not in hay:
            continue
        if storage and item.get("storage_type") != storage:
            continue
        rows.append(deepcopy(item))
    return rows


def get_equipment(equipment_id: str) -> Dict[str, Any] | None:
    needle = str(equipment_id or "").strip().casefold()
    return next((deepcopy(x) for x in EQUIPMENT if str(x.get("equipment_id", "")).casefold() == needle), None)


def equipment_to_layout_object(equipment: Dict[str, Any], *, object_id: str, x: float = 0, y: float = 0) -> Dict[str, Any]:
    """Return one canonical object shape consumed by both 2D and 3D editors."""
    item = deepcopy(equipment)
    return {
        "object_id": object_id,
        "equipment_id": item.get("equipment_id"),
        "object_type": item.get("type"),
        "label": item.get("name"),
        "zone": item.get("storage_type"),
        "x": float(x or 0),
        "y": float(y or 0),
        "width": float(item.get("module_width_cm") or 0) / 100,
        "depth": float(item.get("module_depth_cm") or 0) / 100,
        "height": float(item.get("module_height_cm") or 0) / 100,
        "module_width_cm": item.get("module_width_cm"),
        "module_depth_cm": item.get("module_depth_cm"),
        "module_height_cm": item.get("module_height_cm"),
        "shelf_count": item.get("shelf_count"),
        "storage_type": item.get("storage_type"),
    }

