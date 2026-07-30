
from __future__ import annotations

from copy import deepcopy
from math import ceil
from typing import Any, Callable, Dict, List, Tuple

TR_MAP = str.maketrans({"ı":"i","İ":"i","ğ":"g","Ğ":"g","ü":"u","Ü":"u","ş":"s","Ş":"s","ö":"o","Ö":"o","ç":"c","Ç":"c"})

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()

def norm(v: Any) -> str:
    return _s(v).translate(TR_MAP).lower().strip()

def key_text(*values: Any) -> str:
    return " ".join(norm(v) for v in values if _s(v))

def num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).replace(',', '.'))
    except Exception:
        return default

def infer_storage(obj: Dict[str, Any], parent: Dict[str, Any] | None = None) -> str:
    parent = parent or {}
    text = key_text(
        obj.get('allowed_storage_type'), obj.get('storage_type'), obj.get('module_type'), obj.get('fixture_type'),
        obj.get('type'), obj.get('label'), obj.get('name'), obj.get('temperature'), obj.get('zone_type'),
        parent.get('aisle_id'), parent.get('zone_type'), parent.get('fixture_type'), parent.get('label'), parent.get('name')
    )
    if any(x in text for x in ['-18', 'frozen', 'freezer', 'donuk', 'algida']):
        return 'FROZEN'
    if any(x in text for x in ['+4', 'chilled', 'fridge', 'cooler', 'cold', 'soguk', 'soğuk']):
        return 'CHILLED'
    if 'pallet' in text or 'kasa' in text:
        return 'PALLET'
    return 'AMBIENT'

def module_dimensions(module: Dict[str, Any], storage: str) -> Tuple[float, float, float, float, int]:
    width = num(module.get('module_width_cm') or module.get('width_cm') or module.get('width') or module.get('w'), 100)
    depth = num(module.get('module_depth_cm') or module.get('depth_cm') or module.get('depth') or module.get('d'), 50)
    height = num(module.get('module_height_cm') or module.get('height_cm') or module.get('height') or module.get('h'), 210)
    if width <= 0: width = 100
    if depth <= 0: depth = 50
    if height <= 0: height = 210

    if storage == 'FROZEN':
        shelf_count = int(num(module.get('shelf_count'), 5) or 5)
        shelf_height = max(28, min(45, height / max(shelf_count, 1) - 4))
        max_weight = 70
    elif storage == 'CHILLED':
        shelf_count = int(num(module.get('shelf_count'), 6) or 6)
        shelf_height = max(26, min(40, height / max(shelf_count, 1) - 4))
        max_weight = 60
    else:
        shelf_count = int(num(module.get('shelf_count'), 5) or 5)
        shelf_height = max(28, min(42, height / max(shelf_count, 1) - 4))
        max_weight = 45
    return width, shelf_height, depth, max_weight, max(1, shelf_count)

def ensure_module_shelves(module: Dict[str, Any], aisle: Dict[str, Any], make_shelves: Callable) -> None:
    storage = infer_storage(module, aisle)
    module['allowed_storage_type'] = storage
    module.setdefault('module_type', {'AMBIENT':'regular_shelf','CHILLED':'fridge','FROZEN':'freezer','PALLET':'pallet'}.get(storage, 'regular_shelf'))
    module.setdefault('is_product_fixture', True)
    width, shelf_height, depth, max_weight, shelf_count = module_dimensions(module, storage)
    module['module_width_cm'] = width
    module['module_depth_cm'] = depth
    module['module_height_cm'] = num(module.get('module_height_cm') or module.get('height_cm'), 210)

    shelves = module.get('shelves') or []
    if not shelves:
        module['shelves'] = make_shelves(shelf_count, storage, width, shelf_height, depth, max_weight)
        return

    for idx, shelf in enumerate(shelves):
        shelf.setdefault('shelf_no', idx + 1)
        shelf['allowed_storage_type'] = shelf.get('allowed_storage_type') or storage
        shelf['shelf_width_cm'] = num(shelf.get('shelf_width_cm') or shelf.get('width_cm'), width)
        shelf['shelf_height_cm'] = num(shelf.get('shelf_height_cm') or shelf.get('height_cm'), shelf_height)
        shelf['shelf_depth_cm'] = num(shelf.get('shelf_depth_cm') or shelf.get('depth_cm'), depth)
        shelf['max_weight_kg'] = num(shelf.get('max_weight_kg'), max_weight)
        shelf.setdefault('products', [])
        shelf.setdefault('used_width_cm', 0)
        shelf.setdefault('used_weight_kg', 0)
        shelf.setdefault('used', 0)

def add_capacity_aisle(plan: Dict[str, Any], storage: str, module_count: int, make_shelves: Callable, label: str) -> None:
    if module_count <= 0:
        return
    module_type = {'AMBIENT':'regular_shelf','CHILLED':'fridge','FROZEN':'freezer','PALLET':'pallet'}.get(storage, 'regular_shelf')
    width = 120 if storage == 'AMBIENT' else 150
    depth = 50 if storage == 'AMBIENT' else 60
    height = 210
    shelf_count = 5 if storage == 'FROZEN' else 6
    shelf_height = 36 if storage == 'FROZEN' else 32
    max_weight = 70 if storage == 'FROZEN' else 60 if storage == 'CHILLED' else 45
    next_row = max([int(num(a.get('row'), 0)) for a in plan.get('aisles', [])] or [0]) + 1
    aisle = {
        'aisle_id': label,
        'row': next_row,
        'position': 1,
        'direction': 'AI_CAPACITY',
        'distance_to_dispatch': 99 + next_row,
        'aisle_type': 'ai_capacity',
        'zone_type': f'{storage}_ZONE',
        'fixture_type': f'ai_{storage.lower()}_fixture_capacity',
        'ai_generated_capacity': True,
        'modules': []
    }
    for i in range(module_count):
        aisle['modules'].append({
            'module_id': i + 1,
            'side': 'L' if i % 2 == 0 else 'R',
            'module_type': module_type,
            'fixture_type': module_type,
            'allowed_storage_type': storage,
            'module_width_cm': width,
            'module_depth_cm': depth,
            'module_height_cm': height,
            'is_product_fixture': True,
            'ai_generated_capacity': True,
            'shelves': make_shelves(shelf_count, storage, width, shelf_height, depth, max_weight),
        })
    plan.setdefault('aisles', []).append(aisle)

def storage_capacity(plan: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    out = {s: {'shelves':0, 'modules':0, 'width_cm':0} for s in ['AMBIENT','CHILLED','FROZEN','PALLET']}
    for aisle in plan.get('aisles', []):
        for module in aisle.get('modules', []):
            st = infer_storage(module, aisle)
            out.setdefault(st, {'shelves':0, 'modules':0, 'width_cm':0})
            out[st]['modules'] += 1
            for shelf in module.get('shelves', []) or []:
                sst = shelf.get('allowed_storage_type') or st
                out.setdefault(sst, {'shelves':0, 'modules':0, 'width_cm':0})
                out[sst]['shelves'] += 1
                out[sst]['width_cm'] += num(shelf.get('shelf_width_cm'), 100)
    return out

def normalize_fixture_layout(plan: Dict[str, Any], make_shelves: Callable) -> Dict[str, Any]:
    plan = deepcopy(plan or {})
    plan.setdefault('aisles', [])

    # Some frontend layout payloads keep objects outside aisles. Convert product fixtures to modules.
    loose_objects: List[Dict[str, Any]] = []
    for k in ['objects', 'layout_objects', 'fixtures', 'fixture_objects', 'rooms']:
        v = plan.get(k)
        if isinstance(v, list):
            loose_objects.extend([x for x in v if isinstance(x, dict)])

    if loose_objects:
        aisle = {
            'aisle_id': 'LAYOUT_OBJECTS', 'row': 98, 'position': 1,
            'direction': 'OBJECTS', 'distance_to_dispatch': 98,
            'aisle_type': 'layout_objects', 'zone_type': 'MIXED_ZONE', 'modules': []
        }
        mid = 1
        for obj in loose_objects:
            st = infer_storage(obj)
            text = key_text(obj.get('type'), obj.get('label'), obj.get('name'))
            # Rooms are zones; create internal rack capacity only if they are cold/frozen.
            if any(x in text for x in ['room','oda','cold','chilled','frozen','donuk','soguk','soğuk','algida','dolap','shelf','raf','gondol']):
                module = dict(obj)
                module['module_id'] = module.get('module_id') or mid
                module['allowed_storage_type'] = st
                aisle['modules'].append(module)
                mid += 1
        if aisle['modules']:
            plan['aisles'].append(aisle)

    for aisle in plan.get('aisles', []):
        aisle.setdefault('modules', [])
        for module in aisle.get('modules', []):
            ensure_module_shelves(module, aisle, make_shelves)

    return plan

def product_storage_mix(products: List[Dict[str, Any]]) -> Dict[str, int]:
    try:
        from storage_normalizer import normalize_storage_type
    except Exception:
        normalize_storage_type = None
    mix = {'AMBIENT':0, 'CHILLED':0, 'FROZEN':0, 'PALLET':0}
    for p in products or []:
        if normalize_storage_type:
            st = normalize_storage_type(p)
        else:
            raw = key_text(p.get('storage_type'), p.get('product_name'), p.get('category_l1'), p.get('category_l2'))
            st = 'FROZEN' if any(x in raw for x in ['frozen','donuk','-18','algida']) else 'CHILLED' if any(x in raw for x in ['chilled','+4','soguk','soğuk']) else 'AMBIENT'
        mix[st] = mix.get(st, 0) + 1
    return mix

def expand_layout_for_product_mix(layout: Dict[str, Any], products: List[Dict[str, Any]], make_shelves: Callable) -> Dict[str, Any]:
    plan = normalize_fixture_layout(layout, make_shelves)
    mix = product_storage_mix(products)
    cap = storage_capacity(plan)

    # Approximate SKU capacity per shelf. This is conservative enough to avoid 2K chilled SKUs dying with "no matching fixture".
    sku_per_shelf = {'AMBIENT': 8, 'CHILLED': 7, 'FROZEN': 6, 'PALLET': 4}
    shelves_per_module = {'AMBIENT': 5, 'CHILLED': 6, 'FROZEN': 5, 'PALLET': 1}

    for st in ['CHILLED', 'FROZEN']:
        needed_shelves = int(ceil((mix.get(st, 0) or 0) / sku_per_shelf[st]))
        current_shelves = int(cap.get(st, {}).get('shelves', 0))
        deficit = max(0, needed_shelves - current_shelves)
        if current_shelves == 0 or deficit > 0:
            # Cap auto expansion so UI is still navigable, but enough to stop cold/frozen being decorative.
            add_modules = min(80, int(ceil(deficit / shelves_per_module[st])))
            add_capacity_aisle(plan, st, add_modules, make_shelves, f'AI-{st}-CAPACITY')

    # If frontend sends too few/empty ambient modules, add fallback ambient shelves. Do not override real store layout if it already has capacity.
    cap = storage_capacity(plan)
    if cap.get('AMBIENT', {}).get('shelves', 0) < 60 and mix.get('AMBIENT', 0) > 0:
        needed_shelves = int(ceil(min(mix['AMBIENT'], 1200) / sku_per_shelf['AMBIENT']))
        deficit = max(0, needed_shelves - int(cap.get('AMBIENT', {}).get('shelves', 0)))
        add_modules = min(60, int(ceil(deficit / shelves_per_module['AMBIENT'])))
        add_capacity_aisle(plan, 'AMBIENT', add_modules, make_shelves, 'AI-AMBIENT-CAPACITY')

    plan['ai_fixture_capacity_summary'] = {
        'product_mix': mix,
        'capacity_after': storage_capacity(plan),
        'note': 'Cold/frozen rooms and loose fixture objects were converted into product-accepting shelf capacity. Placement now uses all modules, not just first visible shelves.'
    }
    return plan
