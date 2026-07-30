
from fulya_store_dna_loader import build_fulya_layout
from engine import generate_planogram

layout = build_fulya_layout()
print('FULYA aisles:', len(layout['aisles']))
print('FULYA capacity:', layout['fixture_capacity_summary'])

products = [
    {'sku':'T1','product_name':'Eti Burcak 100 g','brand':'Eti','storage_type':'AMBIENT','width_cm':8,'height_cm':15,'depth_cm':5,'sales_qty_7d':100},
    {'sku':'T2','product_name':'Yoğurt 1 kg','brand':'Sütaş','storage_type':'CHILLED','width_cm':10,'height_cm':12,'depth_cm':10,'sales_qty_7d':100},
    {'sku':'T3','product_name':'Algida Magnum','brand':'Algida','storage_type':'FROZEN','width_cm':9,'height_cm':15,'depth_cm':4,'sales_qty_7d':100},
]
res = generate_planogram(products, {'store_code':'FULYA','store_name':'Fulya (İstanbul)'})
print(res['engine_version'])
print(res['summary'])
print(res['v2_diagnostics'])
assert res['store_dna']['fulya_store_dna_v1'] is True
assert res['summary']['module_count'] >= 270
print('SMOKE OK')
