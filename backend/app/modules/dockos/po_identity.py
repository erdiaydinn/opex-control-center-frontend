from __future__ import annotations
import os
from .runtime_db import enabled as postgres_enabled
from .tenant_db import load_kv,save_kv,write_conn

def source_identity(po_number):
    return f"{os.getenv('DOCKOS_BQ_PROJECT','fulfillment-dwh-production')}:YS_TR:{po_number}"

def persist_bigquery_rows(rows):
    if not postgres_enabled() or not rows: return
    with write_conn() as conn:
        values=load_kv(conn); current=list(values.get('state:purchase_orders') or [])
        by_number={str(r.get('po_number') or r.get('po_order_id') or ''):r for r in current}
        for incoming in rows:
            number=str(incoming.get('po_number') or incoming.get('po_order_id') or '').strip()
            if not number: continue
            row=dict(incoming); row['po_number']=number; row['po_order_id']=number; row['source']='BIGQUERY'; row['source_identity']=source_identity(number)
            existing=by_number.get(number)
            if existing:
                protected=existing.get('status') if existing.get('status') in {'RESERVED','CLOSED','CANCELLED'} else None
                existing.update(row)
                if protected: existing['status']=protected
            else:
                current.append(row); by_number[number]=row
        save_kv(conn,{'state:purchase_orders':current})
