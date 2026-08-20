from commercial_physical_convergence import compare_commercial_to_physical


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


def test_converges_only_when_all_commercial_facings_physically_exist():
    commercial = {
        "available": True,
        "selected_plan": [
            {"sku": "A", "facing_count": 2},
            {"sku": "B", "facing_count": 1},
        ],
    }
    result = compare_commercial_to_physical(
        commercial_result=commercial,
        physical_result=_physical(
            {"sku": "A", "facing_count": 2},
            {"sku": "B", "facing_count": 1},
        ),
    )
    assert result["facing_shortfall_total"] == 0
    assert result["converged"] is True
