from services.abc_upload_service import parse_abc_dataframe
from services.catalog_abc_merge import merge_abc_with_catalog
import pandas as pd


def test_abc_parser_standard_columns():
    df = pd.DataFrame([
        {
            "Country": "Turkey",
            "Store": "Yemeksepeti Market, Fulya (İstanbul)",
            "Rank": 1,
            "Category L1": "Beverages",
            "Category L2": "Water",
            "SKU": "MRK.05019",
            "Product Name": "Buzdagi Water 6 x 1.5 L",
            "Barcodes": "08699878422469",
            "ABC": "A",
            "On-Hand Qty": 595,
            "Location": "Z10-01-W01",
            "Storage Type": "AMBIENT",
            "Is A Zone": "No",
            "Secondary Location": "",
            "Product Image URL": "https://example.com/product.jpg",
            "% Stops": "1.03%",
            "% Orders": "7.05%",
        }
    ])
    parsed = parse_abc_dataframe(df)
    assert parsed["success"] is True
    row = parsed["rows"][0]
    assert row["sku"] == "MRK.05019"
    assert row["image_url"].startswith("https://")
    assert row["order_share_pct"] == 7.05
    assert row["current_location"] == "Z10-01-W01"


def test_catalog_abc_merge_physical_truth_and_visual_from_abc():
    abc_rows = [{
        "sku": "MRK.05019",
        "barcode": "08699878422469",
        "product_name": "Buzdagi Water 6 x 1.5 L",
        "abc_class": "A",
        "on_hand_qty": 595,
        "order_share_pct": 7.05,
        "stop_share_pct": 1.03,
        "storage_type_hint": "CHILLED",  # conflict on purpose
        "image_url": "https://example.com/abc-image.jpg",
        "current_location": "Z10-01-W01",
    }]
    catalog_rows = [{
        "sku": "MRK.05019",
        "product_barcodes": "08699878422469",
        "product_name": "Buzdagi Water 6 x 1.5 L",
        "brand_name": "Buzdagi",
        "frontend_category_local": "Beverages",
        "frontend_subcategory_local": "Water",
        "storage_type": "AMBIENT",
        "width_cm": "9",
        "height_cm": "30",
        "depth_cm": "9",
        "weight_kg": "1.5",
        "image_url": "https://example.com/catalog-image.jpg",
    }]
    merged = merge_abc_with_catalog(abc_rows, catalog_rows)
    p = merged["products"][0]
    assert p["storage_type"] == "AMBIENT"  # catalog wins
    assert p["storage_conflict"] is True
    assert p["image_url"] == "https://example.com/abc-image.jpg"  # ABC visual wins
    assert p["order_share_pct"] == 7.05
    assert p["current_location"] == "Z10-01-W01"


if __name__ == "__main__":
    test_abc_parser_standard_columns()
    test_catalog_abc_merge_physical_truth_and_visual_from_abc()
    print("✅ V1.9 data pipeline tests passed")
