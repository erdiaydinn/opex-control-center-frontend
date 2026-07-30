"""Store DNA persistence backed by the approved depot/equipment master."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


BACKEND_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PLONAGRAM_DATA_DIR", str(BACKEND_ROOT / "data")))
STORES_PATH = DATA_DIR / "stores_master.json"
DNA_PATH = DATA_DIR / "store_dna.json"
LOCK = threading.Lock()


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _aisle_label(index: int) -> str:
    value = index + 1
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def list_stores() -> List[Dict[str, Any]]:
    return [
        item for item in _read(STORES_PATH, [])
        if isinstance(item, dict) and item.get("store_code")
    ]


def get_store(store_code: str) -> Optional[Dict[str, Any]]:
    target = str(store_code or "").strip().upper()
    for store in list_stores():
        if target in {
            str(store.get("store_code", "")).upper(),
            str(store.get("vendor_id", "")).upper(),
        }:
            return store
    return None


def _module(side: str, index: int, fixture_type: str, shelf_count: int) -> Dict[str, Any]:
    specs = {
        "steel_rack": ("AMBIENT", 100, 50, 210),
        "new_generation_steel_rack": ("AMBIENT", 100, 60, 250),
    }
    zone, width, depth, height = specs.get(fixture_type, specs["steel_rack"])
    return {
        "id": f"{side}{index + 1}",
        "side": side,
        "module_id": index + 1,
        "fixture_type": fixture_type,
        "zone": zone,
        "width_cm": width,
        "depth_cm": depth,
        "height_cm": height,
        "shelf_count": shelf_count,
    }


def build_aisles(dna: Dict[str, Any]) -> List[Dict[str, Any]]:
    count = max(1, min(int(dna.get("aisle_count") or 8), 100))
    left_count = max(0, min(int(dna.get("left_modules") or 0), 30))
    right_count = max(0, min(int(dna.get("right_modules") or 0), 30))
    shelf_count = max(1, min(int(dna.get("shelves_per_rack") or 6), 12))
    left_type = str(dna.get("left_fixture_type") or "steel_rack")
    right_type = str(dna.get("right_fixture_type") or "steel_rack")
    return [
        {
            "aisle_id": _aisle_label(index),
            "left_modules": [
                _module("L", module_index, left_type, shelf_count)
                for module_index in range(left_count)
            ],
            "right_modules": [
                _module("R", module_index, right_type, shelf_count)
                for module_index in range(right_count)
            ],
        }
        for index in range(count)
    ]


def build_layout_objects(dna: Dict[str, Any]) -> List[Dict[str, Any]]:
    objects: List[Dict[str, Any]] = []
    aisles = build_aisles(dna)
    for index, aisle in enumerate(aisles):
        row = index // 8
        column = index % 8
        objects.append({
            "id": aisle["aisle_id"],
            "aisle_id": aisle["aisle_id"],
            "label": f"Koridor {aisle['aisle_id']}",
            "type": "corridor",
            "fixture_type": str(dna.get("left_fixture_type") or "steel_rack"),
            "zone": "AMBIENT",
            "x": 4 + column * 11.5,
            "y": 5 + row * 22,
            "w": 8.5,
            "d": 16,
            "h": 2.1,
            "modules": len(aisle["left_modules"]) + len(aisle["right_modules"]),
            "shelf_count": int(dna.get("shelves_per_rack") or 6),
            "isRack": True,
        })

    fixture_specs = [
        ("algida_count", "ALGIDA", "Algida Donuk", "ice_cream_chest_freezer_medium", "FROZEN", 4.5, 4.5, 1.1),
        ("martek_plus4_count", "MARTEK4", "Martek +4", "martek_plus4", "CHILLED", 4.5, 3.8, 2.1),
        ("martek_frozen_count", "MARTEK18", "Martek -18", "martek_frozen_minus18", "FROZEN", 4.5, 3.8, 2.1),
        ("horizontal_fridge_count", "YATAY18", "Yatay -18", "martek_frozen_minus18", "FROZEN", 4.8, 4.2, 1.1),
        ("produce_module_count", "PRODUCE", "Meyve Sebze", "produce_shelf", "PRODUCE", 4.5, 3.8, 1.8),
        ("new_gen_steel_rack_count", "NEWSTEEL", "Yeni Nesil Çelik", "new_generation_steel_rack", "AMBIENT", 4.5, 3.8, 2.5),
    ]
    base_index = len(objects)
    for field, prefix, label, fixture_type, zone, width, depth, height in fixture_specs:
        count = max(0, min(int(dna.get(field) or 0), 200))
        for item_index in range(count):
            position = base_index + len(objects)
            objects.append({
                "id": f"{prefix}-{item_index + 1}",
                "label": f"{label} {item_index + 1}",
                "type": "fixture",
                "fixture_type": fixture_type,
                "zone": zone,
                "x": 4 + (position % 14) * 6.7,
                "y": 72 + ((position // 14) % 4) * 6.5,
                "w": width,
                "d": depth,
                "h": height,
                "modules": 1,
                "shelf_count": (
                    5 if fixture_type == "martek_plus4"
                    else 4 if fixture_type == "martek_frozen_minus18"
                    else 3
                ),
                "isRack": True,
            })
    return objects


def default_dna(store_code: str) -> Optional[Dict[str, Any]]:
    store = get_store(store_code)
    if not store:
        return None
    dna = {
        "store_code": store["store_code"],
        "store_name": store.get("display_name") or store.get("store_name"),
        **(store.get("default_dna") or {}),
        "equipment_inventory": store.get("equipment_inventory") or {},
        "equipment_summary": store.get("equipment_summary") or {},
        "inventory_source": store.get("inventory_source"),
        "inventory_note": store.get("inventory_note"),
        "source": "approved_store_master",
    }
    dna["aisle_module_config"] = build_aisles(dna)
    dna["layout_objects"] = build_layout_objects(dna)
    dna["fixture_summary"] = {
        "total_objects": len(dna["layout_objects"]),
        "total_modules": sum(
            len(aisle["left_modules"]) + len(aisle["right_modules"])
            for aisle in dna["aisle_module_config"]
        ),
        "total_shelves": sum(
            module["shelf_count"]
            for aisle in dna["aisle_module_config"]
            for module in [*aisle["left_modules"], *aisle["right_modules"]]
        ),
    }
    return dna


def get_store_dna(store_code: str) -> Optional[Dict[str, Any]]:
    target = str(store_code or "").strip().upper()
    saved = _read(DNA_PATH, {})
    if isinstance(saved, dict) and isinstance(saved.get(target), dict):
        dna = dict(saved[target])
        dna["layout_objects"] = build_layout_objects(dna)
        dna["aisle_module_config"] = build_aisles(dna)
        return dna
    return default_dna(target)


def save_store_dna(store_code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    store = get_store(store_code)
    if not store:
        raise KeyError(store_code)
    base = default_dna(store["store_code"]) or {}
    clean = {
        **base,
        **dict(payload or {}),
        "store_code": store["store_code"],
        "store_name": store.get("display_name") or store.get("store_name"),
        "source": "user_approved_store_dna",
    }
    clean["aisle_module_config"] = build_aisles(clean)
    clean["layout_objects"] = build_layout_objects(clean)
    with LOCK:
        saved = _read(DNA_PATH, {})
        if not isinstance(saved, dict):
            saved = {}
        persisted = {
            key: value for key, value in clean.items()
            if key not in {"layout_objects", "aisle_module_config"}
        }
        saved[store["store_code"]] = persisted
        _write(DNA_PATH, saved)
    return clean
