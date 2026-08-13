from __future__ import annotations

import os

from .identity import current_identity
from .persistence import STATE_LOCK, persistence_mode, refresh_state
from .tenant_db import db_status
from .bigquery_po import fetch_live_purchase_orders


def production():
    return os.getenv('DOCKOS_ENV','development').lower() == 'production'


def install_service_security(service):
    original = service.is_admin
    def verified_is_admin(user_email=None, user_role=None):
        if not production():
            return original(user_email, user_role)
        identity = current_identity()
        if identity is None:
            return False
        if (user_email or '').strip().lower() != identity.email:
            return False
        return identity.role in {'dockos_admin','opex_admin','admin','superadmin'}
    service.is_admin = verified_is_admin


def mutate(fn):
    with STATE_LOCK:
        return fn()


def sync_bigquery_purchase_orders(service, supplier_name=None, warehouse_name=None):
    result = fetch_live_purchase_orders(supplier_name, warehouse_name)
    if result.get('source') != 'BIGQUERY':
        if production():
            raise ValueError('Canlı BigQuery PO kaynağına ulaşılamadı; production fallback kapalı.')
        return result
    rows = result.get('rows') or []
    def apply():
        by_number = {str(row.get('po_number')): row for row in service.MOCK_PURCHASE_ORDERS}
        for incoming in rows:
            normalized = dict(incoming)
            number = str(normalized.get('po_number') or normalized.get('po_order_id') or '').strip()
            if not number:
                continue
            normalized['po_number'] = number
            normalized['po_order_id'] = number
            normalized['source'] = 'BIGQUERY'
            normalized['source_identity'] = f"fulfillment-dwh-production:YS_TR:{number}"
            existing = by_number.get(number)
            if existing:
                protected_status = existing.get('status') if existing.get('status') in {'RESERVED','CLOSED','CANCELLED'} else None
                existing.update(normalized)
                if protected_status:
                    existing['status'] = protected_status
            else:
                service.MOCK_PURCHASE_ORDERS.append(normalized)
                by_number[number] = normalized
        service.LIVE_PO_CACHE[:] = rows
        service._persist()
    mutate(apply)
    allowed = rows
    identity = current_identity()
    if identity and not service.is_admin(identity.email, identity.role):
        suppliers = set(service.allowed_suppliers(identity.email, identity.role))
        dcs = set(service.allowed_warehouses(identity.email, identity.role))
        allowed = [row for row in rows if row.get('supplier_name') in suppliers and row.get('warehouse_name') in dcs]
    return {'source':'BIGQUERY','message':result.get('message'),'count':len(allowed),'rows':allowed}


def readiness_checks(service):
    status = db_status() if persistence_mode() == 'postgres' else {'ok':False,'migrations':[],'error':'PostgreSQL kapalı'}
    smtp_host = os.getenv('DOCKOS_SMTP_HOST','').strip()
    smtp_from = os.getenv('DOCKOS_SMTP_FROM','').strip()
    checks = [
        {'key':'environment','ok':production(),'detail':'DOCKOS_ENV=production'},
        {'key':'persistence','ok':persistence_mode()=='postgres','detail':'PostgreSQL production source-of-truth'},
        {'key':'database','ok':bool(status.get('ok')),'detail':status},
        {'key':'multi_worker','ok':os.getenv('DOCKOS_SINGLE_WORKER','false').lower()=='false','detail':'Cross-process DB transaction lock etkin'},
        {'key':'oidc','ok':all(os.getenv(k,'').strip() for k in ['DOCKOS_OIDC_ISSUER','DOCKOS_OIDC_AUDIENCE','DOCKOS_OIDC_JWKS_URL']),'detail':'OIDC issuer/audience/JWKS zorunlu'},
        {'key':'gateway','ok':os.getenv('DOCKOS_GATEWAY_TRUST_MODE','hmac').lower()=='hmac' and len(os.getenv('DOCKOS_GATEWAY_SECRET',''))>=32,'detail':'HMAC signed gateway trust'},
        {'key':'po_source','ok':os.getenv('DOCKOS_PO_SOURCE','').upper()=='BIGQUERY','detail':'Production PO fallback kapalı'},
        {'key':'bigquery_identity','ok':bool(os.getenv('DOCKOS_BIGQUERY_IDENTITY','').strip()),'detail':'Workload/service identity label configured'},
        {'key':'smtp','ok':bool(smtp_host and smtp_from and 'example.com' not in smtp_host and 'example.com' not in smtp_from),'detail':'Real SMTP configured'},
        {'key':'smtp_acceptance','ok':os.getenv('DOCKOS_SMTP_ACCEPTED','false').lower()=='true','detail':'Real delivery acceptance completed'},
        {'key':'backup_restore','ok':os.getenv('DOCKOS_BACKUP_RESTORE_ACCEPTED','false').lower()=='true','detail':'PostgreSQL backup/restore drill completed'},
        {'key':'dc_scope','ok':bool(os.getenv('DOCKOS_DC_NAMES','').strip()),'detail':'Production DC allow-list configured'},
        {'key':'supplier_access','ok':any(row.get('active',True) and row.get('supplier_names') for row in service.MOCK_SUPPLIER_ACCESS),'detail':'At least one active supplier access mapping'},
    ]
    return checks
