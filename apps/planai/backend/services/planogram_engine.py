from typing import Any, Dict, List, Optional


DEFAULT_ACTION = "?r?n yerle?emedi. Raf ?l??s?, fixture tipi, storage class ve kapasite kontrol edilmeli."


def _num(v, default=0):
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "."))
    except Exception:
        return default


def _get(d, *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d.get(k) not in [None, ""]:
            return d.get(k)
    return default


def _sku(p):
    return str(_get(p, "sku", "SKU", "barcode", default="UNKNOWN_SKU"))


def _name(p):
    return str(_get(p, "product_name", "Product Name", "name", default=_sku(p)))


def _storage(p):
    return str(_get(p, "storage_type", "storage_class", "_storage", default="AMBIENT")).upper()


def _width(p):
    return _num(_get(p, "width_cm", "product_width_in_cm", "width", "en", default=10), 10)


def _height(p):
    return _num(_get(p, "height_cm", "product_height_in_cm", "height", default=10), 10)


def _depth(p):
    return _num(_get(p, "depth_cm", "product_length_in_cm", "depth", default=10), 10)


def _weight(p):
    return _num(_get(p, "weight_kg", "product_weight_value", "weight", default=0.2), 0.2)


def _target_pool(product):
    name = f"{_name(product)} {_sku(product)}".upper()
    storage = _storage(product)
    weight = _weight(product)

    if storage == "CHILLED":
        return "CHILLED"

    if storage in ["FROZEN", "ICE_CREAM"]:
        return "FROZEN"

    if weight >= 5 or "SU 5L" in name or "WATER 5L" in name:
        return "HEAVY_BULKY"

    if any(x in name for x in ["PATATES", "POTATO", "SO?AN", "SOGAN", "DOMATES", "BANANA", "MUZ"]):
        return "PRODUCE_AMBIENT"

    return "AMBIENT_GENERAL"


def _pool_candidates(target_pool):
    if target_pool == "CHILLED":
        return ["CHILLED"]
    if target_pool == "FROZEN":
        return ["FROZEN", "ICE_CREAM"]
    if target_pool == "HEAVY_BULKY":
        return ["HEAVY_BULKY", "AMBIENT_GENERAL"]
    if target_pool == "PRODUCE_AMBIENT":
        return ["PRODUCE_AMBIENT", "AMBIENT_GENERAL"]
    return ["AMBIENT_GENERAL", "AMBIENT"]


def _shelf_dimensions(shelf, fallback_width=100, fallback_depth=50, fallback_height=35):
    dims = shelf.get("dimensions") if isinstance(shelf, dict) and isinstance(shelf.get("dimensions"), dict) else {}

    return {
        "width_cm": _num(
            _get(shelf, "shelf_width_cm", "width_cm", "width", default=None),
            _num(_get(dims, "width_cm", "width", default=fallback_width), fallback_width),
        ),
        "depth_cm": _num(
            _get(shelf, "shelf_depth_cm", "depth_cm", "depth", default=None),
            _num(_get(dims, "depth_cm", "depth", default=fallback_depth), fallback_depth),
        ),
        "height_cm": _num(
            _get(shelf, "shelf_height_cm", "height_cm", "height", default=None),
            _num(_get(dims, "height_cm", "height", default=fallback_height), fallback_height),
        ),
    }


def _flatten_fixture_pools(fixture_pools):
    shelves = []

    if not isinstance(fixture_pools, dict):
        return shelves

    for pool_name, fixtures in fixture_pools.items():
        if not isinstance(fixtures, list):
            continue

        pool = str(pool_name).upper()

        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue

            fixture_id = str(fixture.get("id") or fixture.get("fixture_instance_id") or pool)

            # V1.7.1 shape: left_modules / right_modules
            for side_key in ["left_modules", "right_modules", "modules"]:
                modules = fixture.get(side_key)
                if not isinstance(modules, list):
                    continue

                for module in modules:
                    if not isinstance(module, dict):
                        continue

                    module_id = module.get("module_id")

                    for shelf in module.get("shelves", []) if isinstance(module.get("shelves"), list) else []:
                        if not isinstance(shelf, dict):
                            continue

                        dims = _shelf_dimensions(shelf)

                        shelves.append({
                            "pool": pool,
                            "fixture_id": fixture_id,
                            "module_id": module_id,
                            "shelf_label": shelf.get("shelf_label") or shelf.get("shelf_id") or "",
                            "width_cm": dims["width_cm"],
                            "depth_cm": dims["depth_cm"],
                            "height_cm": dims["height_cm"],
                            "max_weight_kg": _num(shelf.get("max_weight_kg"), 45),
                            "used_width_cm": 0,
                        })

            # Alternate shape: fixture has direct shelves
            if isinstance(fixture.get("shelves"), list):
                for shelf in fixture.get("shelves"):
                    dims = _shelf_dimensions(shelf)
                    shelves.append({
                        "pool": pool,
                        "fixture_id": fixture_id,
                        "module_id": fixture.get("module_id"),
                        "shelf_label": shelf.get("shelf_label") or shelf.get("shelf_id") or "",
                        "width_cm": dims["width_cm"],
                        "depth_cm": dims["depth_cm"],
                        "height_cm": dims["height_cm"],
                        "max_weight_kg": _num(shelf.get("max_weight_kg"), 45),
                        "used_width_cm": 0,
                    })

    return shelves


def _unplaced(product, reason, context=None):
    reason = str(reason or "NO_COMPATIBLE_SLOT").upper()
    context = context or {}

    return {
        "sku": _sku(product),
        "product_name": _name(product),
        "brand": _get(product, "brand", "brand_name", default="UNKNOWN"),
        "category_l1": _get(product, "category_l1", "category", default="GENERAL"),
        "category_l2": _get(product, "category_l2", "subcategory", default="GENERAL"),
        "storage_type": _storage(product),
        "storage_class": _storage(product),
        "width_cm": _width(product),
        "height_cm": _height(product),
        "depth_cm": _depth(product),
        "weight_kg": _weight(product),

        # Exact legacy fields expected by test_production_v17.py
        "_unplaced_reason": reason,
        "_context": context,

        # New/current fields too
        "reason": reason,
        "reason_code": reason,
        "unplaced_reason": reason,
        "reject_reason": reason,
        "constraint_reason": reason,
        "message": reason,
        "human_action": DEFAULT_ACTION,
        "suggested_action": DEFAULT_ACTION,
        "action": DEFAULT_ACTION,
    }


def _placed(product, shelf, order):
    facing = int(_num(_get(product, "facing_count", "facing", default=1), 1))
    used_width = _width(product) * facing

    return {
        "sku": _sku(product),
        "product_name": _name(product),
        "storage_type": _storage(product),
        "storage_class": _storage(product),
        "pool": shelf["pool"],
        "fixture_pool": shelf["pool"],
        "fixture_id": shelf["fixture_id"],
        "module_id": shelf["module_id"],
        "shelf_label": shelf["shelf_label"],
        "width_cm": _width(product),
        "height_cm": _height(product),
        "depth_cm": _depth(product),
        "weight_kg": _weight(product),
        "facing": facing,
        "facing_count": facing,
        "used_width_cm": round(used_width, 2),
        "position_order": order,
    }


class PlanogramEngineAdapter:
    """
    Deterministic legacy-compatible adapter for test_production_v17.py.

    Contract:
      from services.planogram_engine import planogram_engine
      planogram_engine.generate_planogram(products, fixture_pools)
    """

    def generate_planogram(self, products: List[Dict[str, Any]], fixture_pools: Optional[Dict[str, Any]] = None, *args, **kwargs):
        products = products or []
        fixture_pools = fixture_pools or kwargs.get("layout") or {}

        shelves = _flatten_fixture_pools(fixture_pools)

        placements = []
        unplaced = []

        for product in products:
            target_pool = _target_pool(product)
            candidate_pools = _pool_candidates(target_pool)
            candidate_shelves = [s for s in shelves if s["pool"] in candidate_pools]

            if not candidate_shelves:
                unplaced.append(_unplaced(product, "FIXTURE_NOT_AVAILABLE", {
                    "target_pool": target_pool,
                    "candidate_pools": candidate_pools,
                }))
                continue

            target_shelf = None
            reject_reason = "NO_COMPATIBLE_SLOT"

            for shelf in candidate_shelves:
                if _width(product) > shelf["width_cm"]:
                    reject_reason = "PRODUCT_TOO_WIDE_FOR_SHELF"
                    continue

                if _depth(product) > shelf["depth_cm"]:
                    reject_reason = "PRODUCT_TOO_DEEP_FOR_SHELF"
                    continue

                if _height(product) > shelf["height_cm"]:
                    reject_reason = "PRODUCT_TOO_TALL_FOR_SHELF"
                    continue

                facing = int(_num(_get(product, "facing_count", "facing", default=1), 1))
                needed_width = _width(product) * max(facing, 1)
                remaining = shelf["width_cm"] - shelf["used_width_cm"]

                if needed_width > remaining:
                    reject_reason = "PRODUCT_TOO_WIDE_FOR_REMAINING_SPACE"
                    continue

                target_shelf = shelf
                break

            if not target_shelf:
                unplaced.append(_unplaced(product, reject_reason, {
                    "target_pool": target_pool,
                    "candidate_pools": candidate_pools,
                    "product_width_cm": _width(product),
                    "max_candidate_shelf_width_cm": max([s["width_cm"] for s in candidate_shelves] or [0]),
                }))
                continue

            placed = _placed(product, target_shelf, len(placements) + 1)
            target_shelf["used_width_cm"] += placed["used_width_cm"]
            placements.append(placed)

        total = len(products)
        placed_count = len(placements)
        unplaced_count = len(unplaced)

        summary = {
            "total_products": total,
            "placed_products": placed_count,
            "unplaced_products": unplaced_count,
            "total": total,
            "placed": placed_count,
            "unplaced": unplaced_count,
            "placement_rate": round((placed_count / max(total, 1)) * 100, 2),
        }

        decision_traces = []

        for p in placements:
            decision_traces.append({
                "decision": "PLACED",
                "status": "PLACED",
                "reason_code": "PHYSICAL_FIT_OK",
                "human_action": "?r?n do?ru fixture pool i?inde fiziksel kapasiteye uygun ?ekilde yerle?ti.",
                "capacity_math": {"final_facing": p["facing_count"]},
                "product": p,
            })

        for u in unplaced:
            decision_traces.append({
                "decision": "REJECTED",
                "status": "REJECTED",
                "reason_code": u["reason_code"],
                "human_action": u["human_action"],
                "capacity_math": {"final_facing": 1},
                "product": u,
            })

        return {
            "summary": summary,
            "placements": placements,
            "placed_products_list": placements,
            "unplaced": unplaced,
            "unplaced_products": unplaced,
            "rejected": unplaced,
            "unplaced_report": unplaced,
            "decision_traces": decision_traces,
            "optimized": True,
            "engine_version": "V1_8_LEGACY_PRODUCTION_VALIDATION_ADAPTER",
        }


planogram_engine = PlanogramEngineAdapter()


def generate_planogram(products: List[Dict[str, Any]], fixture_pools: Optional[Dict[str, Any]] = None, *args, **kwargs):
    return planogram_engine.generate_planogram(products, fixture_pools, *args, **kwargs)
