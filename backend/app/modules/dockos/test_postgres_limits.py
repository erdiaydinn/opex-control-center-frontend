import os
from datetime import date,timedelta
from concurrent.futures import ProcessPoolExecutor
os.environ['DOCKOS_PERSISTENCE']='postgres'; os.environ['DOCKOS_TENANT_KEY']='ys_tr'; os.environ['DOCKOS_DC_NAMES']='Ankara DC'; os.environ['DOCKOS_PO_SOURCE']='LOCAL'; os.environ['DOCKOS_NOTIFICATION_AUTOMATION']='false'

def attempt(x):
 n,d,i=x
 from app.modules.dockos.schemas import CreateReservationRequest
 from app.modules.dockos.service import create_reservation
 p=CreateReservationRequest(po_number=n,po_numbers=[n],supplier_name='Limit Supplier',warehouse_name='Ankara DC',shipment_mode='SEVKIYAT',pallet_count=1,sku_count=1,slot_date=d,selected_slot='09:00 - 10:00',shipment_details='parallel acceptance',vehicle_plate=f'34 LIM {i:03d}')
 return create_reservation(p,'limit@example.org','supplier')['status']

def prepare(d,daily):
 from app.modules.dockos import service
 with service.STATE_LOCK:
  service.MOCK_RESERVATIONS.clear(); service.MOCK_NOTIFICATION_OUTBOX.clear(); service.MOCK_SUPPLIER_CAPACITY.clear(); service.MOCK_SUPPLIER_DAILY_LIMITS.clear()
  service.MOCK_SUPPLIER_ACCESS[:]=[{'email':'limit@example.org','supplier_names':['Limit Supplier'],'warehouse_names':['Ankara DC'],'all_warehouses':False,'active':True,'locale':'tr'}]
  service.MOCK_PURCHASE_ORDERS[:]=[{'po_number':f'PO-LIM-{i:03d}','supplier_name':'Limit Supplier','warehouse_name':'Ankara DC','delivery_date':d,'status':'OPEN','sku_count':10,'source':'TEST'} for i in range(12)]
  s=next(r for r in service.MOCK_SLOT_CAPACITY if r['warehouse_name']=='Ankara DC' and r['date']==d and r['slot']=='09:00 - 10:00'); s.update({'max_pallet':40,'max_sku':500,'remaining_pallet':40,'remaining_sku':500})
  if daily: service.MOCK_SUPPLIER_DAILY_LIMITS.append({'warehouse_name':'Ankara DC','supplier_name':'Limit Supplier','date':d,'max_pallet':daily})
  service._persist()

def run(jobs):
 with ProcessPoolExecutor(max_workers=8) as p: return list(p.map(attempt,jobs))

def main():
 d=str(date.today()+timedelta(days=8)); prepare(d,3); out=run([(f'PO-LIM-{i:03d}',d,i) for i in range(8)]); assert out.count('APPROVED')==3,out; assert out.count('FAILED')==5,out
 prepare(d,None); out=run([('PO-LIM-000',d,i) for i in range(8)]); assert out.count('APPROVED')==1,out; assert out.count('FAILED')==7,out
 print('POSTGRES_PARALLEL_LIMITS=PASS')
 from .test_postgres_contracts import main as contract_main
 contract_main()
if __name__=='__main__': main()
