from commercial_physical_convergence import (
    _commercial_products_for_physical_space,
    _physical_projection_product,
    compare_commercial_to_physical,
)


def _physical(*products):
    return {
        "publishable": True,
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [{"shelf_no": 1, "products": list(products)}],
                        }
                    ],
                }
            ]
        },
    }


def test_reports_unplaced_and_facing_shortfall():
    commercial = {
        "available": True,
        "selected_plan": [
            {"sku": "A", "facing_count": 3},
            {"sku": "B", "facing_count": 2},
        ],
    }
    result = compare_commercial_to_physical(
        commercial_result=commercial,
        physical_result=_physical({"sku": "A", "facing_count": 2}),
    )
    assert result["unplaced_target_skus"] == ["B"]
    assert result["facing_shortfall_total"] == 3
    assert result["converged"] is False


def test_converges_when_conservative_reservation_meets_target():
    commercial = {
        "available": True,
        "selected_plan": [
            {"sku": "A", "facing_count": 4},
            {"sku": "B", "facing_count": 1},
        ],
    }
    result = compare_commercial_to_physical(
        commercial_result=commercial,
        physical_result=_physical(
            {"sku": "A", "facing_count": 5},
            {"sku": "B", "facing_count": 1},
        ),
    )
    assert result["facing_shortfall_total"] == 0
    assert result["rows"][0]["conservative_over_reservation"] == 1
    assert result["converged"] is True


def test_convergence_commercial_width_uses_physical_spacing_and_facing_cap():
    products = _commercial_products_for_physical_space(
        [{"sku": "A", "width_cm": 10, "min_facing": 2, "max_facing": 12}]
    )
    assert products[0]["width_cm"] == 11.0
    assert products[0]["max_facing"] == 5
    assert products[0]["min_facing"] == 2


def test_four_facing_projection_reserves_five_without_overwriting_source_truth():
    product = _physical_projection_product(
        {"sku": "A", "sales_qty_7d": 100, "case_pack_qty": 12},
        target_facing=4,
        commercial_fingerprint="fingerprint",
    )
    assert product["commercial_target_facing"] == 4
    assert product["commercial_physical_reserved_facing"] == 5
    assert product["commercial_observed_sales_qty_7d"] == 100
    assert product["sales_qty_7d"] == 0
    assert product["tier"] == "HOT"
