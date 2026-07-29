import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.visual_twin_payload import build_visual_twin_payload


def test_visual_twin_uses_image_tile_not_label():
    result = {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [
                                {
                                    "shelf_no": 1,
                                    "allowed_storage_type": "AMBIENT",
                                    "shelf_width_cm": 100,
                                    "products": [
                                        {
                                            "sku": "MRK.00506",
                                            "product_name": "Coca-Cola 1 L",
                                            "storage_type": "AMBIENT",
                                            "image_url": "https://example.com/coke.jpg",
                                            "facing_count": 2,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    }
    payload = build_visual_twin_payload(result)
    assert payload["summary"]["placed_tiles"] == 1
    tile = payload["product_tiles"][0]
    assert tile["render_mode"] == "image_tile"
    assert tile["show_text_label_default"] is False
    assert tile["image_url"].endswith("coke.jpg")


def test_excluded_products_do_not_enter_scene():
    result = {
        "planogram": {"aisles": []},
        "excluded_products": [
            {
                "sku": "MRK.07018",
                "product_name": "Shopping Bag",
                "image_url": "https://example.com/bag.jpg",
                "planogram_class": "EXCLUDED_OPERATIONAL_SUPPLY",
                "reason_code": "OPERATIONAL_SUPPLY_NOT_SHELF_PRODUCT",
            }
        ],
    }
    payload = build_visual_twin_payload(result)
    assert payload["summary"]["placed_tiles"] == 0
    assert payload["summary"]["excluded_products"] == 1
    assert payload["scene_rules"]["excluded_products_enter_scene"] is False
    assert payload["excluded_products"][0]["sku"] == "MRK.07018"


def test_fallback_tile_when_no_image():
    result = {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "B",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [
                                {
                                    "shelf_no": 2,
                                    "allowed_storage_type": "CHILLED",
                                    "products": [
                                        {
                                            "sku": "MILK1",
                                            "product_name": "Milk",
                                            "storage_type": "CHILLED",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    }
    payload = build_visual_twin_payload(result)
    assert payload["product_tiles"][0]["render_mode"] == "fallback_tile"
    assert payload["summary"]["fallback_tiles"] == 1


if __name__ == "__main__":
    test_visual_twin_uses_image_tile_not_label()
    test_excluded_products_do_not_enter_scene()
    test_fallback_tile_when_no_image()
    print("✅ V1.9.3 visual product twin integration tests passed")