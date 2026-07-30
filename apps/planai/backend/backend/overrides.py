from storage import load_overrides, save_overrides


def apply_product_override(sku, payload):
    data = load_overrides()

    sku = str(sku)
    if sku not in data["products"]:
        data["products"][sku] = {}

    data["products"][sku].update(payload)
    save_overrides(data)


def get_product_override(sku):
    data = load_overrides()
    return data["products"].get(str(sku), {})


def apply_overrides_to_product(product):
    sku = product.get("sku")
    override = get_product_override(sku)

    if not override:
        return product

    updated = dict(product)
    updated.update(override)
    return updated