from commercial_merchandising import optimize_commercial_merchandising


def product(
    sku,
    category,
    sales,
    width,
    price,
    margin,
    elasticity=0.2,
    refill=0.2,
    visits=1,
    **extra,
):
    return {
        "sku": sku,
        "category_l2": category,
        "sales_qty_7d": sales,
        "width_cm": width,
        "unit_price": price,
        "unit_margin": margin,
        "space_elasticity": elasticity,
        "replenishment_cost_per_visit": refill,
        "replenishments_per_day": visits,
        "min_facing": 1,
        "max_facing": 5,
        **extra,
    }


def test_joint_assortment_and_facing_keeps_substitution_coverage():
    products = [
        product(
            "COLA-A",
            "DRINKS",
            100,
            10,
            2,
            0.7,
            substitution_group="COLA",
        ),
        product(
            "COLA-B",
            "DRINKS",
            25,
            10,
            1.5,
            0.4,
            substitution_group="COLA",
        ),
        product("WATER", "DRINKS", 90, 8, 1, 0.25),
    ]
    result = optimize_commercial_merchandising(
        products=products,
        category_capacity_cm={"DRINKS": 40},
        substitution_edges=[
            {
                "sku_a": "COLA-A",
                "sku_b": "COLA-B",
                "cross_elasticity": 0.8,
            }
        ],
    )
    assert result["available"] is True
    selected = {
        row["sku"]: row["facing_count"]
        for row in result["selected_plan"]
    }
    assert "COLA-A" in selected
    assert selected["COLA-A"] >= 1
    assert result["substitution_groups"][0]["selected_skus"]
    assert result["total_used_width_cm"] <= 40


def test_weighted_category_capacity_favors_commercial_value():
    products = [
        product("A", "HIGH", 200, 10, 4, 2.0),
        product("B", "LOW", 10, 10, 1, 0.1),
    ]
    result = optimize_commercial_merchandising(
        products=products,
        total_shelf_width_cm=100,
    )
    assert result["available"] is True
    capacity = result["category_capacity_cm"]
    assert capacity["HIGH"] > capacity["LOW"]
    assert round(sum(capacity.values()), 3) == 100.0


def test_replenishment_and_space_elasticity_are_in_objective():
    products = [
        product(
            "ELASTIC",
            "SNACK",
            80,
            10,
            2,
            0.6,
            elasticity=0.7,
            refill=0.1,
            visits=1,
        ),
        product(
            "REFILL-HEAVY",
            "SNACK",
            80,
            10,
            2,
            0.6,
            elasticity=0.0,
            refill=8,
            visits=4,
        ),
    ]
    result = optimize_commercial_merchandising(
        products=products,
        category_capacity_cm={"SNACK": 50},
    )
    selected = {row["sku"]: row for row in result["selected_plan"]}
    assert selected["ELASTIC"]["facing_count"] >= selected.get(
        "REFILL-HEAVY",
        {"facing_count": 0},
    )["facing_count"]
    assert selected["ELASTIC"]["space_elasticity"] == 0.7


def test_missing_economic_fields_are_not_silently_attested():
    result = optimize_commercial_merchandising(
        products=[
            {
                "sku": "X",
                "category_l2": "C",
                "sales_qty_7d": 10,
                "width_cm": 10,
            }
        ],
        category_capacity_cm={"C": 20},
    )
    assert result["available"] is True
    assert result["commercial_evidence_complete"] is False
    assert result["market_leadership_claim_allowed"] is False


def test_is_deterministic():
    products = [
        product("A", "C", 20, 10, 2, 0.5),
        product("B", "C", 30, 10, 2, 0.5),
    ]
    left = optimize_commercial_merchandising(
        products=products,
        category_capacity_cm={"C": 40},
    )
    right = optimize_commercial_merchandising(
        products=products,
        category_capacity_cm={"C": 40},
    )
    assert left["commercial_fingerprint"] == right["commercial_fingerprint"]
    assert left["selected_plan"] == right["selected_plan"]
