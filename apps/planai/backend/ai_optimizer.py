from copy import deepcopy


def key(v):
    return str(v or "").strip().upper()


def num(v, d=0):
    try:
        if v is None or v == "":
            return d
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except Exception:
        return d


def iter_shelves(plan):
    for a in plan.get("aisles", []):
        for m in a.get("modules", []):
            for s in m.get("shelves", []):
                yield a, m, s


def clean_empty_shelf_tags(plan):
    for _, _, s in iter_shelves(plan):
        if not s.get("products"):
            s["brand"] = None
            s["category"] = None
            s["used"] = 0
    return plan


def recalc_usage(plan):
    for _, _, s in iter_shelves(plan):
        total = 0
        for p in s.get("products", []):
            if p.get("used_width_cm") is not None:
                total += num(p.get("used_width_cm"), 0)
            elif p.get("width_cm") is not None:
                total += num(p.get("width_cm"), 10) * num(p.get("facing_count", p.get("facing", 1)), 1) * 1.1
            else:
                total += 10 * num(p.get("facing_count", p.get("facing", 1)), 1)

        s["used"] = round(total, 1)

        if s.get("products"):
            first = s["products"][0]
            s["brand"] = key(first.get("brand"))
            s["category"] = key(first.get("category_l2") or first.get("category") or s.get("category"))
        else:
            s["brand"] = None
            s["category"] = None

    return plan


def find_back_ambient_shelf(plan):
    preferred_aisles = ["Z", "J", "K", "L", "I", "H", "G"]

    for target in preferred_aisles:
        for a, m, s in iter_shelves(plan):
            if key(a.get("aisle_id")) != target:
                continue
            if key(s.get("allowed_storage_type")) in ["AMBIENT", ""]:
                return s

    for _, _, s in iter_shelves(plan):
        if key(s.get("allowed_storage_type")) in ["AMBIENT", ""]:
            return s

    return None


def move_product(product, source_shelf, target_shelf):
    source_shelf["products"] = [
        x for x in source_shelf.get("products", [])
        if x.get("sku") != product.get("sku")
    ]
    target_shelf.setdefault("products", []).append(product)


def is_cleaning_item(item):
    raw = key(
        f"{item.get('sku', '')} "
        f"{item.get('product_name', '')} "
        f"{item.get('brand', '')} "
        f"{item.get('category_l2', '')} "
        f"{item.get('category', '')}"
    )
    return any(x in raw for x in [
        "DOMESTOS", "DETERJAN", "TEMİZ", "TEMIZ", "BLEACH",
        "CLEAN", "ÇAMAŞIR", "CAMASIR", "YUMUŞATICI", "YUMUSATICI"
    ])


def fix_nonfood_from_front(plan):
    target_shelf = find_back_ambient_shelf(plan)
    if not target_shelf:
        return plan

    for a, m, s in list(iter_shelves(plan)):
        if key(a.get("aisle_id")) != "A":
            continue

        for p in list(s.get("products", [])):
            if is_cleaning_item(p):
                move_product(p, s, target_shelf)

    return plan


def force_place_unplaced_nonfood(plan, unplaced):
    target_shelf = find_back_ambient_shelf(plan)
    if not target_shelf:
        return plan, unplaced

    remaining = []

    for item in unplaced:
        if item.get("reason") == "approval":
            remaining.append(item)
            continue

        if is_cleaning_item(item):
            forced_product = {
                "sku": item.get("sku"),
                "product_name": item.get("product_name", item.get("sku")),
                "brand": item.get("brand", "Domestos"),
                "category_l2": item.get("category_l2", "CLEANING"),
                "storage_type": item.get("storage_type", "AMBIENT"),
                "facing": item.get("facing", 1),
                "facing_count": item.get("facing_count", item.get("facing", 1)),
                "width_cm": item.get("width_cm", 10),
                "used_width_cm": num(item.get("width_cm", 10), 10) * num(item.get("facing_count", item.get("facing", 1)), 1) * 1.1,
                "aisle": "Z",
                "aisle_id": "Z",
                "forced": True,
                "reasoning": "AI optimizer force-placed non-food/cleaning item to back ambient aisle."
            }

            target_shelf.setdefault("products", []).append(forced_product)
        else:
            remaining.append(item)

    return plan, remaining


def fix_brand_split(plan):
    brand_map = {}

    for a, m, s in iter_shelves(plan):
        for p in s.get("products", []):
            b = key(p.get("brand"))
            if not b:
                continue
            brand_map.setdefault(b, []).append((s, p))

    for brand, items in brand_map.items():
        if len(items) <= 1:
            continue

        target_shelf = max(
            [s for s, _ in items],
            key=lambda sh: len(sh.get("products", []))
        )

        for source_shelf, product in list(items):
            if source_shelf is target_shelf:
                continue

            # Aynı marka ama farklı kategori ise aynı rafa taşımak zorunda değil.
            # Ancak aynı markayı tamamen dağınık bırakma: hedef rafa kapasite uygunsa taşı.
            current_used = sum(num(x.get("used_width_cm"), 10) for x in target_shelf.get("products", []))
            product_width = num(product.get("used_width_cm"), 10)
            shelf_width = num(target_shelf.get("shelf_width_cm"), 100)

            if current_used + product_width <= shelf_width:
                move_product(product, source_shelf, target_shelf)

        target_shelf["brand"] = brand

    return plan


def normalize_product_locations(plan):
    for a, m, s in iter_shelves(plan):
        for p in s.get("products", []):
            p["aisle"] = a.get("aisle_id")
            p["aisle_id"] = a.get("aisle_id")
            p["module_id"] = m.get("module_id")
            p["shelf_no"] = s.get("shelf_no")
    return plan


def optimize_planogram(result):
    result = deepcopy(result)
    plan = result.get("planogram", {})
    unplaced = result.get("unplaced", [])

    plan = fix_nonfood_from_front(plan)
    plan, unplaced = force_place_unplaced_nonfood(plan, unplaced)
    plan = fix_brand_split(plan)
    plan = clean_empty_shelf_tags(plan)
    plan = recalc_usage(plan)
    plan = normalize_product_locations(plan)

    result["planogram"] = plan
    result["unplaced"] = unplaced

    if "summary" in result:
        result["summary"]["unplaced"] = len(unplaced)
        result["summary"]["placed"] = result["summary"].get("total", 0) - len(unplaced)

    result["optimized"] = True

    return result