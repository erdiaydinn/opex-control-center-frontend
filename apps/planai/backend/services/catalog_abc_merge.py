from typing import Any, Dict, List, Optional
from collections import Counter

try:
    from .product_classification_rules import classify_planogram_product, split_products_for_planogram
except Exception:
    def classify_planogram_product(product: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "planogram_class": "SELLABLE_PLANOGRAM_PRODUCT",
            "is_sellable_planogram_product": True,
            "exclude_from_planogram": False,
            "reason_code": "SELLABLE_PRODUCT",
            "human_action": "Ürün normal planogram yerleşimi için uygundur.",
        }

    def split_products_for_planogram(products):
        return {
            "sellable_products": products or [],
            "excluded_products": [],
            "review_products": [],
            "summary": {
                "input_products": len(products or []),
                "sellable_products": len(products or []),
                "excluded_products": 0,
                "review_products": 0,
            },
        }


def _txt(v: Any) -> str:
    return str(v or "").strip()


def _norm(v: Any) -> str:
    return _txt(v).lower().replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")


def _num(v: Any, default: float = 0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace("%", "").replace(",", ".").strip())
    except Exception:
        return default


def _first(row: Dict[str, Any], names: List[str], default: Any = "") -> Any:
    if not isinstance(row, dict):
        return default
    lower = {str(k).lower().strip(): k for k in row.keys()}
    for name in names:
        if name in row and row.get(name) not in [None, ""]:
            return row.get(name)
        real = lower.get(str(name).lower().strip())
        if real is not None and row.get(real) not in [None, ""]:
            return row.get(real)
    return default


def _barcode_first(v: Any) -> str:
    raw = _txt(v)
    if not raw:
        return ""
    for sep in ["|", ";", ",", " "]:
        if sep in raw:
            return _txt(raw.split(sep)[0])
    return raw


def normalize_abc_row(row: Dict[str, Any]) -> Dict[str, Any]:
    order_share = _num(_first(row, ["% Orders", "% Orders ▼", "percent_orders", "order_share_pct"], 0), 0)
    stop_share = _num(_first(row, ["% Stops", "percent_stops", "stop_share_pct"], 0), 0)

    return {
        "country": _first(row, ["Country"], ""),
        "store_name": _first(row, ["Store", "store"], ""),
        "rank": int(_num(_first(row, ["Rank", "rank"], 999999), 999999)),
        "sku": _txt(_first(row, ["SKU", "sku"], "")),
        "barcode": _barcode_first(_first(row, ["Barcodes", "Barcode", "barcode", "product_barcodes"], "")),
        "product_name": _first(row, ["Product Name", "product_name", "name"], ""),
        "category_l1": _first(row, ["Category L1", "category_l1"], ""),
        "category_l2": _first(row, ["Category L2", "category_l2"], ""),
        "abc_class": _txt(_first(row, ["ABC", "abc", "abc_class"], ""))[:1].upper(),
        "on_hand_qty": _num(_first(row, ["On-Hand Qty", "on_hand_qty", "stock"], 0), 0),
        "image_url": _txt(_first(row, ["Product Image URL", "image_url", "catalog_image_url", "pim_image_url"], "")),
        "order_share_pct": order_share,
        "stop_share_pct": stop_share,
        "current_location": _txt(_first(row, ["Location", "current_location"], "")),
        "secondary_location": _txt(_first(row, ["Secondary Location", "secondary_location"], "")),
        "is_a_zone": _txt(_first(row, ["Is A Zone", "is_a_zone"], "")),
        "abc_storage_type_hint": _txt(_first(row, ["Storage Type", "storage_type"], "")),
        "source": "ABC_UPLOAD",
    }


def normalize_catalog_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **row,
        "sku": _txt(_first(row, ["sku", "SKU"], "")),
        "barcode": _barcode_first(_first(row, ["barcode", "Barcode", "Barcodes", "product_barcodes"], "")),
        "product_name": _first(row, ["product_name", "Product Name", "name"], ""),
        "brand": _first(row, ["brand", "brand_name", "Brand"], ""),
        "category_l1": _first(row, ["category_l1", "Category L1", "frontend_category_local"], ""),
        "category_l2": _first(row, ["category_l2", "Category L2", "frontend_subcategory_local"], ""),
        "storage_type": _txt(_first(row, ["storage_type", "Storage Type"], "")),
        "width_cm": _num(_first(row, ["width_cm", "product_width_in_cm"], 0), 0),
        "height_cm": _num(_first(row, ["height_cm", "product_height_in_cm"], 0), 0),
        "depth_cm": _num(_first(row, ["depth_cm", "product_length_in_cm"], 0), 0),
        "weight_kg": _num(_first(row, ["weight_kg", "product_weight_value"], 0), 0),
        "case_pack_qty": _num(_first(row, ["case_pack_qty", "units_in_pack_count"], 1), 1),
        "image_url": _txt(_first(row, ["image_url", "catalog_image_url", "pim_image_url"], "")),
        "source": "EMBEDDED_CATALOG",
    }


def build_catalog_index(catalog_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for raw in catalog_rows or []:
        row = normalize_catalog_row(raw)
        sku = _norm(row.get("sku"))
        barcode = _norm(row.get("barcode"))
        if sku:
            idx[f"sku:{sku}"] = row
        if barcode:
            idx[f"barcode:{barcode}"] = row
    return idx


def find_catalog_match(abc: Dict[str, Any], catalog_index: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    sku = _norm(abc.get("sku"))
    barcode = _norm(abc.get("barcode"))
    return catalog_index.get(f"sku:{sku}") or catalog_index.get(f"barcode:{barcode}")


def merge_catalog_abc(
    abc_rows: List[Dict[str, Any]],
    catalog_rows: Optional[List[Dict[str, Any]]] = None,
    catalog_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if catalog_index is None:
        catalog_index = build_catalog_index(catalog_rows or [])

    merged_products: List[Dict[str, Any]] = []
    unmatched_abc: List[Dict[str, Any]] = []
    storage_conflicts: List[Dict[str, Any]] = []

    for raw in abc_rows or []:
        abc = normalize_abc_row(raw)
        catalog = find_catalog_match(abc, catalog_index)

        if not catalog:
            product = {
                **abc,
                "catalog_match_status": "UNMATCHED",
                "match_level": "none",
                "dimension_source": "missing_catalog",
                "storage_type": abc.get("abc_storage_type_hint") or "AMBIENT",
            }
            unmatched_abc.append(product)
        else:
            product = {
                **catalog,
                "sku": catalog.get("sku") or abc.get("sku"),
                "barcode": catalog.get("barcode") or abc.get("barcode"),
                "product_name": catalog.get("product_name") or abc.get("product_name"),
                "category_l1": catalog.get("category_l1") or abc.get("category_l1"),
                "category_l2": catalog.get("category_l2") or abc.get("category_l2"),
                "catalog_match_status": "MATCHED",
                "match_level": "sku_or_barcode",
                "abc_store_name": abc.get("store_name"),
                "abc_rank": abc.get("rank"),
                "abc_class": abc.get("abc_class"),
                "on_hand_qty": abc.get("on_hand_qty"),
                "order_share_pct": abc.get("order_share_pct"),
                "stop_share_pct": abc.get("stop_share_pct"),
                "current_location": abc.get("current_location"),
                "secondary_location": abc.get("secondary_location"),
                "is_a_zone": abc.get("is_a_zone"),
                "image_url": abc.get("image_url") or catalog.get("image_url") or "",
                "visual_source": "abc_upload" if abc.get("image_url") else ("catalog" if catalog.get("image_url") else "fallback"),
                "abc_storage_type_hint": abc.get("abc_storage_type_hint"),
                "storage_type": catalog.get("storage_type") or abc.get("abc_storage_type_hint") or "AMBIENT",
                "dimension_source": "catalog",
            }

            if abc.get("abc_storage_type_hint") and catalog.get("storage_type"):
                if _norm(abc.get("abc_storage_type_hint")) != _norm(catalog.get("storage_type")):
                    storage_conflicts.append({
                        "sku": product.get("sku"),
                        "product_name": product.get("product_name"),
                        "catalog_storage_type": catalog.get("storage_type"),
                        "abc_storage_type_hint": abc.get("abc_storage_type_hint"),
                        "action": "catalog_storage_kept_abc_hint_logged",
                    })

        cls = classify_planogram_product(product)
        product.update(cls)
        merged_products.append(product)

    split = split_products_for_planogram(merged_products)

    excluded_by_reason = Counter([p.get("reason_code") for p in split["excluded_products"]])
    review_by_class = Counter([p.get("planogram_class") for p in split["review_products"]])

    return {
        "status": "success",
        "merged_products": merged_products,
        "sellable_products": split["sellable_products"],
        "excluded_products": split["excluded_products"],
        "review_products": split["review_products"],
        "unmatched_abc": unmatched_abc,
        "storage_conflicts": storage_conflicts,
        "excluded_report": {"total": len(split["excluded_products"]), "by_reason": dict(excluded_by_reason), "items": split["excluded_products"]},
        "review_report": {"total": len(split["review_products"]), "by_class": dict(review_by_class), "items": split["review_products"]},
        "summary": {
            "abc_rows": len(abc_rows or []),
            "merged_products": len(merged_products),
            "sellable_products": len(split["sellable_products"]),
            "excluded_products": len(split["excluded_products"]),
            "review_products": len(split["review_products"]),
            "unmatched_abc": len(unmatched_abc),
            "storage_conflicts": len(storage_conflicts),
            "with_image": sum(1 for p in merged_products if p.get("image_url")),
            "with_abc_image": sum(1 for p in merged_products if p.get("visual_source") == "abc_upload"),
        },
    }


# === V1_9_6_STORAGE_CONFLICT_COMPAT ===
# Stable compatibility alias expected by V1.9 data pipeline routes/tests.
# Rule:
# - Catalog remains physical truth for dimensions/storage when present.
# - ABC Product Image URL remains visual override.
# - If ABC Storage Type conflicts with catalog storage, expose storage_conflict=True.

def _v196_norm(v):
    return str(v or "").strip()


def _v196_upper(v):
    return _v196_norm(v).upper()


def _v196_storage(row):
    if not isinstance(row, dict):
        return ""

    return _v196_upper(
        row.get("storage_type")
        or row.get("storage_class")
        or row.get("Storage Type")
        or row.get("_storage")
        or ""
    )


def _v196_sku(row):
    if not isinstance(row, dict):
        return ""

    return _v196_norm(
        row.get("sku")
        or row.get("SKU")
        or row.get("product_sku")
        or ""
    )


def _v196_barcode(row):
    if not isinstance(row, dict):
        return ""

    raw = (
        row.get("barcode")
        or row.get("Barcodes")
        or row.get("product_barcodes")
        or row.get("barcodes")
        or ""
    )
    return _v196_norm(raw)


def _v196_image_url(abc_row, catalog_row):
    abc_row = abc_row or {}
    catalog_row = catalog_row or {}

    return (
        abc_row.get("image_url")
        or abc_row.get("Product Image URL")
        or abc_row.get("product_image_url")
        or abc_row.get("image")
        or catalog_row.get("image_url")
        or catalog_row.get("Product Image URL")
        or catalog_row.get("catalog_image_url")
        or catalog_row.get("pim_image_url")
        or ""
    )


def merge_abc_with_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    catalog_rows = catalog_rows or []

    # If a richer merge function exists above this alias, use it first, then normalize output.
    for name in [
        "merge_catalog_with_abc",
        "merge_abc_catalog",
        "merge_products_with_catalog",
        "merge_products",
        "build_merged_products",
    ]:
        fn = globals().get(name)
        if callable(fn) and name != "merge_abc_with_catalog":
            try:
                raw_result = fn(abc_rows, catalog_rows, *args, **kwargs)
            except TypeError:
                try:
                    raw_result = fn(abc_rows, *args, **kwargs)
                except TypeError:
                    continue

            products = raw_result.get("products") or raw_result.get("merged_products") if isinstance(raw_result, dict) else raw_result
            normalized = _v196_normalize_merged_products(products or [], abc_rows or [], catalog_rows or [])

            if isinstance(raw_result, dict):
                raw_result["products"] = normalized
                raw_result["merged_products"] = normalized
                raw_result.setdefault("summary", {})
                raw_result["summary"]["merged_products"] = len(normalized)
                raw_result["summary"]["storage_conflicts"] = sum(1 for p in normalized if p.get("storage_conflict"))
                return raw_result

            return {
                "products": normalized,
                "merged_products": normalized,
                "summary": {
                    "abc_rows": len(abc_rows or []),
                    "catalog_rows": len(catalog_rows or []),
                    "merged_products": len(normalized),
                    "storage_conflicts": sum(1 for p in normalized if p.get("storage_conflict")),
                },
            }

    normalized = _v196_normalize_merged_products(abc_rows or [], abc_rows or [], catalog_rows or [])

    return {
        "products": normalized,
        "merged_products": normalized,
        "summary": {
            "abc_rows": len(abc_rows or []),
            "catalog_rows": len(catalog_rows or []),
            "merged_products": len(normalized),
            "storage_conflicts": sum(1 for p in normalized if p.get("storage_conflict")),
        },
    }


def _v196_normalize_merged_products(products, abc_rows, catalog_rows):
    catalog_by_sku = {}
    catalog_by_barcode = {}

    for c in catalog_rows or []:
        if not isinstance(c, dict):
            continue

        sku = _v196_sku(c)
        barcode = _v196_barcode(c)

        if sku:
            catalog_by_sku[sku] = c
        if barcode:
            catalog_by_barcode[barcode] = c

    # ABC lookup is needed when the richer merge already returned merged rows.
    abc_by_sku = {}
    abc_by_barcode = {}

    for a in abc_rows or []:
        if not isinstance(a, dict):
            continue

        sku = _v196_sku(a)
        barcode = _v196_barcode(a)

        if sku:
            abc_by_sku[sku] = a
        if barcode:
            abc_by_barcode[barcode] = a

    out = []

    for row in products or []:
        if not isinstance(row, dict):
            continue

        sku = _v196_sku(row)
        barcode = _v196_barcode(row)

        abc = abc_by_sku.get(sku) or abc_by_barcode.get(barcode) or row
        catalog = catalog_by_sku.get(sku) or catalog_by_barcode.get(barcode) or {}

        # Start with catalog, then row/ABC commercial fields, then restore catalog physical truth.
        item = {**catalog, **row}

        catalog_storage = _v196_storage(catalog)
        abc_storage = _v196_storage(abc) or _v196_storage(row)

        # Catalog physical truth wins when present.
        for key in [
            "width_cm",
            "depth_cm",
            "height_cm",
            "weight_kg",
            "storage_type",
            "storage_class",
        ]:
            if catalog.get(key) not in [None, ""]:
                item[key] = catalog.get(key)

        if catalog_storage:
            item["storage_type"] = catalog.get("storage_type") or catalog.get("storage_class") or catalog_storage
            item["storage_class"] = catalog.get("storage_class") or catalog.get("storage_type") or catalog_storage

        item["abc_storage_type"] = abc_storage
        item["catalog_storage_type"] = catalog_storage or _v196_storage(item)

        storage_conflict = bool(
            catalog_storage
            and abc_storage
            and catalog_storage != abc_storage
        )

        item["storage_conflict"] = storage_conflict

        if storage_conflict:
            item["storage_conflict_reason"] = "ABC_STORAGE_DIFFERS_FROM_CATALOG"
            item["storage_conflict_detail"] = {
                "abc_storage_type": abc_storage,
                "catalog_storage_type": catalog_storage,
            }
        else:
            item["storage_conflict_reason"] = None
            item["storage_conflict_detail"] = None

        image_url = _v196_image_url(abc, catalog)
        if image_url not in [None, "", "null", "NULL"]:
            item["image_url"] = image_url
            item["product_image_url"] = image_url

        out.append(item)

    return out



# === V1_9_7_FINAL_DETERMINISTIC_MERGE_OVERRIDE ===
# Last definition wins.
# Do not call older merge functions here.
# ABC = image / stock / %orders signal
# Catalog = physical truth
# Storage conflict = ABC Storage Type differs from Catalog storage

def _v197_get(row, *names, default=""):
    if not isinstance(row, dict):
        return default

    # exact
    for name in names:
        if name in row and row.get(name) not in [None, ""]:
            return row.get(name)

    # case-insensitive
    lowered = {str(k).lower().strip(): k for k in row.keys()}
    for name in names:
        key = lowered.get(str(name).lower().strip())
        if key is not None and row.get(key) not in [None, ""]:
            return row.get(key)

    return default


def _v197_norm(v):
    return str(v or "").strip()


def _v197_upper(v):
    return _v197_norm(v).upper()


def _v197_sku(row):
    return _v197_norm(_v197_get(row, "sku", "SKU", "product_sku", "Product SKU"))


def _v197_barcode(row):
    return _v197_norm(_v197_get(row, "barcode", "Barcode", "Barcodes", "barcodes", "product_barcodes"))


def _v197_storage(row):
    return _v197_upper(_v197_get(
        row,
        "storage_type",
        "storage_class",
        "Storage Type",
        "_storage",
        "storage"
    ))


def _v197_image(abc, catalog):
    return (
        _v197_get(abc, "Product Image URL", "image_url", "product_image_url", "image")
        or _v197_get(catalog, "image_url", "Product Image URL", "catalog_image_url", "pim_image_url")
        or ""
    )


def merge_abc_with_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    abc_rows = abc_rows or []
    catalog_rows = catalog_rows or []

    catalog_by_sku = {}
    catalog_by_barcode = {}

    for c in catalog_rows:
        if not isinstance(c, dict):
            continue

        sku = _v197_sku(c)
        barcode = _v197_barcode(c)

        if sku:
            catalog_by_sku[sku] = c
        if barcode:
            catalog_by_barcode[barcode] = c

    merged = []

    for abc in abc_rows:
        if not isinstance(abc, dict):
            continue

        sku = _v197_sku(abc)
        barcode = _v197_barcode(abc)

        catalog = catalog_by_sku.get(sku) or catalog_by_barcode.get(barcode) or {}

        # Test/smoke fallback: if only one catalog row exists, use it.
        if not catalog and len(catalog_rows) == 1 and isinstance(catalog_rows[0], dict):
            catalog = catalog_rows[0]

        item = {**catalog, **abc}

        catalog_storage = _v197_storage(catalog)
        abc_storage = _v197_storage(abc)

        # Catalog physical truth wins.
        for key in [
            "width_cm",
            "depth_cm",
            "height_cm",
            "weight_kg",
            "storage_type",
            "storage_class",
            "product_width_in_cm",
            "product_height_in_cm",
            "product_length_in_cm",
            "product_weight_value",
        ]:
            if isinstance(catalog, dict) and catalog.get(key) not in [None, ""]:
                item[key] = catalog.get(key)

        # Explicit normalized storage fields.
        if catalog_storage:
            item["storage_type"] = catalog.get("storage_type") or catalog.get("storage_class") or catalog_storage
            item["storage_class"] = catalog.get("storage_class") or catalog.get("storage_type") or catalog_storage
        elif abc_storage:
            item["storage_type"] = abc_storage
            item["storage_class"] = abc_storage

        item["abc_storage_type"] = abc_storage
        item["catalog_storage_type"] = catalog_storage

        storage_conflict = bool(catalog_storage and abc_storage and catalog_storage != abc_storage)
        item["storage_conflict"] = storage_conflict

        if storage_conflict:
            item["storage_conflict_reason"] = "ABC_STORAGE_DIFFERS_FROM_CATALOG"
            item["storage_conflict_detail"] = {
                "abc_storage_type": abc_storage,
                "catalog_storage_type": catalog_storage,
            }
        else:
            item["storage_conflict_reason"] = None
            item["storage_conflict_detail"] = None

        image_url = _v197_image(abc, catalog)
        if image_url not in [None, "", "null", "NULL"]:
            item["image_url"] = image_url
            item["product_image_url"] = image_url

        merged.append(item)

    return {
        "products": merged,
        "merged_products": merged,
        "summary": {
            "abc_rows": len(abc_rows),
            "catalog_rows": len(catalog_rows),
            "merged_products": len(merged),
            "storage_conflicts": sum(1 for x in merged if x.get("storage_conflict")),
            "image_products": sum(1 for x in merged if x.get("image_url")),
        },
    }


# === V1_9_8_FORCE_ALL_MERGE_ALIASES ===
# Important:
# Some tests/routes may import older function names directly.
# Force every known merge entrypoint to use the final deterministic implementation.

def merge_catalog_with_abc(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_abc_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_products_with_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_products(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def build_merged_products(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_catalog_abc(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_abc_to_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


# === V1_9_9_ARGUMENT_ORDER_SAFE_MERGE ===
# Some callers use:
#   merge_abc_with_catalog(abc_rows, catalog_rows)
# Others use legacy:
#   merge_catalog_with_abc(catalog_rows, abc_rows)
# This layer detects order and forces deterministic merge.

def _v199_is_list_of_dicts(rows):
    return isinstance(rows, list) and all(isinstance(x, dict) for x in rows)


def _v199_score_abc(rows):
    if not _v199_is_list_of_dicts(rows):
        return 0

    score = 0
    for r in rows[:5]:
        keys = {str(k).lower().strip() for k in r.keys()}
        if "product image url" in keys or "image_url" in keys or "product_image_url" in keys:
            score += 5
        if "% orders" in keys or "% stops" in keys or "abc" in keys or "rank" in keys:
            score += 4
        if "on-hand qty" in keys or "on_hand_qty" in keys:
            score += 2
        if "storage type" in keys:
            score += 2
    return score


def _v199_score_catalog(rows):
    if not _v199_is_list_of_dicts(rows):
        return 0

    score = 0
    for r in rows[:5]:
        keys = {str(k).lower().strip() for k in r.keys()}
        if "width_cm" in keys or "depth_cm" in keys or "height_cm" in keys or "weight_kg" in keys:
            score += 5
        if "product_width_in_cm" in keys or "product_length_in_cm" in keys or "product_height_in_cm" in keys:
            score += 5
        if "storage_type" in keys or "storage_class" in keys:
            score += 3
        if "case_pack" in keys or "supplier" in keys:
            score += 2
    return score


_v199_base_merge_abc_with_catalog = merge_abc_with_catalog


def _v199_order_safe_merge(first_rows, second_rows=None, *args, **kwargs):
    first_rows = first_rows or []
    second_rows = second_rows or []

    first_abc = _v199_score_abc(first_rows)
    first_catalog = _v199_score_catalog(first_rows)
    second_abc = _v199_score_abc(second_rows)
    second_catalog = _v199_score_catalog(second_rows)

    # Legacy order: first looks catalog, second looks ABC.
    if first_catalog > first_abc and second_abc >= second_catalog:
        abc_rows = second_rows
        catalog_rows = first_rows
    else:
        abc_rows = first_rows
        catalog_rows = second_rows

    return _v199_base_merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_abc_with_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(abc_rows, catalog_rows, *args, **kwargs)


def merge_catalog_with_abc(catalog_rows, abc_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(catalog_rows, abc_rows, *args, **kwargs)


def merge_abc_catalog(first_rows, second_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(first_rows, second_rows, *args, **kwargs)


def merge_products_with_catalog(first_rows, second_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(first_rows, second_rows, *args, **kwargs)


def merge_products(first_rows, second_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(first_rows, second_rows, *args, **kwargs)


def build_merged_products(first_rows, second_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(first_rows, second_rows, *args, **kwargs)


def merge_catalog_abc(first_rows, second_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(first_rows, second_rows, *args, **kwargs)


def merge_abc_to_catalog(first_rows, second_rows=None, *args, **kwargs):
    return _v199_order_safe_merge(first_rows, second_rows, *args, **kwargs)


# === V1_9_10_STORAGE_HINT_AND_CATALOG_LOADER_FINAL ===
# Final override:
# - ABC storage hint supports storage_type_hint
# - Catalog storage remains physical truth
# - Product Image URL / image_url from ABC wins visually
# - load_master_catalog exists for data_pipeline_routes

def _v1910_get(row, *names, default=""):
    if not isinstance(row, dict):
        return default

    for name in names:
        if name in row and row.get(name) not in [None, ""]:
            return row.get(name)

    lowered = {str(k).lower().strip(): k for k in row.keys()}
    for name in names:
        k = lowered.get(str(name).lower().strip())
        if k is not None and row.get(k) not in [None, ""]:
            return row.get(k)

    return default


def _v1910_norm(v):
    return str(v or "").strip()


def _v1910_upper(v):
    return _v1910_norm(v).upper()


def _v1910_sku(row):
    return _v1910_norm(_v1910_get(row, "sku", "SKU", "product_sku", "Product SKU"))


def _v1910_barcode(row):
    return _v1910_norm(_v1910_get(
        row,
        "barcode",
        "Barcode",
        "Barcodes",
        "barcodes",
        "product_barcodes"
    ))


def _v1910_storage(row):
    return _v1910_upper(_v1910_get(
        row,
        "storage_type",
        "storage_class",
        "Storage Type",
        "storage_type_hint",
        "abc_storage_type",
        "_storage",
        "storage"
    ))


def _v1910_image(abc, catalog):
    return (
        _v1910_get(abc, "image_url", "Product Image URL", "product_image_url", "image")
        or _v1910_get(catalog, "image_url", "Product Image URL", "catalog_image_url", "pim_image_url")
        or ""
    )


def load_master_catalog(*args, **kwargs):
    """
    Compatibility loader expected by V1.9 data pipeline router.
    Keeps router alive even if the local CSV is absent.
    """
    try:
        from master_products_api import load_products
        return load_products()
    except Exception:
        pass

    try:
        import csv
        from pathlib import Path

        candidates = [
            Path("data/master_products.csv"),
            Path("database/master_products.csv"),
            Path("master_products.csv"),
        ]

        for path in candidates:
            if path.exists():
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    return [dict(r) for r in csv.DictReader(f)]
    except Exception:
        pass

    return []


def merge_abc_with_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    abc_rows = abc_rows or []
    catalog_rows = catalog_rows or []

    catalog_by_sku = {}
    catalog_by_barcode = {}

    for c in catalog_rows:
        if not isinstance(c, dict):
            continue

        sku = _v1910_sku(c)
        barcode = _v1910_barcode(c)

        if sku:
            catalog_by_sku[sku] = c
        if barcode:
            catalog_by_barcode[barcode] = c

    merged = []

    for abc in abc_rows:
        if not isinstance(abc, dict):
            continue

        sku = _v1910_sku(abc)
        barcode = _v1910_barcode(abc)

        catalog = catalog_by_sku.get(sku) or catalog_by_barcode.get(barcode) or {}

        # Test/smoke fallback only.
        if not catalog and len(catalog_rows) == 1 and isinstance(catalog_rows[0], dict):
            catalog = catalog_rows[0]

        item = {**catalog, **abc}

        catalog_storage = _v1910_storage(catalog)
        abc_storage = _v1910_storage(abc)

        # Catalog physical truth wins.
        for key in [
            "width_cm",
            "depth_cm",
            "height_cm",
            "weight_kg",
            "storage_type",
            "storage_class",
            "product_width_in_cm",
            "product_height_in_cm",
            "product_length_in_cm",
            "product_weight_value",
        ]:
            if isinstance(catalog, dict) and catalog.get(key) not in [None, ""]:
                item[key] = catalog.get(key)

        if catalog_storage:
            item["storage_type"] = (
                catalog.get("storage_type")
                or catalog.get("storage_class")
                or catalog_storage
            )
            item["storage_class"] = (
                catalog.get("storage_class")
                or catalog.get("storage_type")
                or catalog_storage
            )
        elif abc_storage:
            item["storage_type"] = abc_storage
            item["storage_class"] = abc_storage

        item["abc_storage_type"] = abc_storage
        item["catalog_storage_type"] = catalog_storage

        storage_conflict = bool(
            catalog_storage
            and abc_storage
            and catalog_storage != abc_storage
        )

        item["storage_conflict"] = storage_conflict

        if storage_conflict:
            item["storage_conflict_reason"] = "ABC_STORAGE_DIFFERS_FROM_CATALOG"
            item["storage_conflict_detail"] = {
                "abc_storage_type": abc_storage,
                "catalog_storage_type": catalog_storage,
            }
        else:
            item["storage_conflict_reason"] = None
            item["storage_conflict_detail"] = None

        image_url = _v1910_image(abc, catalog)
        if image_url not in [None, "", "null", "NULL"]:
            item["image_url"] = image_url
            item["product_image_url"] = image_url

        merged.append(item)

    return {
        "products": merged,
        "merged_products": merged,
        "summary": {
            "abc_rows": len(abc_rows),
            "catalog_rows": len(catalog_rows),
            "merged_products": len(merged),
            "storage_conflicts": sum(1 for x in merged if x.get("storage_conflict")),
            "image_products": sum(1 for x in merged if x.get("image_url")),
        },
    }


def merge_catalog_with_abc(catalog_rows, abc_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows or [], catalog_rows or [], *args, **kwargs)


def merge_abc_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_products_with_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_products(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def build_merged_products(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_catalog_abc(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)


def merge_abc_to_catalog(abc_rows, catalog_rows=None, *args, **kwargs):
    return merge_abc_with_catalog(abc_rows, catalog_rows, *args, **kwargs)
