"""Build physical placement slots from Store DNA."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .fixture_catalog import get_fixture_spec, normalize_fixture_key


def _num(v: Any, d: float = 0) -> float:
    try:
        if v is None or v == "":
            return d
        return float(str(v).replace(",", "."))
    except Exception:
        return d


def _int(v: Any, d: int = 0) -> int:
    try:
        return int(float(str(v).replace(",", ".")))
    except Exception:
        return d


def _letters(idx: int) -> str:
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if idx < len(alpha):
        return alpha[idx]
    return f"A{idx + 1}"


def make_shelf_slot(*, store_code: str, fixture_instance_id: str, fixture_key: str, aisle_id: str, module_id: Any, side: str, shelf_no: int, shelf: Dict[str, Any], module: Dict[str, Any], source: str = "store_dna") -> Dict[str, Any]:
    spec = get_fixture_spec(fixture_key)
    storage_classes = list(module.get("storage_classes") or shelf.get("storage_classes") or spec.get("storage_classes") or [shelf.get("allowed_storage_type") or "AMBIENT"])
    dims = shelf.get("dimensions") or {}
    mdims = module.get("dimensions") or {}
    width = _num(shelf.get("shelf_width_cm") or dims.get("width_cm") or mdims.get("width") or module.get("module_width_cm"), spec.get("default_width_cm", 100))
    depth = _num(shelf.get("shelf_depth_cm") or dims.get("depth_cm") or mdims.get("depth") or module.get("module_depth_cm"), spec.get("default_depth_cm", 50))
    height = _num(shelf.get("shelf_height_cm") or dims.get("height_cm"), max(25, _num(mdims.get("height") or module.get("module_height_cm"), spec.get("default_height_cm", 210)) / max(1, len(module.get("shelves") or []))))
    max_weight = _num(shelf.get("max_weight_kg"), spec.get("default_max_weight_kg", 45))
    used_width = _num(shelf.get("used_width_cm") or shelf.get("used"), 0)
    return {
        "slot_id": f"{store_code}:{fixture_instance_id}:M{module_id}:S{shelf_no}",
        "store_code": store_code,
        "fixture_instance_id": fixture_instance_id,
        "fixture_key": fixture_key,
        "fixture_label": spec.get("label"),
        "fixture_family": spec.get("family"),
        "aisle_id": aisle_id,
        "module_id": module_id,
        "side": side or module.get("side") or "L",
        "shelf_no": shelf_no,
        "shelf_width_cm": width,
        "shelf_depth_cm": depth,
        "shelf_height_cm": height,
        "max_weight_kg": max_weight,
        "used_width_cm": used_width,
        "remaining_width_cm": max(0, width - used_width),
        "used_weight_kg": _num(shelf.get("used_weight_kg"), 0),
        "storage_classes": storage_classes,
        "primary_storage_class": storage_classes[0] if storage_classes else "AMBIENT",
        "brand_lock": spec.get("brand_lock") or module.get("brand_lock"),
        "allowed_merch_groups": spec.get("allowed_merch_groups", []),
        "hard_rules": spec.get("hard_rules", []),
        "zone_type": shelf.get("zone_type") or "mid",
        "products": deepcopy(shelf.get("products") or []),
        "source": source,
    }


def _module_to_slots(store_code: str, aisle_id: str, module: Dict[str, Any], fixture_instance_id: str, fixture_key: str, source: str) -> List[Dict[str, Any]]:
    spec = get_fixture_spec(fixture_key)
    shelf_count = _int(module.get("shelf_count"), spec.get("default_shelf_count", 6))
    shelves = module.get("shelves") or []
    if not shelves:
        shelves = [
            {
                "shelf_no": i + 1,
                "shelf_width_cm": _num(module.get("module_width_cm"), spec.get("default_width_cm", 100)),
                "shelf_depth_cm": _num(module.get("module_depth_cm"), spec.get("default_depth_cm", 50)),
                "shelf_height_cm": max(25, _num(module.get("module_height_cm"), spec.get("default_height_cm", 210)) / max(1, shelf_count)),
                "max_weight_kg": spec.get("default_max_weight_kg", 45),
                "zone_type": "bottom" if i == 0 else "top" if i == shelf_count - 1 else "eye" if i in [shelf_count // 2, max(0, shelf_count // 2 - 1)] else "mid",
                "products": [],
            }
            for i in range(max(1, shelf_count))
        ]
    slots = []
    for i, shelf in enumerate(shelves):
        slots.append(make_shelf_slot(
            store_code=store_code,
            fixture_instance_id=fixture_instance_id,
            fixture_key=fixture_key,
            aisle_id=aisle_id,
            module_id=module.get("module_id") or module.get("id") or 1,
            side=module.get("side") or "L",
            shelf_no=_int(shelf.get("shelf_no"), i + 1),
            shelf=shelf,
            module={**module, "storage_classes": spec.get("storage_classes")},
            source=source,
        ))
    return slots


def build_fixture_slots(store_dna: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a flat physical slot list. Never truncates fixture/module count."""
    store_code = str(store_dna.get("store_code") or "AUTO").upper()
    slots: List[Dict[str, Any]] = []

    # Aisle/module model.
    for aisle_idx, aisle in enumerate(store_dna.get("aisles") or []):
        aisle_id = str(aisle.get("aisle_id") or _letters(aisle_idx))
        modules = list(aisle.get("modules") or [])
        # Support left_modules/right_modules arrays if present.
        for side_key, side_label in [("left_modules", "L"), ("right_modules", "R")]:
            side_modules = aisle.get(side_key)
            if isinstance(side_modules, list):
                for m in side_modules:
                    m = {**m, "side": m.get("side") or side_label}
                    modules.append(m)
        for module_idx, module in enumerate(modules):
            fixture_key = normalize_fixture_key(module.get("fixture_key") or module.get("fixture_type") or module.get("module_type") or aisle.get("fixture_type") or "REGULAR_AMBIENT_RACK")
            fixture_instance_id = str(module.get("fixture_instance_id") or f"{aisle_id}-{module.get('side','L')}-{module.get('module_id') or module_idx+1}")
            slots.extend(_module_to_slots(store_code, aisle_id, module, fixture_instance_id, fixture_key, "aisle_module"))

    # Instance model in Store DNA / layout_objects. Each instance becomes module-like slots.
    instances = list(store_dna.get("fixture_instances") or [])
    # V1.7.5: support wizard/raw Store DNA fixture inventory directly.
    # This avoids losing Algida/Martek/produce counts when the wizard stores
    # them as fixture_inventory instead of fully expanded fixture_instances.
    instances.extend(list(store_dna.get("fixture_inventory") or []))
    for obj in store_dna.get("layout_objects") or []:
        if obj.get("planogram_eligible") or obj.get("type") in {"corridor", "algida_freezer", "ice_cream_chest_freezer_medium", "martek_plus4", "martek_frozen_minus18", "horizontal_fridge", "horizontal_freezer", "produce_shelf", "steel_rack", "new_gen_steel_rack", "pallet_area", "chilled_room", "frozen_room"}:
            instances.append(obj)
    for idx, inst in enumerate(instances):
        # Legacy Store DNA layout object may itself contain left/right modules.
        nested_modules = []
        for side_key, side_label in [("left_modules", "L"), ("right_modules", "R")]:
            if isinstance(inst.get(side_key), list):
                for m in inst.get(side_key) or []:
                    nested_modules.append({**m, "side": m.get("side") or side_label})
        if nested_modules:
            aisle_id = str(inst.get("id") or inst.get("aisle_id") or f"OBJ-{idx+1}")
            for m_idx, module in enumerate(nested_modules):
                fixture_key = normalize_fixture_key(module.get("fixture_key") or module.get("fixture_type") or module.get("module_type") or inst.get("type"))
                fixture_instance_id = str(module.get("fixture_instance_id") or module.get("module_id") or f"{aisle_id}-{m_idx+1}")
                slots.extend(_module_to_slots(store_code, aisle_id, module, fixture_instance_id, fixture_key, "layout_object_modules"))
            continue

        fixture_key = normalize_fixture_key(inst.get("fixture_key") or inst.get("fixture_type") or inst.get("type"))
        spec = get_fixture_spec(fixture_key)
        if inst.get("planogram_eligible") is False or spec.get("planogram_eligible") is False:
            continue
        count = max(1, _int(inst.get("count") or inst.get("quantity"), 1))
        for c in range(count):
            instance_id = str(inst.get("fixture_instance_id") or inst.get("id") or f"FI-{idx+1}-{c+1}")
            module = {
                "module_id": inst.get("module_id") or c + 1,
                "side": inst.get("side") or "L",
                "module_width_cm": _num(inst.get("width_cm"), spec.get("default_width_cm", 100)),
                "module_depth_cm": _num(inst.get("depth_cm"), spec.get("default_depth_cm", 50)),
                "module_height_cm": _num(inst.get("height_cm"), spec.get("default_height_cm", 210)),
                "shelf_count": _int(inst.get("shelf_count"), spec.get("default_shelf_count", 1)),
                "storage_classes": spec.get("storage_classes"),
            }
            aisle_id = str(inst.get("aisle_id") or inst.get("zone") or spec.get("fixture_key"))
            slots.extend(_module_to_slots(store_code, aisle_id, module, instance_id, fixture_key, "fixture_instance"))
    return slots


def build_fixture_pools(store_dna: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    slots = build_fixture_slots(store_dna)
    pools: Dict[str, List[Dict[str, Any]]] = {}
    for slot in slots:
        for storage_class in slot.get("storage_classes") or [slot.get("primary_storage_class", "AMBIENT")]:
            pools.setdefault(storage_class, []).append(deepcopy(slot))
    return pools


def summarize_pools(pools: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {
        k: {
            "slot_count": len(v),
            "total_width_cm": round(sum(_num(s.get("shelf_width_cm"), 0) for s in v), 1),
            "remaining_width_cm": round(sum(_num(s.get("remaining_width_cm"), 0) for s in v), 1),
        }
        for k, v in sorted(pools.items())
    }
