import os
from datetime import date,timedelta
os.environ['DOCKOS_PERSISTENCE']='postgres'; os.environ['DOCKOS_TENANT_KEY']='ys_tr'; os.environ['DOCKOS_DC_NAMES']='Ankara DC'; os.environ['DOCKOS_PO_SOURCE']='LOCAL'; os.environ['DOCKOS_NOTIFICATION_AUTOMATION']='false'

def main():
 from app.modules.dockos import service
 from app.modules.dockos.persistence import refresh_state
 from app.modules.dockos.schemas import CreateReservationRequest,AdminReservationEditRequest,PurchaseOrderBulkImportRequest,PurchaseOrderImportRow
 d=str(date.today()+timedelta(days=7))
 with service.STATE_LOCK:
  service.MOCK_RESERVATIONS.clear(); service.MOCK_NOTIFICATION_OUTBOX.clear(); service.MOCK_AUDIT_LOG.clear(); service.MOCK_SUPPLIER_CAPACITY.clear(); service.MOCK_SUPPLIER_DAILY_LIMITS.clear(); service.MOCK_PURCHASE_ORDERS.clear()
  service.MOCK_SUPPLIER_ACCESS[:]=[{'email':'flow@example.org','supplier_names':['Flow Supplier'],'warehouse_names':['Ankara DC'],'all_warehouses':False,'active':True,'locale':'tr'}]; service._persist()
 rows=[PurchaseOrderImportRow(warehouse_name='Ankara DC',po_order_id='PO-FLOW-001',supplier_name='Flow Supplier',promised_date=d,order_status='confirmed',total_sku=10)]
 imported=service.import_purchase_orders(PurchaseOrderBulkImportRequest(rows=rows,replace_existing=False),'erdi.aydin@yemeksepeti.com','admin'); assert imported['imported']==1,imported
 refresh_state(); assert any(p['po_number']=='PO-FLOW-001' for p in service.MOCK_PURCHASE_ORDERS)
 payload=CreateReservationRequest(po_number='PO-FLOW-001',po_numbers=['PO-FLOW-001'],supplier_name='Flow Supplier',warehouse_name='Ankara DC',shipment_mode='SEVKIYAT',pallet_count=2,sku_count=10,slot_date=d,selected_slot='10:00 - 11:00',shipment_details='postgres flow acceptance',vehicle_plate='34 FLW 001')
 created=service.create_reservation(payload,'flow@example.org','supplier'); assert created['status']=='APPROVED',created; no=created['reservation_no']
 refresh_state(); events={x['event'] for x in service.MOCK_NOTIFICATION_OUTBOX if x.get('reservation_no')==no}; assert {'CREATED','REMINDER_48','FINAL_24'}<=events,events
 edited=service.edit_reservation_admin(no,AdminReservationEditRequest(slot_date=d,selected_slot='11:00 - 12:00',pallet_count=2,sku_count=10,vehicle_plate='34 FLW 002',vehicle_type='TIR',shipment_details='postgres edited flow',edit_reason='rampa planı değişti'),'erdi.aydin@yemeksepeti.com','admin'); assert edited['status']=='UPDATED',edited
 cancelled=service.cancel_reservation(no,True,'erdi.aydin@yemeksepeti.com','admin','operasyon iptali'); assert cancelled['status']=='CANCELLED',cancelled
 refresh_state(); record=next(r for r in service.MOCK_RESERVATIONS if r['reservation_no']==no); assert record['status']=='CANCELLED'; assert next(p for p in service.MOCK_PURCHASE_ORDERS if p['po_number']=='PO-FLOW-001')['status']=='OPEN'
 events={x['event'] for x in service.MOCK_NOTIFICATION_OUTBOX if x.get('reservation_no')==no}; assert 'EDITED' in events and 'CANCELLED' in events,events
 kpis=service.get_kpis('erdi.aydin@yemeksepeti.com','admin',supplier_name='Flow Supplier'); assert kpis, kpis
 audit=service.get_audit_log(200,'erdi.aydin@yemeksepeti.com','admin'); actions={x['action'] for x in audit}; assert {'IMPORT','CREATE','EDIT','CANCEL'}<=actions,actions
 print('POSTGRES_END_TO_END_TRUTH=PASS')
if __name__=='__main__': main()
