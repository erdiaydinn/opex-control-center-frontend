from physical_capacity_v2 import validate_planogram_capacity_v2


def plan(weight_limit=20, used_weight=2, facings=2, depth=10, weight=1):
    return {
        "aisles": [{
            "aisle_id": "A",
            "modules": [{
                "module_id": 1,
                "shelves": [{
                    "shelf_no": 1,
                    "shelf_width_cm": 100,
                    "shelf_height_cm": 40,
                    "shelf_depth_cm": 50,
                    "max_weight_kg": weight_limit,
                    "used_weight_kg": used_weight,
                    "used_width_cm": 22,
                    "products": [{
                        "sku": "SKU-1",
                        "width_cm": 10,
                        "height_cm": 20,
                        "depth_cm": depth,
                        "weight_kg": weight,
                        "facing_count": facings,
                    }],
                }],
            }],
        }],
    }


def test_full_depth_weight_is_used():
    result = validate_planogram_capacity_v2(plan(weight_limit=9, facings=2, depth=10, weight=1))
    assert result["valid"] is False
    assert any(v["code"] == "shelf_full_depth_weight_exceeded" for v in result["violations"])


def test_legacy_understatement_is_warning_when_true_capacity_is_safe():
    result = validate_planogram_capacity_v2(plan(weight_limit=20, used_weight=2, facings=2))
    assert result["valid"] is True
    assert any(w["code"] == "legacy_declared_weight_understated" for w in result["warnings"])


def test_linear_width_uses_spacing_buffer():
    result = validate_planogram_capacity_v2(plan(weight_limit=100, facings=10))
    assert result["valid"] is False
    assert any(v["code"] == "shelf_linear_width_exceeded" for v in result["violations"])


def test_missing_mass_is_fail_closed():
    payload = plan(weight_limit=100)
    payload["aisles"][0]["modules"][0]["shelves"][0]["products"][0]["weight_kg"] = 0
    result = validate_planogram_capacity_v2(payload)
    assert result["valid"] is False
    assert result["missing_evidence_count"] == 1
