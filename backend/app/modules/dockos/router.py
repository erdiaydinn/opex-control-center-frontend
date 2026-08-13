import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from .schemas import *
from .service import *


def require_production_gateway(request: Request):
    """Reject spoofable identity headers when the API is exposed publicly.

    In production the reverse proxy/gateway must inject X-DockOS-Gateway after
    authenticating the OPEX session. Health/readiness remain probeable.
    """
    if os.getenv("DOCKOS_ENV", "development").lower() != "production":
        return
    if request.url.path.endswith("/health") or request.url.path.endswith("/readiness"):
        return
    expected = os.getenv("DOCKOS_GATEWAY_SECRET", "")
    provided = request.headers.get("X-DockOS-Gateway", "")
    if len(expected) < 32 or expected.startswith("CHANGE_ME") or not secrets.compare_digest(provided, expected):
        raise HTTPException(401, "DockOS production gateway doğrulaması başarısız.")


router = APIRouter(prefix="/dockos", tags=["DockOS"], dependencies=[Depends(require_production_gateway)])


@router.on_event("startup")
def dockos_startup():
    start_notification_worker()


@router.on_event("shutdown")
def dockos_shutdown():
    stop_notification_worker()


def guard(fn):
    try:
        return fn()
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/health")
def health():
    return {"status": "ok", "module": "dockos", "release": "RC7.5-internal-test", "notifications": "automatic"}


@router.get("/readiness")
def readiness():
    production = os.getenv("DOCKOS_ENV", "development").lower() == "production"
    state_file = os.getenv("DOCKOS_STATE_FILE", "")
    gateway_secret = os.getenv("DOCKOS_GATEWAY_SECRET", "")
    smtp_host = os.getenv("DOCKOS_SMTP_HOST", "").strip()
    smtp_from = os.getenv("DOCKOS_SMTP_FROM", "").strip()
    recipients = os.getenv("DOCKOS_DC_EMAILS", "").strip()
    backup_dir = os.getenv("DOCKOS_BACKUP_DIR", "").strip()
    checks = [
        {"key": "environment", "ok": production, "detail": "DOCKOS_ENV=production"},
        {"key": "gateway", "ok": len(gateway_secret) >= 32 and not gateway_secret.startswith("CHANGE_ME"), "detail": "En az 32 karakter gerçek gateway secret"},
        {"key": "identity_headers", "ok": os.getenv("DOCKOS_TRUST_ROLE_HEADER", "false").lower() == "false", "detail": "Rol header'ı doğrudan güvenilir olmamalı"},
        {"key": "po_source", "ok": os.getenv("DOCKOS_PO_SOURCE", "AUTO").upper() == "BIGQUERY", "detail": "Canlı PO kaynağı BIGQUERY"},
        {"key": "smtp", "ok": bool(smtp_host and smtp_from and "example.com" not in smtp_host and "example.com" not in smtp_from), "detail": "Gerçek SMTP host ve gönderen adresi"},
        {"key": "recipients", "ok": bool(recipients and "example.com" not in recipients), "detail": "Gerçek merkez depo bildirim alıcıları"},
        {"key": "supplier_access", "ok": any(row.get("active", True) and row.get("supplier_names") for row in MOCK_SUPPLIER_ACCESS), "detail": "En az bir aktif e-posta–tedarikçi erişim eşleşmesi"},
        {"key": "persistent_state", "ok": bool(state_file and os.path.isabs(state_file)), "detail": "Kalıcı disk üzerinde mutlak DOCKOS_STATE_FILE yolu"},
        {"key": "single_worker", "ok": os.getenv("DOCKOS_SINGLE_WORKER", "false").lower() == "true", "detail": "JSON pilot deposu için tek backend worker"},
        {"key": "backup", "ok": bool(backup_dir and os.path.isabs(backup_dir)), "detail": "Mutlak harici yedek klasörü"},
    ]
    return {"ready": all(item["ok"] for item in checks), "release": "RC7.5-internal-test", "checks": checks}


@router.get("/my-suppliers")
def my_suppliers(x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return get_my_suppliers(x_opex_user, x_opex_role)


@router.get("/suppliers")
def suppliers(x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return get_suppliers(x_opex_user, x_opex_role)


@router.get("/warehouses")
def warehouses(supplier_name: str | None = None, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: get_warehouses(supplier_name, x_opex_user, x_opex_role))


@router.get("/live-purchase-orders")
def live_pos(supplier_name: str | None = None, warehouse_name: str | None = None, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: get_live_purchase_orders(supplier_name, warehouse_name, x_opex_user, x_opex_role))


@router.post("/purchase-orders/import")
def purchase_order_import(payload: PurchaseOrderBulkImportRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: import_purchase_orders(payload, x_opex_user, x_opex_role))


@router.post("/purchase-orders/manual")
def manual_po(payload: ManualPurchaseOrderRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: create_manual_po(payload, x_opex_user, x_opex_role))


@router.get("/slots")
def slots(warehouse_name: str | None = None, slot_date: str | None = None, supplier_name: str | None = None, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    def load():
        if supplier_name:
            if warehouse_name:
                assert_supplier_warehouse_access(x_opex_user, supplier_name, warehouse_name, x_opex_role)
            else:
                assert_supplier_access(x_opex_user, supplier_name, x_opex_role)
        return get_slot_capacity(warehouse_name, slot_date, supplier_name)
    return guard(load)


@router.put("/slots/capacity/bulk")
def bulk(payload: BulkCapacityRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: bulk_update_capacity(payload, x_opex_user, x_opex_role))


@router.post("/slots/capacity/block-dates")
def block_dates(payload: BlockSlotDatesRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: block_slot_dates(payload, x_opex_user, x_opex_role))


@router.put("/slots/capacity/edit")
def edit_slot(payload: EditSlotCapacityRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: edit_slot_capacity(payload, x_opex_user, x_opex_role))


@router.put("/slots/capacity/bulk-selection")
def edit_selected_slots(payload: BulkSlotEditRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: bulk_edit_slot_capacities(payload, x_opex_user, x_opex_role))


@router.post("/slots/capacity/bulk-delete")
def delete_selected_slots(payload: BulkSlotDeleteRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: bulk_delete_slot_capacities(payload, x_opex_user, x_opex_role))


@router.delete("/slots/capacity")
def delete_slot(warehouse_name: str, date: str, slot: str, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: delete_slot_capacity(warehouse_name, date, slot, x_opex_user, x_opex_role))


@router.get("/supplier-capacity")
def supplier_capacity(warehouse_name: str | None = None, supplier_name: str | None = None, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    if not is_admin(x_opex_user, x_opex_role):
        raise HTTPException(403, "Sabit kapasite listesini görüntüleme yetkiniz yok.")
    return get_supplier_capacity(warehouse_name, supplier_name)


@router.put("/supplier-capacity/bulk")
def supplier_capacity_bulk(payload: SupplierCapacityBulkRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: bulk_update_supplier_capacity(payload, x_opex_user, x_opex_role))


@router.put("/supplier-capacity/matrix")
def supplier_capacity_matrix(payload: SupplierCapacityMatrixRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: bulk_update_supplier_capacity_matrix(payload, x_opex_user, x_opex_role))


@router.get("/supplier-daily-limits")
def supplier_daily_limits(warehouse_name: str | None = None, supplier_name: str | None = None, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    if not is_admin(x_opex_user, x_opex_role):
        raise HTTPException(403, "Günlük tedarikçi limitlerini görüntüleme yetkiniz yok.")
    return get_supplier_daily_limits(warehouse_name, supplier_name)


@router.get("/supplier-access")
def supplier_access_list(x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: get_supplier_access_mappings(x_opex_user, x_opex_role))


@router.put("/supplier-access")
def supplier_access_upsert(payload: SupplierAccessMappingRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: upsert_supplier_access_mapping(payload, x_opex_user, x_opex_role))


@router.delete("/supplier-access/{email}")
def supplier_access_delete(email: str, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: delete_supplier_access_mapping(email, x_opex_user, x_opex_role))


@router.put("/supplier-daily-limits")
def supplier_daily_limits_update(payload: SupplierDailyLimitRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: update_supplier_daily_limit(payload, x_opex_user, x_opex_role))


@router.get("/reservations")
def reservations(supplier_name: str | None = None, warehouse_name: str | None = None, status: str | None = None, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: get_reservations(supplier_name, warehouse_name, status, x_opex_user, x_opex_role))


@router.post("/reservations")
def create(payload: CreateReservationRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: create_reservation(payload, x_opex_user, x_opex_role))


@router.put("/reservations/{no}/arrival-check")
def arrival(no: str, payload: ArrivalCheckRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: update_arrival_check(no, payload, x_opex_user, x_opex_role))


@router.put("/reservations/{no}/admin-edit")
def reservation_admin_edit(no: str, payload: AdminReservationEditRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: edit_reservation_admin(no, payload, x_opex_user, x_opex_role))


@router.put("/reservations/{no}/status")
def reservation_status(no: str, payload: ReservationStatusRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: update_reservation_status(no, payload, x_opex_user, x_opex_role))


@router.post("/reservations/{no}/cancel")
def cancel(no: str, admin_override: bool = False, reason: str = "", x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: cancel_reservation(no, admin_override, x_opex_user, x_opex_role, reason))


@router.get("/kpis")
def kpis(supplier_name: str | None = None, warehouse_name: str | None = None, date_from: str | None = None, date_to: str | None = None, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: get_kpis(x_opex_user, x_opex_role, supplier_name, warehouse_name, date_from, date_to))


@router.post("/analytics/ask")
def analytics_ask(payload: AnalyticsAskRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: ask_analytics(payload, x_opex_user, x_opex_role))


@router.post("/admin/command/execute")
def admin_command_execute(payload: AdminCommandExecuteRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: execute_admin_command(payload, x_opex_user, x_opex_role))


@router.get("/notifications/outbox")
def notification_outbox(limit: int = 200, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: get_notification_outbox(limit, x_opex_user, x_opex_role))


@router.post("/notifications/process-due")
def notification_process(x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: process_notifications(x_opex_user, x_opex_role))


@router.get("/audit-log")
def audit_log(limit: int = 200, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: get_audit_log(limit, x_opex_user, x_opex_role))


@router.get("/settings")
def settings():
    return get_settings()


@router.put("/settings")
def settings_update(payload: SettingsUpdateRequest, x_opex_user: str | None = Header(None), x_opex_role: str | None = Header(None)):
    return guard(lambda: update_settings(payload, x_opex_user, x_opex_role))
