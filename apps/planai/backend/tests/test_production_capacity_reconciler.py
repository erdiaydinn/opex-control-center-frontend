from production_capacity_reconciler import reconcile_full_depth_capacity


def _plan(*, max_weight=40, products=None):
    return {
        "aisles": [
            {
                "aisle_id": "I",
                "modules": [
                    {
                        "module_id": 1,
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 40,
                                "shelf_depth_cm": 50,
                                "max_weight_kg": max_weight,
                                "products": products or [],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _product(sku, *, facings, weight, sales):
    return {
        "sku": sku,
        "width_cm": 10,
        "height_cm": 20,
        "depth_cm": 10,
        "weight_kg": weight,
        "facing_count": facings,
        "sales_qty_7d": sales,
    }


def test_reduces_low_sales_facings_until_full_depth_weight_is_safe():
    result = reconcile_full_depth_capacity(
        _plan(
            max_weight=40,
            products=[
                _product("HIGH", facings=3, weight=2, sales=100),
                _product("LOW", facings=3, weight=2, sales=1),
            ],
        )
    )

    assert result["valid"] is True
    assert result["adjustment_count"] == 2
    shelf = result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]
    facings = {row["sku"]: row["facing_count"] for row in shelf["products"]}
    assert facings == {"HIGH": 3, "LOW": 1}
    assert shelf["used_weight_kg"] == 40
    assert shelf["weight_model"] == "facing_x_depth_units_x_unit_weight"


def test_never_drops_last_facing_to_hide_irreducible_overload():
    result = reconcile_full_depth_capacity(
        _plan(
            max_weight=45,
            products=[_product("HEAVY", facings=1, weight=10, sales=10)],
        )
    )

    assert result["valid"] is False
    assert result["adjustment_count"] == 0
    assert any(
        blocker["code"] == "shelf_full_depth_weight_irreducible"
        for blocker in result["blockers"]
    )
    shelf = result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]
    assert shelf["products"][0]["facing_count"] == 1


def test_missing_product_capacity_evidence_fails_closed():
    product = _product("MISSING", facings=2, weight=1, sales=10)
    product["depth_cm"] = 0
    result = reconcile_full_depth_capacity(_plan(max_weight=100, products=[product]))

    assert result["valid"] is False
    assert any(
        blocker["code"] == "product_capacity_evidence_missing"
        for blocker in result["blockers"]
    )
