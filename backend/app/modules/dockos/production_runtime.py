from __future__ import annotations

import os
from datetime import datetime, timezone

from .identity import current_identity
from .observability import record_bigquery_sync
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
        record_bigquery_sync(False)
        if production():
            raise ValueError('Canlı BigQuery PO kaynağına ulaşılamadı; production fallback kapalı.')
        return result
    record_bigquery_sync(True)
    rows = result.get('rows') or []
    synced_at = datetime.now(timezone.utc).isoformat()
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
            normalized['source_synced_at'] = synced_at
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
    return {'source':'BIGQUERY','message':result.get('message'),'count':len(allowed),'rows':allowed,'synced_at':synced_at}


def _accepted(name):
    return os.getenv(name, 'false').lower() == 'true'


def readiness_checks(service):
    status = db_status() if persistence_mode() == 'postgres' else {'ok':False,'migrations':[],'error':'PostgreSQL kapalı'}
    migrations = set(status.get('migrations') or [])
    smtp_host = os.getenv('DOCKOS_SMTP_HOST','').strip()
    smtp_from = os.getenv('DOCKOS_SMTP_FROM','').strip()
    checks = [
        {'key':'environment','ok':production(),'detail':'DOCKOS_ENV=production'},
        {'key':'persistence','ok':persistence_mode()=='postgres','detail':'PostgreSQL production source-of-truth'},
        {'key':'database','ok':bool(status.get('ok')) and {'001_dockos_postgres','002_runtime_hardening'} <= migrations,'detail':status},
        {'key':'multi_worker_config','ok':os.getenv('DOCKOS_SINGLE_WORKER','false').lower()=='false','detail':'Cross-process DB transaction lock enabled'},
        {'key':'oidc_config','ok':all(os.getenv(k,'').strip() for k in ['DOCKOS_OIDC_ISSUER','DOCKOS_OIDC_AUDIENCE','DOCKOS_OIDC_JWKS_URL']),'detail':'OIDC issuer/audience/JWKS configured'},
        {'key':'oidc_acceptance','ok':_accepted('DOCKOS_OIDC_ACCEPTED'),'detail':'Real corporate login acceptance completed'},
        {'key':'gateway_config','ok':os.getenv('DOCKOS_GATEWAY_TRUST_MODE','hmac').lower()=='hmac' and len(os.getenv('DOCKOS_GATEWAY_SECRET',''))>=32,'detail':'HMAC signed gateway trust configured'},
        {'key':'gateway_acceptance','ok':_accepted('DOCKOS_GATEWAY_ACCEPTED'),'detail':'Signed trust, rotation and replay acceptance completed'},
        {'key':'po_source','ok':os.getenv('DOCKOS_PO_SOURCE','').upper()=='BIGQUERY','detail':'Production PO source is BIGQUERY only'},
        {'key':'bigquery_identity','ok':bool(os.getenv('DOCKOS_BIGQUERY_IDENTITY','').strip()),'detail':'Production workload/service identity configured'},
        {'key':'bigquery_acceptance','ok':_accepted('DOCKOS_BIGQUERY_ACCEPTED'),'detail':'Real BigQuery IAM/query/PO identity acceptance completed'},
        {'key':'smtp','ok':bool(smtp_host and smtp_from and 'example.com' not in smtp_host and 'example.com' not in smtp_from),'detail':'Real SMTP configured'},
        {'key':'smtp_acceptance','ok':_accepted('DOCKOS_SMTP_ACCEPTED'),'detail':'Real delivery acceptance completed'},
        {'key':'multi_worker_acceptance','ok':_accepted('DOCKOS_MULTIWORKER_ACCEPTED'),'detail':'Real multi-worker deployment acceptance completed'},
        {'key':'load_acceptance','ok':_accepted('DOCKOS_LOAD_ACCEPTED'),'detail':'Horizontal load/concurrency acceptance completed'},
        {'key':'backup_restore','ok':_accepted('DOCKOS_BACKUP_RESTORE_ACCEPTED'),'detail':'Production-like PostgreSQL backup/restore rehearsal completed'},
        {'key':'resilience_acceptance','ok':_accepted('DOCKOS_RESILIENCE_ACCEPTED'),'detail':'Network interruption, DB restart, BQ outage and retry acceptance completed'},
        {'key':'outbox_acceptance','ok':_accepted('DOCKOS_OUTBOX_ACCEPTED'),'detail':'Retry/dead-letter/duplicate notification acceptance completed'},
        {'key':'observability_acceptance','ok':_accepted('DOCKOS_OBSERVABILITY_ACCEPTED'),'detail':'SLO metrics scrape/alert acceptance completed'},
        {'key':'pilot_acceptance','ok':_accepted('DOCKOS_PILOT_ACCEPTED'),'detail':'Supplier/DC operational pilot checklist completed'},
        {'key':'dc_scope','ok':bool(os.getenv('DOCKOS_DC_NAMES','').strip()),'detail':'Production DC allow-list configured'},
        {'key':'supplier_access','ok':any(row.get('active',True) and row.get('supplier_names') for row in service.MOCK_SUPPLIER_ACCESS),'detail':'At least one active supplier access mapping'},
    ]
    return checks
