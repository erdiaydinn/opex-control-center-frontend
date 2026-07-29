import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.planogram_input_guard import guard_planogram_input

products = [
    {"SKU": "MRK.07018", "Product Name": "Shopping Bag", "% Orders": "98.38%"},
    {"SKU": "MRK.00506", "Product Name": "Coca-Cola 1 L", "% Orders": "3.79%"},
    {"SKU": "BRD.001", "Product Name": "Ramazan Pidesi 350 g"},
]

r = guard_planogram_input(products)

assert len(r["sellable_products"]) == 1
assert r["sellable_products"][0]["SKU"] == "MRK.00506"
assert len(r["excluded_products"]) == 2
assert r["excluded_report"]["total_excluded"] == 2

print("✅ V1.9.5 input guard smoke passed")
