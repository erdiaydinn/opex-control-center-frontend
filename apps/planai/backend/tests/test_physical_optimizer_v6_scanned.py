from __future__ import annotations

import physical_optimizer_v6_scanned as optimizer


def product(
    sku: str,
    *,
    storage: str = "AMBIENT",
    width_cm: float = 50,
    sales: float = 10,
) -> dict[str, object]:
    return {
        "sku": sku,
        "name": sku,
        "category": "SNACKS" if storage == "AMBIENT" else storage,
        "brand": "EAY",
        "storage_type": storage,
        "width_cm": width_cm,
        "height_cm": 30,
        "depth_cm": 20,
        "weight_g": 500,
        "weekly_sales": sales,
    }


def shelf(storage: str = "AMBIENT") -> dict[str, object]:
    return {
        "shelf_no": 1,
        "shelf_width_cm": 55,
        "shelf_height_cm": 60,
        "shelf_depth_cm": 50,
        "max_weight_kg": 50,
        "allowed_storage_type": storage,
        "zone_type": "eye",
        "products": [],
    }


def module(
    module_id: str,
    *,
    x_m: float,
    y_m: float,
    rotation_deg: float,
    storage: str = "AMBIENT",
) -> dict[str, object]:
    return {
        "module_id": module_id,
        "side": "L",
        "position": 1 if module_id == "NEAR" else 2,
        "x_m": x_m,
        "y_m": y_m,
        "width_m": 1.2,
        "depth_m": 0.6,
        "rotation_deg": rotation_deg,
        "fixture_type": "steel_rack" if storage == "AMBIENT" else "chilled_cooler",
        "storage_type": storage,
        "relocatable": False,
        "utility_relocation_attested": False,
        "shelves": [shelf(storage)],
    }


def layout() -> dict[str, object]:
    return {
        "source": "fingerprint_bound_scanned_fixture_review",
        "aisles": [
            {
                "aisle_id": "A01",
                "modules": [
                    module("NEAR", x_m=2.0, y_m=1.5, rotation_deg=17),
                    module("FAR", x_m=8.2, y_m=6.4, rotation_deg=-17),
                ],
            }
        ],
    }


def store_dna() -> dict[str, object]:
    return {
        "architecture": {
            "schema_version": 2,
            "coordinate_system": "cartesian_m",
            "source": "lidar_scan",
            "source_ref": "scan://store-v2-reviewed",
            "floor_width_m": 12,
            "floor_depth_m": 9,
            "elements": [
                {
                    "element_id": "wall-angled",
                    "element_type": "wall",
                    "center_x_m": 5.0,
                    "center_y_m": 4.7,
                    "width_m": 2.4,
                    "depth_m": 0.12,
                    "rotation_deg": 17,
                    "clearance_m": 0,
                },
                {
                    "element_id": "picker-entry",
                    "element_type": "picker_entry",
                    "center_x_m": 0.8,
                    "center_y_m": 0.8,
                    "width_m": 0.4,
                    "depth_m": 0.4,
                    "rotation_deg": 0,
                    "clearance_m": 0,
                },
                {
                    "element_id": "picker-exit",
                    "element_type": "picker_exit",
                    "center_x_m": 0.8,
                    "center_y_m": 0.8,
                    "width_m": 0.4,
                    "depth_m": 0.4,
                    "rotation_deg": 0,
                    "clearance_m": 0,
                },
                {
                    "element_id": "inbound",
                    "element_type": "inbound",
                    "center_x_m": 1.4,
                    "center_y_m": 7.4,
                    "width_m": 1.4,
                    "depth_m": 1.0,
                    "rotation_deg": 0,
                    "clearance_m": 0,
                },
                {
                    "element_id": "dispatch",
                    "element_type": "dispatch",
                    "center_x_m": 10.2,
                    "center_y_m": 1.0,
                    "width_m": 1.2,
                    "depth_m": 1.0,
                    "rotation_deg": 0,
                    "clearance_m": 0,
                },
            ],
        }
    }


def orders() -> list[dict[str, list[str]]]:
    return [
        *({"skus": ["FAST"]} for _ in range(18)),
        *({"skus": ["SLOW"]} for _ in range(3)),
        *({"skus": ["FAST", "SLOW"]} for _ in range(4)),
    ]


def placed_module(planogram: dict[str, object], sku: str) -> str | None:
    for aisle in planogram.get("aisles") or []:
        for row in aisle.get("modules") or []:
            for row_shelf in row.get("shelves") or []:
                for placed in row_shelf.get("products") or []:
                    if str(placed.get("sku") or "").upper() == sku:
                        return str(row.get("module_id"))
    return None


def test_scanned_v2_optimizer_uses_real_baskets_and_preserves_arbitrary_angles() -> None:
    result = optimizer.optimize_scanned_store(
        products=[
            product("FAST", sales=100),
            product("SLOW", sales=5),
        ],
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        max_candidates=24,
    )

    assert result["allowed"] is True
    assert result["candidate_count"] == 24
    assert result["production_authority"] is False
    assert result["store_dna_authority"] is False
    assert result["installation_approved"] is False
    assert result["relocation_execution_allowed"] is False
    assert result["capex_approved"] is False
    assert result["global_optimum_claim"] is False
    assert result["field_evidence"] is False
    assert placed_module(result["planogram"], "FAST") == "NEAR"
    assert placed_module(result["planogram"], "SLOW") == "FAR"
    assert result["selected_tour"]["coverage_pct"] == 100.0
    assert result["selected_tour"]["order_count"] == len(orders())
    assert result["physical_truth"]["architecture_v2"]["valid"] is True
    assert result["physical_truth"]["architecture_v2"]["non_orthogonal_element_count"] >= 1
    near = result["planogram"]["aisles"][0]["modules"][0]
    far = result["planogram"]["aisles"][0]["modules"][1]
    assert near["rotation_deg"] == 17
    assert far["rotation_deg"] == -17
    assert len(result["optimizer_fingerprint"]) == 64


def test_scanned_optimizer_is_deterministic_for_same_evidence() -> None:
    kwargs = {
        "products": [product("FAST", sales=100), product("SLOW", sales=5)],
        "layout": layout(),
        "store_dna": store_dna(),
        "orders": orders(),
        "max_candidates": 12,
    }
    first = optimizer.optimize_scanned_store(**kwargs)
    second = optimizer.optimize_scanned_store(**kwargs)

    assert first["selected_profile_id"] == second["selected_profile_id"]
    assert first["selected_objective"] == second["selected_objective"]
    assert first["planogram"] == second["planogram"]
    assert first["optimizer_fingerprint"] == second["optimizer_fingerprint"]


def test_scanned_optimizer_never_places_chilled_on_ambient_and_keeps_oversize_unplaced() -> None:
    result = optimizer.optimize_scanned_store(
        products=[
            product("FAST", sales=100),
            product("CHILL", storage="CHILLED", sales=50),
            product("OVERSIZE", width_cm=90, sales=20),
        ],
        layout=layout(),
        store_dna=store_dna(),
        orders=[
            {"skus": ["FAST"]},
            {"skus": ["CHILL"]},
            {"skus": ["OVERSIZE"]},
        ],
        max_candidates=8,
    )

    assert result["allowed"] is True
    assert placed_module(result["planogram"], "FAST") is not None
    assert placed_module(result["planogram"], "CHILL") is None
    assert placed_module(result["planogram"], "OVERSIZE") is None
    assert "CHILL" in result["unplaced_skus"]
    assert "OVERSIZE" in result["unplaced_skus"]
    assert result["selected_objective"]["unplaced_sku_count"] == 2


def test_scanned_optimizer_fails_closed_without_baskets_or_complete_physical_truth() -> None:
    no_baskets = optimizer.optimize_scanned_store(
        products=[product("FAST")],
        layout=layout(),
        store_dna=store_dna(),
        orders=[],
    )
    assert no_baskets["allowed"] is False
    assert "scanned_optimizer_order_baskets_required" in no_baskets["blockers"]
    assert no_baskets["production_authority"] is False

    incomplete = product("FAST")
    incomplete.pop("width_cm")
    invalid = optimizer.optimize_scanned_store(
        products=[incomplete],
        layout=layout(),
        store_dna=store_dna(),
        orders=[{"skus": ["FAST"]}],
    )
    assert invalid["allowed"] is False
    assert any("width" in blocker for blocker in invalid["blockers"])
