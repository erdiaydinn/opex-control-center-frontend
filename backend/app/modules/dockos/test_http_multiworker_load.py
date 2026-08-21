import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

os.environ['DOCKOS_PERSISTENCE'] = 'postgres'
os.environ['DOCKOS_TENANT_KEY'] = 'ys_tr'
os.environ['DOCKOS_DC_NAMES'] = 'Ankara DC'
os.environ['DOCKOS_PO_SOURCE'] = 'LOCAL'
os.environ['DOCKOS_NOTIFICATION_AUTOMATION'] = 'false'

SLOT_DATE = str(date.today() + timedelta(days=10))
SLOT = '10:00 - 11:00'
TOTAL = 120
CAPACITY = 20


def prepare():
    from . import service
    with service.STATE_LOCK:
        service.MOCK_RESERVATIONS.clear()
        service.MOCK_NOTIFICATION_OUTBOX.clear()
        service.MOCK_AUDIT_LOG.clear()
        service.MOCK_SUPPLIER_CAPACITY.clear()
        service.MOCK_SUPPLIER_DAILY_LIMITS.clear()
        service.MOCK_SUPPLIER_ACCESS[:] = [{
            'email':'load@example.org','supplier_names':['Load Supplier'],
            'warehouse_names':['Ankara DC'],'all_warehouses':False,'active':True,'locale':'tr'
        }]
        service.MOCK_PURCHASE_ORDERS[:] = [
            {'po_number':f'PO-LOAD-{i:03d}','po_order_id':f'PO-LOAD-{i:03d}','supplier_name':'Load Supplier',
             'warehouse_name':'Ankara DC','delivery_date':SLOT_DATE,'promised_date':SLOT_DATE,
             'status':'OPEN','order_status':'OPEN','sku_count':1,'total_sku':1,'source':'TEST'}
            for i in range(TOTAL)
        ]
        row = next(r for r in service.MOCK_SLOT_CAPACITY if r['warehouse_name']=='Ankara DC' and r['date']==SLOT_DATE and r['slot']==SLOT)
        row.update({'max_pallet':CAPACITY,'max_sku':500,'remaining_pallet':CAPACITY,'remaining_sku':500,'blocked':False})
        service._persist()
    print(f'HTTP_LOAD_PREPARED date={SLOT_DATE} total={TOTAL} capacity={CAPACITY}')


def _one(index):
    payload = {
        'po_number':f'PO-LOAD-{index:03d}','po_numbers':[f'PO-LOAD-{index:03d}'],
        'supplier_name':'Load Supplier','warehouse_name':'Ankara DC','shipment_mode':'SEVKIYAT',
        'pallet_count':1,'sku_count':1,'slot_date':SLOT_DATE,'selected_slot':SLOT,
        'shipment_details':'multi-worker HTTP acceptance','vehicle_plate':f'34 LOAD {index:03d}'
    }
    request = urllib.request.Request(
        'http://127.0.0.1:8090/api/dockos/reservations',
        data=json.dumps(payload).encode('utf-8'),method='POST',
        headers={'Content-Type':'application/json','X-OPEX-User':'load@example.org','X-OPEX-Role':'supplier'}
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            body = json.loads(response.read().decode('utf-8'))
            status = str(body.get('status') or f'HTTP_{response.status}')
    except urllib.error.HTTPError as error:
        status = f'HTTP_{error.code}'
    return status,(time.perf_counter()-started)*1000.0


def run():
    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(_one,range(TOTAL)))
    statuses = [status for status,_ in results]
    latencies = sorted(latency for _,latency in results)
    approved = statuses.count('APPROVED')
    failed = TOTAL-approved
    p50 = statistics.median(latencies)
    p95 = latencies[max(0,int(len(latencies)*0.95)-1)]
    p99 = latencies[max(0,int(len(latencies)*0.99)-1)]
    assert approved == CAPACITY,(approved,failed,statuses)
    print(f'HTTP_MULTIWORKER_LOAD=PASS approved={approved} rejected={failed} p50_ms={p50:.1f} p95_ms={p95:.1f} p99_ms={p99:.1f}')


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'prepare','run'}:
        raise SystemExit('usage: python -m app.modules.dockos.test_http_multiworker_load prepare|run')
    prepare() if sys.argv[1]=='prepare' else run()
