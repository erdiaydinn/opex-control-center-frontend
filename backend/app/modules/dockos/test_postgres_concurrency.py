import os
from datetime import date,timedelta
from concurrent.futures import ProcessPoolExecutor
os.environ['DOCKOS_PERSISTENCE']='postgres'
os.environ['DOCKOS_TENANT_KEY']='ys_tr'
os.environ['DOCKOS_DC_NAMES']='Ankara DC'
os.environ['DOCKOS_PO_SOURCE']='LOCAL'
os.environ['DOCKOS_NOTIFICATION_AUTOMATION']='false'

def attempt(x):
    n,d=x
    from app.modules.dockos.schemas import CreateReservationRequest
    from app.modules.dockos.service import create_reservation
    p=CreateReservationRequest(po_number=n,po_numbers=[n],supplier_name='Load Supplier',warehouse_name='Ankara DC',shipment_mode='SEVKIYAT',pallet_count=1,sku_count=1,slot_date=d,selected_slot='08:00 - 09:00',shipment_details='parallel acceptance',vehicle_plate='34 TST 001')
    return create_reservation(p,'load@example.org','supplier')['status']

def main():
    from app.modules.dockos import service
    d=str(date.today()+timedelta(days=7))
    with service.STATE_LOCK:
        service.MOCK_RESERVATIONS.clear(); service.MOCK_NOTIFICATION_OUTBOX.clear(); service.MOCK_SUPPLIER_CAPACITY.clear(); service.MOCK_SUPPLIER_DAILY_LIMITS.clear()
        service.MOCK_SUPPLIER_ACCESS[:]=[{'email':'load@example.org','supplier_names':['Load Supplier'],'warehouse_names':['Ankara DC'],'all_warehouses':False,'active':True,'locale':'tr'}]
        service.MOCK_PURCHASE_ORDERS[:]=[{'po_number':f'PO-TST-{i:03d}','supplier_name':'Load Supplier','warehouse_name':'Ankara DC','delivery_date':d,'status':'OPEN','sku_count':10,'source':'TEST'} for i in range(12)]
        s=next(r for r in service.MOCK_SLOT_CAPACITY if r['warehouse_name']=='Ankara DC' and r['date']==d and r['slot']=='08:00 - 09:00')
        s.update({'max_pallet':5,'max_sku':500,'remaining_pallet':5,'remaining_sku':500}); service._persist()
    with ProcessPoolExecutor(max_workers=8) as p:
        out=list(p.map(attempt,[(f'PO-TST-{i:03d}',d) for i in range(12)]))
    assert out.count('APPROVED')==5,out
    assert out.count('FAILED')==7,out
    print('POSTGRES_CONCURRENCY_ACCEPTANCE=PASS approved=5 rejected=7')
if __name__=='__main__': main()
