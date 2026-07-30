import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.product_classification_rules import classify_planogram_product, split_products_for_planogram


def test_shopping_bag_excluded():
    p = {
        "SKU": "MRK.07018",
        "Product Name": "Shopping Bag",
        "Category L1": "Home / Pet",
        "Category L2": "Disposables",
        "% Orders": "98.38%",
    }
    r = classify_planogram_product(p)
    assert r["exclude_from_planogram"] is True
    assert r["planogram_class"] == "EXCLUDED_OPERATIONAL_SUPPLY"


def test_everyday_equipment_excluded():
    p = {
        "SKU": "EQP.001",
        "Product Name": "Everyday Coffee Machine",
        "Category L1": "Equipment",
        "% Orders": "20%",
    }
    r = classify_planogram_product(p)
    assert r["exclude_from_planogram"] is True
    assert r["planogram_class"] == "EXCLUDED_EQUIPMENT"


def test_la_lorraine_bakery_flow():
    p = {
        "SKU": "YS0215",
        "Product Name": "La Lorraine French Baguette 110 g",
        "Category L1": "Ready To Consume",
        "Category L2": "Food",
    }
    r = classify_planogram_product(p)
    assert r["exclude_from_planogram"] is True
    assert r["planogram_class"] == "BAKERY_FLOW_REVIEW"


def test_ramazan_pidesi_without_la_lorraine_caught():
    p = {
        "SKU": "BRD.001",
        "Product Name": "Ramazan Pidesi 350 g",
        "Category L1": "Ready To Consume",
        "Category L2": "Bakery",
    }
    r = classify_planogram_product(p)
    assert r["exclude_from_planogram"] is True
    assert r["planogram_class"] == "BAKERY_FLOW_REVIEW"


def test_algida_not_excluded_but_special_fixture():
    p = {
        "SKU": "ALG.001",
        "Product Name": "Algida Magnum Classic",
        "Category L1": "Frozen",
        "Category L2": "Ice Cream",
    }
    r = classify_planogram_product(p)
    assert r["exclude_from_planogram"] is False
    assert r["planogram_class"] == "ICE_CREAM_PRODUCT"
    assert r["required_fixture_class"] == "ICE_CREAM"


def test_split_products():
    products = [
        {"SKU": "MRK.07018", "Product Name": "Shopping Bag"},
        {"SKU": "MRK.00506", "Product Name": "Coca-Cola 1 L"},
        {"SKU": "BRD.001", "Product Name": "Ramazan Pidesi 350 g"},
    ]
    r = split_products_for_planogram(products)
    assert r["summary"]["input_products"] == 3
    assert r["summary"]["sellable_products"] == 1
    assert r["summary"]["excluded_products"] == 2
    assert r["summary"]["review_products"] == 1


if __name__ == "__main__":
    test_shopping_bag_excluded()
    test_everyday_equipment_excluded()
    test_la_lorraine_bakery_flow()
    test_ramazan_pidesi_without_la_lorraine_caught()
    test_algida_not_excluded_but_special_fixture()
    test_split_products()
    print("✅ V1.9.1 product classification guard tests passed")
