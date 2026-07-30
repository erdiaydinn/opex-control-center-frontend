
from engine import run_engine, generate_default_layout

products = []
for i in range(180):
    products.append({
        'sku': f'AMB-{i}',
        'product_name': f'Ambient Test Product {i}',
        'brand': f'Brand {i%12}',
        'category_l1': 'Snacks',
        'category_l2': 'Test',
        'storage_type': 'AMBIENT',
        'width_cm': 8,
        'height_cm': 18,
        'depth_cm': 6,
        'sales_qty_7d': 10 + i % 120,
    })
for i in range(60):
    products.append({
        'sku': f'CHL-{i}',
        'product_name': f'Chilled Yogurt Test {i}',
        'brand': f'Dairy {i%8}',
        'category_l1': 'Dairy / Chilled / Eggs',
        'category_l2': 'Yogurt',
        'storage_type': 'CHILLED',
        'width_cm': 9,
        'height_cm': 12,
        'depth_cm': 8,
        'sales_qty_7d': 20 + i,
    })
for i in range(25):
    products.append({
        'sku': f'FRZ-{i}',
        'product_name': f'Algida Ice Cream Test {i}',
        'brand': 'Algida',
        'category_l1': 'Frozen',
        'category_l2': 'Ice Cream',
        'storage_type': 'FROZEN',
        'width_cm': 8,
        'height_cm': 14,
        'depth_cm': 6,
        'sales_qty_7d': 15 + i,
    })

res = run_engine(products, generate_default_layout())
plan = res['planogram']
placed_by_aisle = {}
for a in plan.get('aisles', []):
    cnt = 0
    for m in a.get('modules', []):
        for s in m.get('shelves', []):
            cnt += len(s.get('products', []))
    if cnt:
        placed_by_aisle[a.get('aisle_id')] = cnt
print('summary:', res['summary'])
print('placed_by_aisle:', placed_by_aisle)
print('patches:', res.get('engine_patches'))
print('fixture_capacity_summary:', res.get('fixture_capacity_summary'))
