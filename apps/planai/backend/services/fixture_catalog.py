"""
PLONAGRAM OS V1.7.4 - Default Darkstore Fixture Catalog

This catalog is intentionally explicit. It separates temperature/storage hard
constraints from merchandising adjacency rules so ambient racks can hold both
food and non-food, while odor/non-food is isolated from food at shelf/module
level.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


STORAGE_CLASSES = {
    "AMBIENT",
    "AMBIENT_HEAVY",
    "CHILLED",
    "FROZEN",
    "ICE_CREAM",
    "FRESH_PRODUCE_AMBIENT",
    "FRESH_PRODUCE_CHILLED",
    "BULK",
    "OPERATIONAL",
    "STRUCTURAL",
}

# Fixture keys are stable API/data-contract values. Labels can be translated in UI.
FIXTURE_CATALOG: Dict[str, Dict[str, Any]] = {
    "REGULAR_AMBIENT_RACK": {
        "fixture_key": "REGULAR_AMBIENT_RACK",
        "label": "Klasik Ambient Raf",
        "family": "rack",
        "storage_classes": ["AMBIENT"],
        "default_width_cm": 100,
        "default_depth_cm": 50,
        "default_height_cm": 210,
        "default_shelf_count": 6,
        "default_max_weight_kg": 45,
        "allowed_merch_groups": ["FOOD_AMBIENT", "NON_FOOD_NEUTRAL", "NON_FOOD_ODOR"],
        "forbidden_storage_classes": ["CHILLED", "FROZEN", "ICE_CREAM", "FRESH_PRODUCE_AMBIENT", "FRESH_PRODUCE_CHILLED"],
        "hard_rules": ["food_and_odor_not_same_shelf", "prefer_odor_back_zone"],
        "notes": "Deterjan/kokulu non-food ambient rafa girebilir; gıda ile yan yana aynı rafta olamaz.",
    },
    "NEW_GEN_STEEL_RACK": {
        "fixture_key": "NEW_GEN_STEEL_RACK",
        "label": "Yeni Nesil Çelik Raf",
        "family": "rack",
        "storage_classes": ["AMBIENT", "AMBIENT_HEAVY"],
        "default_width_cm": 100,
        "default_depth_cm": 60,
        "default_height_cm": 250,
        "default_shelf_count": 6,
        "default_max_weight_kg": 80,
        "allowed_merch_groups": ["FOOD_AMBIENT", "NON_FOOD_NEUTRAL", "NON_FOOD_ODOR", "HEAVY_AMBIENT"],
        "forbidden_storage_classes": ["CHILLED", "FROZEN", "ICE_CREAM"],
        "hard_rules": ["food_and_odor_not_same_shelf", "heavy_product_bottom_preferred"],
    },
    "HEAVY_BOTTOM_RACK": {
        "fixture_key": "HEAVY_BOTTOM_RACK",
        "label": "Ağır Ürün Rafı",
        "family": "heavy_rack",
        "storage_classes": ["AMBIENT_HEAVY", "AMBIENT"],
        "default_width_cm": 100,
        "default_depth_cm": 60,
        "default_height_cm": 180,
        "default_shelf_count": 4,
        "default_max_weight_kg": 120,
        "allowed_merch_groups": ["HEAVY_AMBIENT", "FOOD_AMBIENT", "NON_FOOD_NEUTRAL"],
        "hard_rules": ["heavy_product_bottom_preferred"],
    },
    "MARTEK_CHILLED": {
        "fixture_key": "MARTEK_CHILLED",
        "label": "Martek +4 Dolap",
        "family": "cooler",
        "storage_classes": ["CHILLED"],
        "temperature_c": "+4",
        "default_width_cm": 120,
        "default_depth_cm": 65,
        "default_height_cm": 200,
        "default_shelf_count": 5,
        "default_max_weight_kg": 60,
        "allowed_merch_groups": ["FOOD_CHILLED"],
        "forbidden_storage_classes": ["AMBIENT", "FROZEN", "ICE_CREAM"],
    },
    "MARTEK_FROZEN": {
        "fixture_key": "MARTEK_FROZEN",
        "label": "Martek -18 Dolap",
        "family": "freezer",
        "storage_classes": ["FROZEN"],
        "temperature_c": "-18",
        "default_width_cm": 120,
        "default_depth_cm": 70,
        "default_height_cm": 200,
        "default_shelf_count": 4,
        "default_max_weight_kg": 70,
        "allowed_merch_groups": ["FOOD_FROZEN", "BAKERY_FROZEN"],
        "forbidden_storage_classes": ["AMBIENT", "CHILLED", "ICE_CREAM"],
    },
    "ALGIDA_FREEZER": {
        "fixture_key": "ALGIDA_FREEZER",
        "label": "Algida Dondurma Dolabı",
        "family": "ice_cream_freezer",
        "storage_classes": ["ICE_CREAM"],
        "temperature_c": "-22",
        "brand_lock": ["ALGIDA"],
        "default_width_cm": 120,
        "default_depth_cm": 70,
        "default_height_cm": 190,
        "default_shelf_count": 5,
        "default_max_weight_kg": 55,
        "allowed_merch_groups": ["ICE_CREAM"],
        "forbidden_storage_classes": ["AMBIENT", "CHILLED", "FROZEN"],
    },
    "HORIZONTAL_FREEZER": {
        "fixture_key": "HORIZONTAL_FREEZER",
        "label": "Yatay Donuk Dolap",
        "family": "horizontal_freezer",
        "storage_classes": ["FROZEN"],
        "temperature_c": "-18",
        "default_width_cm": 150,
        "default_depth_cm": 70,
        "default_height_cm": 90,
        "default_shelf_count": 2,
        "default_max_weight_kg": 80,
        "allowed_merch_groups": ["FOOD_FROZEN", "BAKERY_FROZEN"],
        "forbidden_storage_classes": ["AMBIENT", "CHILLED", "ICE_CREAM"],
    },
    "PRODUCE_AMBIENT_SHELF": {
        "fixture_key": "PRODUCE_AMBIENT_SHELF",
        "label": "Meyve Sebze Ambient Rafı",
        "family": "produce",
        "storage_classes": ["FRESH_PRODUCE_AMBIENT"],
        "default_width_cm": 120,
        "default_depth_cm": 60,
        "default_height_cm": 160,
        "default_shelf_count": 4,
        "default_max_weight_kg": 50,
        "allowed_merch_groups": ["PRODUCE_AMBIENT"],
        "forbidden_storage_classes": ["AMBIENT", "CHILLED", "FROZEN", "ICE_CREAM"],
    },
    "PRODUCE_CHILLED_SHELF": {
        "fixture_key": "PRODUCE_CHILLED_SHELF",
        "label": "Taze Yeşillik / Produce +8 Alanı",
        "family": "produce_chilled",
        "storage_classes": ["FRESH_PRODUCE_CHILLED"],
        "temperature_c": "+8/+12",
        "default_width_cm": 120,
        "default_depth_cm": 60,
        "default_height_cm": 180,
        "default_shelf_count": 4,
        "default_max_weight_kg": 45,
        "allowed_merch_groups": ["PRODUCE_CHILLED"],
    },
    "CHILLED_ROOM": {
        "fixture_key": "CHILLED_ROOM",
        "label": "Soğuk Oda",
        "family": "room",
        "storage_classes": ["CHILLED"],
        "temperature_c": "+4",
        "default_width_cm": 300,
        "default_depth_cm": 250,
        "default_height_cm": 240,
        "default_shelf_count": 1,
        "default_max_weight_kg": 500,
        "capacity_metric": "sqm_and_floor_area",
        "allowed_merch_groups": ["FOOD_CHILLED"],
    },
    "FROZEN_ROOM": {
        "fixture_key": "FROZEN_ROOM",
        "label": "Donuk Oda",
        "family": "room",
        "storage_classes": ["FROZEN"],
        "temperature_c": "-18",
        "default_width_cm": 300,
        "default_depth_cm": 250,
        "default_height_cm": 240,
        "default_shelf_count": 1,
        "default_max_weight_kg": 500,
        "capacity_metric": "sqm_and_floor_area",
        "allowed_merch_groups": ["FOOD_FROZEN", "BAKERY_FROZEN"],
    },
    "PALLET_AREA": {
        "fixture_key": "PALLET_AREA",
        "label": "Palet Alanı",
        "family": "bulk",
        "storage_classes": ["BULK", "AMBIENT_HEAVY"],
        "default_width_cm": 120,
        "default_depth_cm": 100,
        "default_height_cm": 180,
        "default_shelf_count": 1,
        "default_max_weight_kg": 700,
        "allowed_merch_groups": ["BULK_AMBIENT", "HEAVY_AMBIENT"],
    },
    "DISPATCH_AREA": {
        "fixture_key": "DISPATCH_AREA",
        "label": "Dispatch Alanı",
        "family": "operational",
        "storage_classes": ["OPERATIONAL"],
        "planogram_eligible": False,
    },
    "RECEIVING_AREA": {
        "fixture_key": "RECEIVING_AREA",
        "label": "Mal Kabul Alanı",
        "family": "operational",
        "storage_classes": ["OPERATIONAL"],
        "planogram_eligible": False,
    },
    "STRUCTURAL_COLUMN": {
        "fixture_key": "STRUCTURAL_COLUMN",
        "label": "Kolon",
        "family": "structural",
        "storage_classes": ["STRUCTURAL"],
        "planogram_eligible": False,
    },
    "WALL": {
        "fixture_key": "WALL",
        "label": "Duvar",
        "family": "structural",
        "storage_classes": ["STRUCTURAL"],
        "planogram_eligible": False,
    },
}

# Common aliases from older patches / UI labels.
FIXTURE_ALIASES = {
    "steel_rack": "REGULAR_AMBIENT_RACK",
    "regular_shelf": "REGULAR_AMBIENT_RACK",
    "corridor": "REGULAR_AMBIENT_RACK",
    "new_gen_steel_rack": "NEW_GEN_STEEL_RACK",
    "hdr_heavy_rack": "HEAVY_BOTTOM_RACK",
    "martek_plus4": "MARTEK_CHILLED",
    "vertical_chiller": "MARTEK_CHILLED",
    "martek_frozen_minus18": "MARTEK_FROZEN",
    "freezer": "MARTEK_FROZEN",
    "ice_cream_chest_freezer_small": "ALGIDA_FREEZER",
    "ice_cream_chest_freezer_medium": "ALGIDA_FREEZER",
    "ice_cream_chest_freezer_large": "ALGIDA_FREEZER",
    "algida_freezer": "ALGIDA_FREEZER",
    "horizontal_fridge": "HORIZONTAL_FREEZER",
    "horizontal_freezer": "HORIZONTAL_FREEZER",
    "produce_shelf": "PRODUCE_AMBIENT_SHELF",
    "produce_ambient_shelf": "PRODUCE_AMBIENT_SHELF",
    "produce_chilled_shelf": "PRODUCE_CHILLED_SHELF",
    "chilled_room": "CHILLED_ROOM",
    "frozen_room": "FROZEN_ROOM",
    "pallet_area": "PALLET_AREA",
    "dispatch": "DISPATCH_AREA",
    "receiving": "RECEIVING_AREA",
    "column": "STRUCTURAL_COLUMN",
    "wall": "WALL",
}


def normalize_fixture_key(value: Any) -> str:
    raw = str(value or "REGULAR_AMBIENT_RACK").strip()
    if not raw:
        return "REGULAR_AMBIENT_RACK"
    key = raw.upper().replace(" ", "_").replace("+", "PLUS").replace("-", "MINUS")
    if key in FIXTURE_CATALOG:
        return key
    lower = raw.lower().strip()
    return FIXTURE_ALIASES.get(lower, FIXTURE_ALIASES.get(key.lower(), "REGULAR_AMBIENT_RACK"))


def get_fixture_spec(fixture_key: Any) -> Dict[str, Any]:
    k = normalize_fixture_key(fixture_key)
    return deepcopy(FIXTURE_CATALOG.get(k, FIXTURE_CATALOG["REGULAR_AMBIENT_RACK"]))


def list_fixture_catalog() -> List[Dict[str, Any]]:
    return [deepcopy(v) for v in FIXTURE_CATALOG.values()]


def storage_classes_for_fixture(fixture_key: Any) -> List[str]:
    return list(get_fixture_spec(fixture_key).get("storage_classes", ["AMBIENT"]))
