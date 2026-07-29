from typing import Any, Dict


def _txt(v: Any) -> str:
    return str(v or "").strip()


def _upper(v: Any) -> str:
    return _txt(v).upper()


def _haystack(product: Dict[str, Any]) -> str:
    fields = [
        "sku",
        "product_name",
        "Product Name",
        "brand",
        "brand_name",
        "Category L1",
        "Category L2",
        "category_l1",
        "category_l2",
        "frontend_category_local",
        "frontend_subcategory_local",
        "storage_type",
        "Storage Type",
    ]
    return " ".join(_upper(product.get(k)) for k in fields)


def classify_planogram_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Front-door classifier before placement.

    Important:
    - Excluded products are NOT unplaced.
    - They are intentionally outside planogram placement.
    """

    raw = _haystack(product)

    # 1) Shopping bag / operational supply
    if any(x in raw for x in [
        "SHOPPING BAG",
        "ALIŞVERİŞ POŞET",
        "ALISVERIS POSET",
        "POŞET",
        "POSET",
        "CARRIER BAG",
        "MARKET BAG",
        "DISPOSABLE BAG",
    ]):
        return {
            "planogram_class": "EXCLUDED_OPERATIONAL_SUPPLY",
            "is_sellable_planogram_product": False,
            "exclude_from_planogram": True,
            "reason_code": "OPERATIONAL_SUPPLY_NOT_SHELF_PRODUCT",
            "human_action": "Alışveriş poşeti operasyonel sarftır; raf planogram ürünü olarak yerleştirilmez.",
        }

    # 2) Equipment / machine / operational asset
    if any(x in raw for x in [
        "COFFEE MACHINE",
        "KAHVE MAKİNESİ",
        "KAHVE MAKINESI",
        "EVERYDAY COFFEE MACHINE",
        "EVERYDAY",
        "MACHINE",
        "MAKİNE",
        "MAKINE",
        "EQUIPMENT",
        "EKİPMAN",
        "EKIPMAN",
    ]):
        return {
            "planogram_class": "EXCLUDED_EQUIPMENT",
            "is_sellable_planogram_product": False,
            "exclude_from_planogram": True,
            "reason_code": "EQUIPMENT_NOT_SHELF_PRODUCT",
            "human_action": "Bu kayıt ekipman/operasyonel asset olarak sınıflandı; ürün rafına yerleştirilmez.",
        }

    # 3) Bakery / bake-off / La Lorraine / Ramazan pidesi
    # Marka bazlı değil; ürün adı + kategori + bakery sinyali birlikte yakalanır.
    if any(x in raw for x in [
        "LA LORRAINE",
        "BAGUETTE",
        "BAGEL",
        "SİMİT",
        "SIMIT",
        "RAMAZAN PİDESİ",
        "RAMAZAN PIDESI",
        "PİDE",
        "PIDE",
        "BAKERY",
        "FIRIN",
        "FIRIN ÜRÜNÜ",
        "FIRIN URUNU",
        "EKMEK",
        "BREAD",
    ]):
        return {
            "planogram_class": "BAKERY_FLOW_REVIEW",
            "is_sellable_planogram_product": False,
            "exclude_from_planogram": True,
            "reason_code": "BAKERY_FLOW_NOT_REGULAR_SHELF",
            "human_action": "Fırın/bakery akışı normal ambient raf ürünü gibi yerleştirilmez; bakery/donuk/özel fixture akışıyla değerlendirilmelidir.",
        }

    # 4) Ice cream / Algida
    if any(x in raw for x in [
        "ALGIDA",
        "ICE CREAM",
        "DONDURMA",
        "MAGNUM",
        "CORNETTO",
        "CARTE D'OR",
        "CARTE DOR",
    ]):
        return {
            "planogram_class": "ICE_CREAM_PRODUCT",
            "is_sellable_planogram_product": True,
            "exclude_from_planogram": False,
            "required_fixture_class": "ICE_CREAM",
            "required_storage_class": "FROZEN",
            "reason_code": "ICE_CREAM_REQUIRES_SPECIAL_FREEZER",
            "human_action": "Dondurma ürünü yalnızca Algida/ice cream freezer veya uygun donuk fixture içinde değerlendirilmelidir.",
        }

    return {
        "planogram_class": "SELLABLE_PLANOGRAM_PRODUCT",
        "is_sellable_planogram_product": True,
        "exclude_from_planogram": False,
        "reason_code": "SELLABLE_PRODUCT",
        "human_action": "Ürün normal planogram yerleşimi için uygundur.",
    }


def split_products_for_planogram(products):
    sellable = []
    excluded = []
    review = []

    for p in products or []:
        cls = classify_planogram_product(p)
        enriched = {**p, **cls}

        if cls["exclude_from_planogram"]:
            excluded.append(enriched)
            if cls["planogram_class"] == "BAKERY_FLOW_REVIEW":
                review.append(enriched)
        else:
            sellable.append(enriched)

    return {
        "sellable_products": sellable,
        "excluded_products": excluded,
        "review_products": review,
        "summary": {
            "input_products": len(products or []),
            "sellable_products": len(sellable),
            "excluded_products": len(excluded),
            "review_products": len(review),
        },
    }
