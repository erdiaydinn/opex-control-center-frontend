import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.catalog_abc_merge import merge_catalog_abc


def test_pipeline_excludes_shopping_bag_even_high_orders():
    abc = [{"SKU": "MRK.07018", "Product Name": "Shopping Bag", "Barcodes": "19051905111192", "ABC": "A", "% Orders": "98.38%", "% Stops": "14.38%", "On-Hand Qty": 18132, "Product Image URL": "https://example.com/bag.jpg", "Location": "001-01-B01", "Storage Type": "AMBIENT"}]
    catalog = [{"sku": "MRK.07018", "product_name": "Shopping Bag", "barcode": "19051905111192", "storage_type": "AMBIENT", "width_cm": 18, "height_cm": 28, "depth_cm": 2, "weight_kg": 0.02}]
    result = merge_catalog_abc(abc, catalog)
    assert result["summary"]["abc_rows"] == 1
    assert result["summary"]["sellable_products"] == 0
    assert result["summary"]["excluded_products"] == 1
    assert result["excluded_products"][0]["planogram_class"] == "EXCLUDED_OPERATIONAL_SUPPLY"
    assert result["excluded_products"][0]["image_url"] == "https://example.com/bag.jpg"


def test_pipeline_sends_coke_to_sellable_with_abc_image_and_order_signal():
    abc = [{"SKU": "MRK.00506", "Product Name": "Coca-Cola 1 L", "Barcodes": "05000112664492", "ABC": "A", "% Orders": "3.79%", "% Stops": "0.55%", "On-Hand Qty": 180, "Product Image URL": "https://example.com/coke.jpg", "Location": "U10-02-D02", "Storage Type": "AMBIENT"}]
    catalog = [{"sku": "MRK.00506", "product_name": "Coca-Cola 1 L", "barcode": "05000112664492", "storage_type": "AMBIENT", "width_cm": 9, "height_cm": 28, "depth_cm": 9, "weight_kg": 1, "case_pack_qty": 12}]
    result = merge_catalog_abc(abc, catalog)
    assert result["summary"]["sellable_products"] == 1
    p = result["sellable_products"][0]
    assert p["sku"] == "MRK.00506"
    assert p["image_url"] == "https://example.com/coke.jpg"
    assert p["visual_source"] == "abc_upload"
    assert p["order_share_pct"] == 3.79
    assert p["stop_share_pct"] == 0.55
    assert p["current_location"] == "U10-02-D02"
    assert p["width_cm"] == 9


def test_pipeline_bakery_review_without_la_lorraine_brand():
    abc = [{"SKU": "BRD.001", "Product Name": "Ramazan Pidesi 350 g", "Barcodes": "123", "ABC": "A", "% Orders": "4.0%", "Product Image URL": "https://example.com/pide.jpg", "Storage Type": "AMBIENT"}]
    catalog = [{"sku": "BRD.001", "product_name": "Ramazan Pidesi 350 g", "barcode": "123", "storage_type": "FROZEN", "width_cm": 30, "height_cm": 4, "depth_cm": 30, "weight_kg": 0.35}]
    result = merge_catalog_abc(abc, catalog)
    assert result["summary"]["sellable_products"] == 0
    assert result["summary"]["review_products"] == 1
    assert result["review_products"][0]["planogram_class"] == "BAKERY_FLOW_REVIEW"


def test_pipeline_keeps_catalog_storage_when_abc_conflicts():
    abc = [{"SKU": "ICE.001", "Product Name": "Algida Magnum Classic", "Barcodes": "999", "ABC": "A", "% Orders": "5.0%", "Product Image URL": "https://example.com/magnum.jpg", "Storage Type": "AMBIENT"}]
    catalog = [{"sku": "ICE.001", "product_name": "Algida Magnum Classic", "barcode": "999", "storage_type": "FROZEN", "width_cm": 8, "height_cm": 12, "depth_cm": 3, "weight_kg": 0.1}]
    result = merge_catalog_abc(abc, catalog)
    assert result["summary"]["storage_conflicts"] == 1
    assert result["sellable_products"][0]["storage_type"] == "FROZEN"
    assert result["sellable_products"][0]["planogram_class"] == "ICE_CREAM_PRODUCT"


if __name__ == "__main__":
    test_pipeline_excludes_shopping_bag_even_high_orders()
    test_pipeline_sends_coke_to_sellable_with_abc_image_and_order_signal()
    test_pipeline_bakery_review_without_la_lorraine_brand()
    test_pipeline_keeps_catalog_storage_when_abc_conflicts()
    print("✅ V1.9.2 classification pipeline integration tests passed")
