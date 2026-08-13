from datetime import date, datetime, timedelta
import os
import re
from threading import Event, Lock, Thread
from typing import Any

from .mock_data import (
    ADMIN_EMAILS,
    DOCKOS_SETTINGS,
    MOCK_AUDIT_LOG,
    MOCK_NOTIFICATION_OUTBOX,
    MOCK_PURCHASE_ORDERS,
    MOCK_RESERVATIONS,
    MOCK_SLOT_CAPACITY,
    MOCK_SLOT_HOLDS,
    MOCK_SUPPLIER_CAPACITY,
    MOCK_SUPPLIER_DAILY_LIMITS,
    MOCK_SUPPLIER_ACCESS,
    MOCK_USER_SUPPLIERS,
    MOCK_WAREHOUSES,
)
from .persistence import STATE_LOCK, load_state, save_state
from .bigquery_po import fetch_live_purchase_orders
from .notifications import process_due_notifications, queue_reservation_flow

LIVE_PO_CACHE: list[dict[str, Any]] = []
_NOTIFICATION_STOP = Event()
_NOTIFICATION_START_LOCK = Lock()
_NOTIFICATION_THREAD = None

STATE_COLLECTIONS = {
    "purchase_orders": MOCK_PURCHASE_ORDERS,
    "reservations": MOCK_RESERVATIONS,
    "slot_capacity": MOCK_SLOT_CAPACITY,
    "supplier_capacity": MOCK_SUPPLIER_CAPACITY,
    "supplier_daily_limits": MOCK_SUPPLIER_DAILY_LIMITS,
    "supplier_access": MOCK_SUPPLIER_ACCESS,
    "audit_log": MOCK_AUDIT_LOG,
    "notification_outbox": MOCK_NOTIFICATION_OUTBOX,
}
load_state(STATE_COLLECTIONS, DOCKOS_SETTINGS)


def _slot_key(warehouse_name, date_key, slot_name):
    return f"{warehouse_name}|{date_key}|{slot_name}"


def _ensure_slot_horizon(days=90):
    existing = {(row["warehouse_name"], row["date"], row["slot"]) for row in MOCK_SLOT_CAPACITY}
    deleted = set(DOCKOS_SETTINGS.setdefault("deleted_slots", []))
    added = 0
    for offset in range(days + 1):
        date_key = str(date.today() + timedelta(days=offset))
        for warehouse in MOCK_WAREHOUSES:
            for hour in range(6, 24):
                slot_name = f"{hour:02d}:00 - {(0 if hour == 23 else hour + 1):02d}:00"
                key = (warehouse["warehouse_name"], date_key, slot_name)
                if key in existing or _slot_key(*key) in deleted:
                    continue
                MOCK_SLOT_CAPACITY.append({"warehouse_name": key[0], "date": key[1], "slot": key[2], "max_pallet": 40, "max_sku": 500, "remaining_pallet": 40, "remaining_sku": 500})
                existing.add(key)
                added += 1
    if added:
        save_state(STATE_COLLECTIONS, DOCKOS_SETTINGS)


_ensure_slot_horizon()


def _persist():
    save_state(STATE_COLLECTIONS, DOCKOS_SETTINGS)


def _validate_slot_name(slot_name):
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)\s*-\s*([01]\d|2[0-3]):([0-5]\d)", str(slot_name or "").strip())
    if not match:
        raise ValueError("Slot saati HH:MM - HH:MM biçiminde olmalıdır.")
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    if start == end:
        raise ValueError("Slot başlangıç ve bitiş saati aynı olamaz.")
    return f"{match.group(1)}:{match.group(2)} - {match.group(3)}:{match.group(4)}"


def _slot_bounds(slot_name):
    normalized = _validate_slot_name(slot_name)
    start_text, end_text = [value.strip() for value in normalized.split("-")]
    start_hour, start_minute = [int(value) for value in start_text.split(":")]
    end_hour, end_minute = [int(value) for value in end_text.split(":")]
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    if end <= start:
        end += 1440
    return start, end


def _slots_overlap(first, second):
    first_start, first_end = _slot_bounds(first)
    second_start, second_end = _slot_bounds(second)
    return any(first_start < second_end + shift and second_start + shift < first_end for shift in (-1440, 0, 1440))


def _slot_duration(slot_name):
    start, end = _slot_bounds(slot_name)
    return end - start


def _is_default_hour_slot(slot_name):
    start, _ = _slot_bounds(slot_name)
    return start % 60 == 0 and _slot_duration(slot_name) == 60


def _restore_deleted_slot(warehouse_name, date_key, slot_name):
    deleted = DOCKOS_SETTINGS.setdefault("deleted_slots", [])
    key = _slot_key(warehouse_name, date_key, slot_name)
    if key in deleted:
        deleted.remove(key)


def _audit(action, entity_type, entity_id, user_email=None, details=None):
    MOCK_AUDIT_LOG.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user_email": _email(user_email) or "system",
        "details": details or {},
    })
    if len(MOCK_AUDIT_LOG) > 5000:
        del MOCK_AUDIT_LOG[:-5000]


def _email(v):
    return (v or "").strip().lower()


def _access_mapping(user_email):
    email = _email(user_email)
    return next((row for row in MOCK_SUPPLIER_ACCESS if _email(row.get("email")) == email and row.get("active", True)), None)


def _supplier_contact_email(supplier_name):
    return next((_email(row.get("email")) for row in MOCK_SUPPLIER_ACCESS if row.get("active", True) and supplier_name in row.get("supplier_names", []) and _email(row.get("email")) not in ADMIN_EMAILS), "")

def is_admin(user_email=None, user_role=None):
    trusted_role_header = os.getenv("DOCKOS_TRUST_ROLE_HEADER", "false").lower() == "true"
    role_is_admin = (user_role or "").lower() in {"admin", "superadmin", "dockos_admin", "opex_admin"}
    return _email(user_email) in ADMIN_EMAILS or (trusted_role_header and role_is_admin)

def allowed_suppliers(user_email=None, user_role=None):
    if is_admin(user_email,user_role):
        return sorted({p["supplier_name"] for p in MOCK_PURCHASE_ORDERS})
    mapping = _access_mapping(user_email)
    return sorted(set(mapping.get("supplier_names", []))) if mapping else []


def allowed_warehouses(user_email=None, user_role=None):
    if is_admin(user_email, user_role):
        return sorted({row["warehouse_name"] for row in MOCK_WAREHOUSES})
    mapping = _access_mapping(user_email)
    if not mapping:
        return []
    if mapping.get("all_warehouses", True):
        return sorted({row.get("warehouse_name") for row in MOCK_WAREHOUSES if row.get("warehouse_name")})
    return sorted(set(mapping.get("warehouse_names", [])))

def assert_supplier_access(user_email, supplier_name, user_role=None):
    if not is_admin(user_email,user_role) and supplier_name not in allowed_suppliers(user_email,user_role):
        raise PermissionError("Bu tedarikçi için işlem yapma yetkiniz yok.")


def assert_supplier_warehouse_access(user_email, supplier_name, warehouse_name, user_role=None):
    assert_supplier_access(user_email, supplier_name, user_role)
    if not is_admin(user_email, user_role) and warehouse_name not in allowed_warehouses(user_email, user_role):
        raise PermissionError("Bu merkez depo için işlem yapma yetkiniz yok.")


def get_supplier_access_mappings(user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Tedarikçi erişim eşleşmelerini görüntüleme yetkiniz yok.")
    return sorted((dict(row) for row in MOCK_SUPPLIER_ACCESS), key=lambda row: _email(row.get("email")))


def upsert_supplier_access_mapping(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Tedarikçi erişim eşleşmesi yönetme yetkiniz yok.")
    email = _email(payload.email)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Geçerli bir e-posta adresi girin.")
    known_suppliers = {row.get("supplier_name") for row in MOCK_PURCHASE_ORDERS}
    unknown_suppliers = sorted(set(payload.supplier_names) - known_suppliers)
    if unknown_suppliers:
        raise ValueError("Bilinmeyen tedarikçi: " + ", ".join(unknown_suppliers))
    known_warehouses = {row.get("warehouse_name") for row in MOCK_WAREHOUSES}
    unknown_warehouses = sorted(set(payload.warehouse_names) - known_warehouses)
    if unknown_warehouses:
        raise ValueError("Bilinmeyen merkez depo: " + ", ".join(unknown_warehouses))
    if not payload.all_warehouses and not payload.warehouse_names:
        raise ValueError("En az bir merkez depo seçin veya tüm depoları etkinleştirin.")
    row = {
        "email": email,
        "supplier_names": sorted(set(payload.supplier_names)),
        "warehouse_names": [] if payload.all_warehouses else sorted(set(payload.warehouse_names)),
        "all_warehouses": payload.all_warehouses,
        "active": payload.active,
        "locale": payload.locale,
        "updated_at": datetime.now().isoformat(),
        "updated_by": _email(user_email),
    }
    with STATE_LOCK:
        existing = next((item for item in MOCK_SUPPLIER_ACCESS if _email(item.get("email")) == email), None)
        if existing:
            existing.clear(); existing.update(row)
            action = "UPDATE"
        else:
            MOCK_SUPPLIER_ACCESS.append(row)
            action = "CREATE"
        _audit(action, "SUPPLIER_ACCESS", email, user_email, {"supplier_names": row["supplier_names"], "warehouse_names": row["warehouse_names"], "all_warehouses": row["all_warehouses"], "active": row["active"]})
        _persist()
    return {"status": "UPDATED", "message": "E-posta erişim eşleşmesi kaydedildi.", "row": row}


def delete_supplier_access_mapping(email, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Tedarikçi erişim eşleşmesi silme yetkiniz yok.")
    normalized = _email(email)
    with STATE_LOCK:
        existing = next((item for item in MOCK_SUPPLIER_ACCESS if _email(item.get("email")) == normalized), None)
        if not existing:
            raise ValueError("Erişim eşleşmesi bulunamadı.")
        MOCK_SUPPLIER_ACCESS.remove(existing)
        _audit("DELETE", "SUPPLIER_ACCESS", normalized, user_email)
        _persist()
    return {"status": "DELETED", "message": "E-posta erişim eşleşmesi kaldırıldı."}

def get_my_suppliers(user_email=None, user_role=None):
    return [{"supplier_name":x} for x in allowed_suppliers(user_email,user_role)]

def get_suppliers(user_email=None, user_role=None):
    return get_my_suppliers(user_email,user_role)

def get_warehouses(supplier_name=None, user_email=None, user_role=None):
    if not supplier_name:
        return MOCK_WAREHOUSES
    assert_supplier_access(user_email, supplier_name, user_role)
    source = [*MOCK_PURCHASE_ORDERS, *LIVE_PO_CACHE]
    allowed = {row.get("warehouse_name") for row in source if row.get("supplier_name") == supplier_name}
    known = [row for row in MOCK_WAREHOUSES if row.get("warehouse_name") in allowed]
    extra = [{"warehouse_name": name} for name in sorted(allowed - {row.get("warehouse_name") for row in known}) if name]
    result = [*known, *extra]
    if not is_admin(user_email, user_role):
        allowed_warehouse_names = set(allowed_warehouses(user_email, user_role))
        result = [row for row in result if row.get("warehouse_name") in allowed_warehouse_names]
    return result


def _mock_purchase_orders(supplier_name=None, warehouse_name=None):
    rows = []
    for po in MOCK_PURCHASE_ORDERS:
        if po.get("status") != "OPEN":
            continue
        if supplier_name and po["supplier_name"].casefold() != supplier_name.casefold():
            continue
        if warehouse_name and po["warehouse_name"].casefold() != warehouse_name.casefold():
            continue
        row = dict(po)
        row.setdefault("po_order_id", row.get("po_number"))
        row.setdefault("promised_date", row.get("delivery_date"))
        row.setdefault("total_sku", row.get("sku_count", 0))
        row.setdefault("order_status", row.get("status", "OPEN"))
        rows.append(row)
    return rows


def get_live_purchase_orders(supplier_name=None, warehouse_name=None, user_email=None, user_role=None):
    if supplier_name:
        assert_supplier_access(user_email, supplier_name, user_role)
    source_mode = os.getenv("DOCKOS_PO_SOURCE", "AUTO").upper()
    live = {"source": "SKIPPED", "message": "", "rows": []}
    if source_mode in {"AUTO", "BIGQUERY"}:
        live = fetch_live_purchase_orders(supplier_name, warehouse_name)
    if live.get("source") == "BIGQUERY":
        rows = live.get("rows", [])
        LIVE_PO_CACHE[:] = rows
        if not is_admin(user_email, user_role):
            allowed = set(allowed_suppliers(user_email, user_role))
            allowed_dc = set(allowed_warehouses(user_email, user_role))
            rows = [row for row in rows if row.get("supplier_name") in allowed and row.get("warehouse_name") in allowed_dc]
        return {"source": "BIGQUERY", "message": live.get("message"), "count": len(rows), "rows": rows}

    rows = _mock_purchase_orders(supplier_name, warehouse_name)
    if not is_admin(user_email,user_role):
        allowed=set(allowed_suppliers(user_email,user_role)); allowed_dc=set(allowed_warehouses(user_email,user_role)); rows=[r for r in rows if r.get("supplier_name") in allowed and r.get("warehouse_name") in allowed_dc]
    has_persisted_import = any(row.get("source") in {"CSV_UPLOAD", "MANUAL", "LIVE"} for row in rows)
    return {
        "source": "PERSISTED_IMPORT" if has_persisted_import else "MOCK",
        "message": "Kalıcı PO içe aktarımı kullanılıyor." if has_persisted_import else "Pilot test verisi kullanılıyor.",
        "fallback_reason": live.get("message") if source_mode in {"AUTO", "BIGQUERY"} else None,
        "count": len(rows),
        "rows": rows,
    }


def get_purchase_orders(supplier_name=None, warehouse_name=None, user_email=None, user_role=None):
    return get_live_purchase_orders(supplier_name, warehouse_name, user_email, user_role)["rows"]



def import_purchase_orders(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("PO dosyası yükleme yetkiniz yok.")

    required = {
        "warehouse_name", "po_order_id", "supplier_name",
        "order_status", "total_sku"
    }
    imported = 0
    updated = 0
    skipped = 0
    errors = []

    if payload.replace_existing:
        removable = [po for po in MOCK_PURCHASE_ORDERS if po.get("source") == "CSV_UPLOAD"]
        for po in removable:
            MOCK_PURCHASE_ORDERS.remove(po)

    for index, item in enumerate(payload.rows, start=2):
        raw = item.model_dump()
        missing = [key for key in required if raw.get(key) in (None, "")]
        if missing:
            skipped += 1
            errors.append({"row": index, "message": f"Eksik alan: {', '.join(missing)}"})
            continue

        po_number = str(raw["po_order_id"]).strip().upper()
        existing = next(
            (po for po in MOCK_PURCHASE_ORDERS
             if str(po.get("po_number", "")).casefold() == po_number.casefold()),
            None,
        )

        normalized = {
            "warehouse_name": str(raw["warehouse_name"]).replace("Yemeksepeti Market, ", "").strip(),
            "po_number": po_number,
            "po_order_id": po_number,
            "supplier_id": str(raw.get("supplier_id") or "").strip(),
            "supplier_name": str(raw["supplier_name"]).strip(),
            "created_date": raw.get("created_date"),
            "delivery_date": raw.get("promised_date"),
            "promised_date": raw.get("promised_date"),
            "order_status": str(raw.get("order_status") or "confirmed").strip(),
            "status": "OPEN",
            "sku_count": int(raw.get("total_sku") or 0),
            "total_sku": int(raw.get("total_sku") or 0),
            "pallet_count": 0,
            "source": "CSV_UPLOAD",
        }

        if existing:
            existing.update(normalized)
            updated += 1
        else:
            MOCK_PURCHASE_ORDERS.append(normalized)
            imported += 1

    _audit("IMPORT", "PURCHASE_ORDER", "CSV", user_email, {
        "imported": imported, "updated": updated, "skipped": skipped,
    })
    _persist()
    return {
        "status": "IMPORTED",
        "message": f"{imported} PO eklendi, {updated} PO güncellendi, {skipped} satır atlandı.",
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:50],
        "total_open_po": len([po for po in MOCK_PURCHASE_ORDERS if po.get("status") == "OPEN"]),
    }


def cleanup_expired_holds():
    now = datetime.now()
    MOCK_SLOT_HOLDS[:] = [
        item for item in MOCK_SLOT_HOLDS
        if datetime.fromisoformat(item["expires_at"]) > now
    ]


def _active_reservations(warehouse_name, slot_date, slot_name, exclude_reservation_no=None):
    return [
        row for row in MOCK_RESERVATIONS
        if row.get("reservation_no") != exclude_reservation_no
        and row.get("shipment_mode") == "SEVKIYAT"
        and row.get("status") != "CANCELLED"
        and row.get("warehouse_name") == warehouse_name
        and row.get("slot_date") == slot_date
        and row.get("selected_slot") == slot_name
    ]


def _allocation(warehouse_name, slot_date, slot_name, supplier_name):
    return next((
        row for row in MOCK_SUPPLIER_CAPACITY
        if row.get("warehouse_name") == warehouse_name
        and row.get("date") == slot_date
        and row.get("slot") == slot_name
        and row.get("supplier_name") == supplier_name
    ), None)


def _availability(slot, supplier_name=None, exclude_reservation_no=None):
    reservations = _active_reservations(slot["warehouse_name"], slot["date"], slot["slot"], exclude_reservation_no)
    total_used_pallet = sum(int(row.get("pallet_count") or 0) for row in reservations)
    total_used_sku = sum(int(row.get("sku_count") or 0) for row in reservations)

    allocations = [
        row for row in MOCK_SUPPLIER_CAPACITY
        if row.get("warehouse_name") == slot["warehouse_name"]
        and row.get("date") == slot["date"]
        and row.get("slot") == slot["slot"]
    ]
    reserved_pallet = sum(int(row.get("reserved_pallet") or 0) for row in allocations)
    reserved_sku = sum(int(row.get("reserved_sku") or 0) for row in allocations)

    allocation = _allocation(slot["warehouse_name"], slot["date"], slot["slot"], supplier_name) if supplier_name else None
    if allocation:
        own_rows = [row for row in reservations if row.get("supplier_name") == supplier_name]
        available_pallet = int(allocation["reserved_pallet"]) - sum(int(row.get("pallet_count") or 0) for row in own_rows)
        available_sku = int(allocation["reserved_sku"]) - sum(int(row.get("sku_count") or 0) for row in own_rows)
        source = "SUPPLIER_RESERVED"
    elif supplier_name:
        allocated_names = {row.get("supplier_name") for row in allocations}
        general_rows = [row for row in reservations if row.get("supplier_name") not in allocated_names]
        available_pallet = int(slot["max_pallet"]) - reserved_pallet - sum(int(row.get("pallet_count") or 0) for row in general_rows)
        available_sku = int(slot["max_sku"]) - reserved_sku - sum(int(row.get("sku_count") or 0) for row in general_rows)
        source = "GENERAL"
    else:
        available_pallet = int(slot["max_pallet"]) - total_used_pallet
        available_sku = int(slot["max_sku"]) - total_used_sku
        source = "ADMIN_TOTAL"

    return max(0, available_pallet), max(0, available_sku), source


def get_slot_capacity(warehouse_name=None, slot_date=None, supplier_name=None):
    cleanup_expired_holds()
    rows = MOCK_SLOT_CAPACITY
    if warehouse_name:
        rows = [r for r in rows if r["warehouse_name"].casefold() == warehouse_name.casefold()]
    if slot_date:
        rows = [r for r in rows if r["date"] == slot_date]
    result = []
    for original in rows:
        row = dict(original)
        available_pallet, available_sku, source = _availability(row, supplier_name)
        row["remaining_pallet"] = available_pallet
        row["remaining_sku"] = available_sku
        row["available_pallet"] = available_pallet
        row["available_sku"] = available_sku
        row["capacity_source"] = source
        result.append(row)
    return result


def get_supplier_capacity(warehouse_name=None, supplier_name=None):
    rows = list(MOCK_SUPPLIER_CAPACITY)
    if warehouse_name:
        rows = [row for row in rows if row.get("warehouse_name") == warehouse_name]
    if supplier_name:
        rows = [row for row in rows if row.get("supplier_name") == supplier_name]
    return rows


def get_supplier_daily_limits(warehouse_name=None, supplier_name=None):
    rows = list(MOCK_SUPPLIER_DAILY_LIMITS)
    if warehouse_name:
        rows = [row for row in rows if row.get("warehouse_name") == warehouse_name]
    if supplier_name:
        rows = [row for row in rows if row.get("supplier_name") == supplier_name]
    return sorted(rows, key=lambda row: (row.get("date", ""), row.get("supplier_name", "")))


def _daily_limit(warehouse_name, supplier_name, date_key):
    return next((row for row in MOCK_SUPPLIER_DAILY_LIMITS if row.get("warehouse_name") == warehouse_name and row.get("supplier_name") == supplier_name and row.get("date") == date_key), None)


def _daily_used(warehouse_name, supplier_name, date_key, exclude_reservation_no=None):
    return sum(int(row.get("pallet_count") or 0) for row in MOCK_RESERVATIONS if row.get("reservation_no") != exclude_reservation_no and row.get("status") != "CANCELLED" and row.get("shipment_mode") == "SEVKIYAT" and row.get("warehouse_name") == warehouse_name and row.get("supplier_name") == supplier_name and row.get("slot_date") == date_key)


def update_supplier_daily_limit(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Günlük tedarikçi limiti yalnızca merkez depo admini tarafından yönetilebilir.")
    updated = 0
    with STATE_LOCK:
        for date_key in sorted(set(payload.dates)):
            used = _daily_used(payload.warehouse_name, payload.supplier_name, date_key)
            if payload.max_pallet and payload.max_pallet < used:
                raise ValueError(f"{date_key} için limit mevcut {used} palet kullanımının altına indirilemez.")
            existing = _daily_limit(payload.warehouse_name, payload.supplier_name, date_key)
            if payload.max_pallet == 0:
                if existing:
                    MOCK_SUPPLIER_DAILY_LIMITS.remove(existing)
            elif existing:
                existing["max_pallet"] = payload.max_pallet
            else:
                MOCK_SUPPLIER_DAILY_LIMITS.append({"warehouse_name": payload.warehouse_name, "supplier_name": payload.supplier_name, "date": date_key, "max_pallet": payload.max_pallet})
            updated += 1
        _audit("UPSERT", "SUPPLIER_DAILY_LIMIT", payload.supplier_name, user_email, {"warehouse_name": payload.warehouse_name, "dates": payload.dates, "max_pallet": payload.max_pallet})
        _persist()
    return {"status": "UPDATED", "count": updated, "message": f"{payload.supplier_name} için {updated} güne maksimum {payload.max_pallet} palet limiti uygulandı."}


def bulk_update_supplier_capacity(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Sabit tedarikçi kapasitesi yalnızca admin tarafından yönetilebilir.")
    updated = 0
    with STATE_LOCK:
        for date_key in payload.dates:
            for slot_name in payload.slots:
                base = next((row for row in MOCK_SLOT_CAPACITY if row["warehouse_name"] == payload.warehouse_name and row["date"] == date_key and row["slot"] == slot_name), None)
                if not base:
                    raise ValueError(f"Kapasite tanımı bulunamadı: {date_key} {slot_name}")
                others = [row for row in MOCK_SUPPLIER_CAPACITY if row["warehouse_name"] == payload.warehouse_name and row["date"] == date_key and row["slot"] == slot_name and row["supplier_name"] != payload.supplier_name]
                if sum(int(row["reserved_pallet"]) for row in others) + payload.reserved_pallet > int(base["max_pallet"]):
                    raise ValueError(f"Ayrılan palet kapasitesi slot limitini aşıyor: {date_key} {slot_name}")
                if sum(int(row["reserved_sku"]) for row in others) + payload.reserved_sku > int(base["max_sku"]):
                    raise ValueError(f"Ayrılan SKU kapasitesi slot limitini aşıyor: {date_key} {slot_name}")
                existing = _allocation(payload.warehouse_name, date_key, slot_name, payload.supplier_name)
                if payload.reserved_pallet == 0 and payload.reserved_sku == 0:
                    if existing:
                        MOCK_SUPPLIER_CAPACITY.remove(existing)
                elif existing:
                    existing.update({"reserved_pallet": payload.reserved_pallet, "reserved_sku": payload.reserved_sku})
                else:
                    MOCK_SUPPLIER_CAPACITY.append({
                        "warehouse_name": payload.warehouse_name,
                        "supplier_name": payload.supplier_name,
                        "date": date_key,
                        "slot": slot_name,
                        "reserved_pallet": payload.reserved_pallet,
                        "reserved_sku": payload.reserved_sku,
                    })
                updated += 1
        _audit("UPSERT", "SUPPLIER_CAPACITY", payload.supplier_name, user_email, {"count": updated, "warehouse_name": payload.warehouse_name})
        _persist()
    return {"status": "UPDATED", "count": updated, "message": f"{payload.supplier_name} için {updated} slot kapasitesi güncellendi."}


def bulk_update_supplier_capacity_matrix(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Çoklu tedarikçi kapasitesi yalnızca admin tarafından yönetilebilir.")
    supplier_names = [item.supplier_name.strip() for item in payload.allocations]
    if len(set(name.casefold() for name in supplier_names)) != len(supplier_names):
        raise ValueError("Aynı tedarikçi kapasite matrisinde birden fazla kez seçilemez.")

    dates = sorted(set(payload.dates))
    slots = sorted(set(payload.slots))
    selected_names = {name.casefold() for name in supplier_names}
    with STATE_LOCK:
        # Önce tüm kombinasyonları doğrula; hata varsa hiçbir kayıt değişmez.
        for item in payload.allocations:
            if item.max_daily_pallet is not None and item.max_daily_pallet > 0:
                for date_key in dates:
                    used = _daily_used(payload.warehouse_name, item.supplier_name, date_key)
                    if item.max_daily_pallet < used:
                        raise ValueError(f"{item.supplier_name} {date_key} günlük limiti mevcut {used} palet kullanımının altına indirilemez.")
        for date_key in dates:
            for slot_name in slots:
                base = next((row for row in MOCK_SLOT_CAPACITY if row["warehouse_name"] == payload.warehouse_name and row["date"] == date_key and row["slot"] == slot_name), None)
                if not base:
                    raise ValueError(f"Kapasite tanımı bulunamadı: {date_key} {slot_name}")
                untouched = [row for row in MOCK_SUPPLIER_CAPACITY if row["warehouse_name"] == payload.warehouse_name and row["date"] == date_key and row["slot"] == slot_name and row["supplier_name"].casefold() not in selected_names]
                pallet_total = sum(int(row.get("reserved_pallet") or 0) for row in untouched) + sum(item.reserved_pallet for item in payload.allocations)
                sku_total = sum(int(row.get("reserved_sku") or 0) for row in untouched) + sum(item.reserved_sku for item in payload.allocations)
                if pallet_total > int(base["max_pallet"]):
                    raise ValueError(f"Toplam ayrılmış palet {date_key} {slot_name} limitini aşıyor: {pallet_total}/{base['max_pallet']}")
                if sku_total > int(base["max_sku"]):
                    raise ValueError(f"Toplam ayrılmış SKU {date_key} {slot_name} limitini aşıyor: {sku_total}/{base['max_sku']}")

        updated = 0
        for date_key in dates:
            for slot_name in slots:
                for item in payload.allocations:
                    existing = _allocation(payload.warehouse_name, date_key, slot_name, item.supplier_name)
                    if item.reserved_pallet == 0 and item.reserved_sku == 0:
                        if existing:
                            MOCK_SUPPLIER_CAPACITY.remove(existing)
                    elif existing:
                        existing.update({"reserved_pallet": item.reserved_pallet, "reserved_sku": item.reserved_sku})
                    else:
                        MOCK_SUPPLIER_CAPACITY.append({
                            "warehouse_name": payload.warehouse_name,
                            "supplier_name": item.supplier_name,
                            "date": date_key,
                            "slot": slot_name,
                            "reserved_pallet": item.reserved_pallet,
                            "reserved_sku": item.reserved_sku,
                        })
                    updated += 1
            for item in payload.allocations:
                if item.max_daily_pallet is None:
                    continue
                existing_limit = _daily_limit(payload.warehouse_name, item.supplier_name, date_key)
                if item.max_daily_pallet == 0:
                    if existing_limit:
                        MOCK_SUPPLIER_DAILY_LIMITS.remove(existing_limit)
                elif existing_limit:
                    existing_limit["max_pallet"] = item.max_daily_pallet
                else:
                    MOCK_SUPPLIER_DAILY_LIMITS.append({"warehouse_name": payload.warehouse_name, "supplier_name": item.supplier_name, "date": date_key, "max_pallet": item.max_daily_pallet})
        _audit("MATRIX_UPSERT", "SUPPLIER_CAPACITY", payload.warehouse_name, user_email, {"dates": len(dates), "slots": len(slots), "suppliers": supplier_names, "records": updated})
        _persist()
    return {"status": "UPDATED", "count": updated, "message": f"{len(supplier_names)} tedarikçi × {len(dates)} tarih × {len(slots)} saat için kapasite uygulandı."}


def hold_slot(payload):
    matching = next(
        (
            row for row in MOCK_SLOT_CAPACITY
            if row["warehouse_name"] == payload.warehouse_name
            and row["date"] == payload.slot_date
            and row["slot"] == payload.selected_slot
        ),
        None,
    )
    if not matching:
        return {"hold_id": "", "status": "FAILED", "message": "Slot bulunamadı.", "expires_at": ""}

    held_pallet = sum(
        h["pallet_count"] for h in MOCK_SLOT_HOLDS
        if h["warehouse_name"] == payload.warehouse_name
        and h["slot_date"] == payload.slot_date
        and h["selected_slot"] == payload.selected_slot
    )
    held_sku = sum(
        h["sku_count"] for h in MOCK_SLOT_HOLDS
        if h["warehouse_name"] == payload.warehouse_name
        and h["slot_date"] == payload.slot_date
        and h["selected_slot"] == payload.selected_slot
    )

    if payload.pallet_count > matching["remaining_pallet"] - held_pallet:
        return {"hold_id": "", "status": "FAILED", "message": "Palet kapasitesi yetersiz.", "expires_at": ""}
    if payload.sku_count > matching["remaining_sku"] - held_sku:
        return {"hold_id": "", "status": "FAILED", "message": "SKU kapasitesi yetersiz.", "expires_at": ""}

    hold_id = f"HOLD-{datetime.now():%Y%m%d%H%M%S%f}"
    expires_at = (datetime.now() + timedelta(minutes=2)).isoformat()
    MOCK_SLOT_HOLDS.append(
        {
            "hold_id": hold_id,
            "warehouse_name": payload.warehouse_name,
            "slot_date": payload.slot_date,
            "selected_slot": payload.selected_slot,
            "pallet_count": payload.pallet_count,
            "sku_count": payload.sku_count,
            "expires_at": expires_at,
        }
    )
    return {"hold_id": hold_id, "status": "HELD", "message": "Slot 2 dakika tutuldu.", "expires_at": expires_at}


def _validate_pos(payload, po_numbers, user_email=None, user_role=None):
    assert_supplier_warehouse_access(user_email, payload.supplier_name, payload.warehouse_name, user_role)
    source_by_number = {str(po.get("po_number")): po for po in MOCK_PURCHASE_ORDERS}
    source_by_number.update({str(po.get("po_number")): po for po in LIVE_PO_CACHE})
    source = list(source_by_number.values())
    matching = [
        po for po in source
        if po.get("po_number") in po_numbers
        and po.get("supplier_name") == payload.supplier_name
        and po.get("warehouse_name") == payload.warehouse_name
        and po.get("status") == "OPEN"
    ]
    return matching


def create_reservation(payload, user_email=None, user_role=None):
    po_numbers = payload.po_numbers or ([payload.po_number] if payload.po_number else [])
    assert_supplier_warehouse_access(user_email, payload.supplier_name, payload.warehouse_name, user_role)
    matching_pos = []

    with STATE_LOCK:
        if payload.shipment_mode == "SEVKIYAT":
            if not po_numbers:
                return {"reservation_no": "", "status": "FAILED", "message": "Sevkiyat için en az bir PO seçilmelidir."}
            matching_pos = _validate_pos(payload, po_numbers, user_email, user_role)
            if len(matching_pos) != len(po_numbers):
                return {"reservation_no": "", "status": "FAILED", "message": "PO bulunamadı veya PO–tedarikçi–depo eşleşmesi geçersiz."}
            if payload.sku_count <= 0 or payload.pallet_count <= 0:
                return {"reservation_no": "", "status": "FAILED", "message": "Sevkiyat için palet ve SKU sayısı zorunludur."}
            if not payload.slot_date or not payload.selected_slot:
                return {"reservation_no": "", "status": "FAILED", "message": "Sevkiyat için tarih ve slot zorunludur."}
            if not payload.shipment_details or len(payload.shipment_details.strip()) < 5:
                return {"reservation_no": "", "status": "FAILED", "message": "Sevkiyat detayları en az 5 karakter olmalıdır."}
            if not payload.vehicle_plate or len(payload.vehicle_plate.strip()) < 3:
                return {"reservation_no": "", "status": "FAILED", "message": "Sevkiyat için araç plakası zorunludur."}

            slot = next((row for row in MOCK_SLOT_CAPACITY if row["warehouse_name"] == payload.warehouse_name and row["date"] == payload.slot_date and row["slot"] == payload.selected_slot), None)
            if not slot:
                return {"reservation_no": "", "status": "FAILED", "message": "Seçilen tarih ve saat için kapasite tanımı yok."}
            available_pallet, available_sku, _ = _availability(slot, payload.supplier_name)
            if payload.pallet_count > available_pallet or payload.sku_count > available_sku:
                return {"reservation_no": "", "status": "FAILED", "message": "Seçilen slotun size ayrılan kapasitesi yetersiz."}
            daily_limit = _daily_limit(payload.warehouse_name, payload.supplier_name, payload.slot_date)
            daily_used = _daily_used(payload.warehouse_name, payload.supplier_name, payload.slot_date)
            if daily_limit and daily_used + payload.pallet_count > int(daily_limit["max_pallet"]):
                return {"reservation_no": "", "status": "FAILED", "message": f"Tedarikçinin günlük palet limiti aşılıyor. Kullanılan {daily_used}, talep {payload.pallet_count}, limit {daily_limit['max_pallet']}."}
        else:
            po_numbers = []
            if not payload.cargo_date:
                return {"reservation_no": "", "status": "FAILED", "message": "Kargo gönderim tarihi zorunludur."}
            if not payload.cargo_tracking_no or len(payload.cargo_tracking_no.strip()) < 3:
                return {"reservation_no": "", "status": "FAILED", "message": "Kargo takip numarası zorunludur."}

        reservation_no = f"DKS-{datetime.now():%Y%m%d%H%M%S%f}"
        reservation = {
            "reservation_no": reservation_no,
            "po_numbers": po_numbers,
            "po_number": ",".join(po_numbers),
            "supplier_name": payload.supplier_name,
            "warehouse_name": payload.warehouse_name,
            "shipment_mode": payload.shipment_mode,
            "pallet_count": payload.pallet_count if payload.shipment_mode == "SEVKIYAT" else 0,
            "sku_count": payload.sku_count if payload.shipment_mode == "SEVKIYAT" else 0,
            "slot_date": payload.slot_date if payload.shipment_mode == "SEVKIYAT" else payload.cargo_date,
            "selected_slot": payload.selected_slot if payload.shipment_mode == "SEVKIYAT" else "KARGO",
            "shipment_details": payload.shipment_details.strip() if payload.shipment_details else "",
            "waybill_info": payload.waybill_info,
            "shipment_form": payload.shipment_form,
            "box_count": payload.box_count,
            "vehicle_type": payload.vehicle_type if payload.shipment_mode == "SEVKIYAT" else None,
            "vehicle_count": payload.vehicle_count if payload.shipment_mode == "SEVKIYAT" else None,
            "vehicle_plate": (payload.vehicle_plate or "").upper().strip() if payload.shipment_mode == "SEVKIYAT" else "",
            "cargo_tracking_no": (payload.cargo_tracking_no or "").strip() if payload.shipment_mode == "KARGO" else "",
            "reservation_user": payload.reservation_user,
            "contact_email": _email(user_email),
            "status": "APPROVED",
            "status_note": "",
            "dc_task_status": "WAITING_ARRIVAL_CHECK" if payload.shipment_mode == "SEVKIYAT" else "CARGO_REGISTERED",
            "arrival_check": {"arrived": None, "dock_compatible": None, "on_time": None, "ramp_no": "", "note": ""},
            "created_at": datetime.now().isoformat(),
        }
        MOCK_RESERVATIONS.append(reservation)
        for po in matching_pos:
            po["status"] = "RESERVED"
        queue_reservation_flow(MOCK_NOTIFICATION_OUTBOX, reservation, "CREATED")
        notification_result = process_due_notifications(MOCK_NOTIFICATION_OUTBOX)
        _audit("CREATE", "RESERVATION", reservation_no, user_email, {"shipment_mode": payload.shipment_mode})
        _persist()

    message = "Rezervasyon başarıyla oluşturuldu." if payload.shipment_mode == "SEVKIYAT" else "Kargo kaydı başarıyla oluşturuldu."
    return {"reservation_no": reservation_no, "status": "APPROVED", "message": message, "notification": notification_result}


def get_reservations(supplier_name=None, warehouse_name=None, status=None, user_email=None, user_role=None):
    rows = list(MOCK_RESERVATIONS)
    if not is_admin(user_email,user_role):
        allowed=set(allowed_suppliers(user_email,user_role)); allowed_dc=set(allowed_warehouses(user_email,user_role)); rows=[r for r in rows if r.get("supplier_name") in allowed and r.get("warehouse_name") in allowed_dc]
    if supplier_name:
        assert_supplier_access(user_email, supplier_name, user_role)
    if warehouse_name and not is_admin(user_email, user_role) and warehouse_name not in allowed_warehouses(user_email, user_role):
        raise PermissionError("Bu merkez depo için rezervasyon görüntüleme yetkiniz yok.")
    if supplier_name:
        rows = [r for r in rows if r.get("supplier_name", "").casefold() == supplier_name.casefold()]
    if warehouse_name:
        rows = [r for r in rows if r.get("warehouse_name", "").casefold() == warehouse_name.casefold()]
    if status:
        rows = [r for r in rows if r.get("status", "").casefold() == status.casefold()]
    return rows


def _reservation_start(reservation):
    date_key = reservation.get("slot_date")
    slot_name = reservation.get("selected_slot", "")
    if not date_key or slot_name == "KARGO":
        return None
    start_text = slot_name.split("-")[0].strip()
    return datetime.fromisoformat(f"{date_key}T{start_text}:00")


def cancel_reservation(reservation_no, admin_override=False, user_email=None, user_role=None, reason=""):
    reservation = next((r for r in MOCK_RESERVATIONS if r["reservation_no"] == reservation_no), None)
    if not reservation:
        return {"reservation_no": reservation_no, "status": "FAILED", "message": "Rezervasyon bulunamadı."}
    if reservation["status"] == "CANCELLED":
        return {"reservation_no": reservation_no, "status": "FAILED", "message": "Rezervasyon zaten iptal edilmiş."}

    assert_supplier_warehouse_access(user_email, reservation.get("supplier_name"), reservation.get("warehouse_name"), user_role)
    if admin_override and not is_admin(user_email, user_role):
        raise PermissionError("Admin iptal yetkiniz yok.")
    start_at = _reservation_start(reservation)
    if start_at and not admin_override:
        deadline = start_at - timedelta(hours=DOCKOS_SETTINGS["supplier_cancel_hours"])
        if datetime.now() > deadline:
            return {
                "reservation_no": reservation_no,
                "status": "FAILED",
                "message": f"İptal süresi doldu. Randevuya {DOCKOS_SETTINGS['supplier_cancel_hours']} saat kala iptal kapanır.",
            }

    with STATE_LOCK:
        reservation["status"] = "CANCELLED"
        for po in MOCK_PURCHASE_ORDERS:
            if po.get("po_number") in reservation.get("po_numbers", []):
                po["status"] = "OPEN"
        reservation["status_note"] = (reason or "").strip()
        reservation["contact_email"] = reservation.get("contact_email") or _supplier_contact_email(reservation.get("supplier_name"))
        queue_reservation_flow(MOCK_NOTIFICATION_OUTBOX, reservation, "CANCELLED", reservation["status_note"])
        notification_result = process_due_notifications(MOCK_NOTIFICATION_OUTBOX)
        _audit("CANCEL", "RESERVATION", reservation_no, user_email, {"reason": reservation["status_note"]})
        _persist()

    return {"reservation_no": reservation_no, "status": "CANCELLED", "message": "Kayıt iptal edildi ve bildirim akışı oluşturuldu.", "notification": notification_result}


def update_arrival_check(reservation_no, payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Merkez depo kontrolü için admin yetkisi gereklidir.")
    reservation = next((r for r in MOCK_RESERVATIONS if r["reservation_no"] == reservation_no), None)
    if not reservation:
        return {"reservation_no": reservation_no, "status": "FAILED", "message": "Rezervasyon bulunamadı."}
    reservation["arrival_check"] = payload.model_dump()
    reservation["dc_task_status"] = "ARRIVAL_CHECK_COMPLETED"
    _audit("ARRIVAL_CHECK", "RESERVATION", reservation_no, user_email, payload.model_dump())
    _persist()
    return {"reservation_no": reservation_no, "status": "UPDATED", "message": "Merkez depo kontrolü kaydedildi."}


def edit_reservation_admin(reservation_no, payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Rezervasyon düzenleme yalnızca merkez depo admini tarafından yapılabilir.")
    reservation = next((row for row in MOCK_RESERVATIONS if row.get("reservation_no") == reservation_no), None)
    if not reservation:
        raise ValueError("Rezervasyon bulunamadı.")
    if reservation.get("status") == "CANCELLED":
        raise ValueError("İptal edilmiş rezervasyon düzenlenemez.")
    if reservation.get("shipment_mode") != "SEVKIYAT":
        raise ValueError("Bu düzenleme akışı yalnızca merkez depo sevkiyatları içindir.")

    with STATE_LOCK:
        slot = next((row for row in MOCK_SLOT_CAPACITY if row.get("warehouse_name") == reservation.get("warehouse_name") and row.get("date") == payload.slot_date and row.get("slot") == payload.selected_slot), None)
        if not slot:
            raise ValueError("Seçilen tarih/saat için slot kapasitesi bulunamadı.")
        available_pallet, available_sku, _ = _availability(slot, reservation.get("supplier_name"), reservation_no)
        if payload.pallet_count > available_pallet or payload.sku_count > available_sku:
            raise ValueError(f"Yeni slot kapasitesi yetersiz. Uygun: {available_pallet} palet / {available_sku} SKU.")
        limit = _daily_limit(reservation.get("warehouse_name"), reservation.get("supplier_name"), payload.slot_date)
        used = _daily_used(reservation.get("warehouse_name"), reservation.get("supplier_name"), payload.slot_date, reservation_no)
        if limit and used + payload.pallet_count > int(limit["max_pallet"]):
            raise ValueError(f"Tedarikçinin günlük maksimum {limit['max_pallet']} palet limiti aşılır.")

        before = {key: reservation.get(key) for key in ["slot_date", "selected_slot", "pallet_count", "sku_count", "vehicle_plate", "vehicle_type", "shipment_details"]}
        reservation.update({
            "slot_date": payload.slot_date,
            "selected_slot": payload.selected_slot,
            "pallet_count": payload.pallet_count,
            "sku_count": payload.sku_count,
            "vehicle_plate": payload.vehicle_plate.upper().strip(),
            "vehicle_type": payload.vehicle_type,
            "shipment_details": payload.shipment_details.strip(),
            "status": "APPROVED",
            "status_note": payload.edit_reason.strip(),
            "updated_at": datetime.now().isoformat(),
            "updated_by": _email(user_email),
        })
        reservation["contact_email"] = reservation.get("contact_email") or _supplier_contact_email(reservation.get("supplier_name"))
        queue_reservation_flow(MOCK_NOTIFICATION_OUTBOX, reservation, "EDITED", payload.edit_reason)
        notification_result = process_due_notifications(MOCK_NOTIFICATION_OUTBOX)
        _audit("EDIT", "RESERVATION", reservation_no, user_email, {"before": before, "after": {key: reservation.get(key) for key in before}, "reason": payload.edit_reason})
        _persist()
    return {"reservation_no": reservation_no, "status": "UPDATED", "message": "Rezervasyon güncellendi ve kurumsal bildirim akışı yenilendi.", "notification": notification_result, "row": reservation}


def update_slot_capacity(payload, user_email=None, user_role=None, persist=True):
    if not is_admin(user_email, user_role):
        raise PermissionError("Kapasite yönetimi için admin yetkisi gereklidir.")
    payload.slot = _validate_slot_name(payload.slot)
    _restore_deleted_slot(payload.warehouse_name, payload.date, payload.slot)
    slot = next(
        (
            row for row in MOCK_SLOT_CAPACITY
            if row["warehouse_name"] == payload.warehouse_name
            and row["date"] == payload.date
            and row["slot"] == payload.slot
        ),
        None,
    )
    allocations = [row for row in MOCK_SUPPLIER_CAPACITY if row.get("warehouse_name") == payload.warehouse_name and row.get("date") == payload.date and row.get("slot") == payload.slot]
    active = _active_reservations(payload.warehouse_name, payload.date, payload.slot)
    minimum_pallet = max(sum(int(row.get("reserved_pallet") or 0) for row in allocations), sum(int(row.get("pallet_count") or 0) for row in active))
    minimum_sku = max(sum(int(row.get("reserved_sku") or 0) for row in allocations), sum(int(row.get("sku_count") or 0) for row in active))
    if payload.max_pallet < minimum_pallet or payload.max_sku < minimum_sku:
        raise ValueError(f"Kapasite mevcut rezervasyon veya sabit tedarikçi ayrımının altına indirilemez. Minimum: {minimum_pallet} palet / {minimum_sku} SKU")
    if not slot:
        slot = {
            "warehouse_name": payload.warehouse_name,
            "date": payload.date,
            "slot": payload.slot,
            "max_pallet": payload.max_pallet,
            "max_sku": payload.max_sku,
            "remaining_pallet": payload.max_pallet,
            "remaining_sku": payload.max_sku,
        }
        MOCK_SLOT_CAPACITY.append(slot)
    else:
        used_pallet = max(0, slot["max_pallet"] - slot["remaining_pallet"])
        used_sku = max(0, slot["max_sku"] - slot["remaining_sku"])
        slot["max_pallet"] = payload.max_pallet
        slot["max_sku"] = payload.max_sku
        slot["remaining_pallet"] = max(0, payload.max_pallet - used_pallet)
        slot["remaining_sku"] = max(0, payload.max_sku - used_sku)
    if persist:
        _audit("UPSERT", "SLOT_CAPACITY", f"{payload.warehouse_name}|{payload.date}|{payload.slot}", user_email)
        _persist()
    return {"status": "UPDATED", "message": "Kapasite güncellendi."}


def _remove_slot_row(row):
    warehouse_name = row.get("warehouse_name")
    date_key = row.get("date")
    slot_name = row.get("slot")
    if row in MOCK_SLOT_CAPACITY:
        MOCK_SLOT_CAPACITY.remove(row)
    MOCK_SUPPLIER_CAPACITY[:] = [item for item in MOCK_SUPPLIER_CAPACITY if not (item.get("warehouse_name") == warehouse_name and item.get("date") == date_key and item.get("slot") == slot_name)]
    MOCK_SLOT_HOLDS[:] = [item for item in MOCK_SLOT_HOLDS if not (item.get("warehouse_name") == warehouse_name and item.get("slot_date") == date_key and item.get("selected_slot") == slot_name)]
    key = _slot_key(warehouse_name, date_key, slot_name)
    deleted = DOCKOS_SETTINGS.setdefault("deleted_slots", [])
    if key not in deleted:
        deleted.append(key)


def block_slot_dates(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Tarih bloklama için admin yetkisi gereklidir.")
    dates = sorted(set(payload.dates))
    active = [row for row in MOCK_RESERVATIONS if row.get("warehouse_name") == payload.warehouse_name and row.get("slot_date") in dates and row.get("shipment_mode") == "SEVKIYAT" and row.get("status") not in {"CANCELLED", "COMPLETED"}]
    if active:
        numbers = ", ".join(row.get("reservation_no", "-") for row in active[:5])
        raise ValueError(f"Aktif rezervasyonu olan tarihler tamamen bloklanamaz: {numbers}")
    rows = [row for row in MOCK_SLOT_CAPACITY if row.get("warehouse_name") == payload.warehouse_name and row.get("date") in dates]
    for row in rows:
        row["max_pallet"] = 0
        row["max_sku"] = 0
        row["remaining_pallet"] = 0
        row["remaining_sku"] = 0
    MOCK_SUPPLIER_CAPACITY[:] = [row for row in MOCK_SUPPLIER_CAPACITY if not (row.get("warehouse_name") == payload.warehouse_name and row.get("date") in dates)]
    MOCK_SLOT_HOLDS[:] = [row for row in MOCK_SLOT_HOLDS if not (row.get("warehouse_name") == payload.warehouse_name and row.get("slot_date") in dates)]
    _audit("BLOCK_DATES", "SLOT_CAPACITY", payload.warehouse_name, user_email, {"dates": dates, "slots": len(rows)})
    _persist()
    return {"status": "BLOCKED", "count": len(rows), "message": f"{len(dates)} tarih tamamen bloklandı. İsterseniz seçili saatleri yeniden açabilirsiniz."}


def edit_slot_capacity(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Slot düzenleme için admin yetkisi gereklidir.")
    current_slot = _validate_slot_name(payload.current_slot)
    new_slot = _validate_slot_name(payload.new_slot)
    row = next((item for item in MOCK_SLOT_CAPACITY if item.get("warehouse_name") == payload.warehouse_name and item.get("date") == payload.date and item.get("slot") == current_slot), None)
    if not row:
        raise ValueError("Düzenlenecek slot bulunamadı.")
    active = _active_reservations(payload.warehouse_name, payload.date, current_slot)
    if new_slot != current_slot and active:
        raise ValueError("Aktif rezervasyonu bulunan slotun saati değiştirilemez; yalnızca kapasitesi düzenlenebilir.")
    if new_slot != current_slot and any(item.get("warehouse_name") == payload.warehouse_name and item.get("date") == payload.date and item.get("slot") == new_slot for item in MOCK_SLOT_CAPACITY):
        raise ValueError("Yeni saat aralığında zaten bir slot bulunuyor.")
    overlaps = [item for item in MOCK_SLOT_CAPACITY if item is not row and item.get("warehouse_name") == payload.warehouse_name and item.get("date") == payload.date and _slots_overlap(item.get("slot"), new_slot)]
    for item in overlaps:
        conflicting = _active_reservations(payload.warehouse_name, payload.date, item.get("slot"))
        if conflicting:
            numbers = ", ".join(reservation.get("reservation_no", "-") for reservation in conflicting[:5])
            raise ValueError(f"Yeni saat aralığı aktif rezervasyonlu {item.get('slot')} slotuyla çakışıyor: {numbers}")
    allocations = [item for item in MOCK_SUPPLIER_CAPACITY if item.get("warehouse_name") == payload.warehouse_name and item.get("date") == payload.date and item.get("slot") == current_slot]
    minimum_pallet = max(sum(int(item.get("reserved_pallet") or 0) for item in allocations), sum(int(item.get("pallet_count") or 0) for item in active))
    minimum_sku = max(sum(int(item.get("reserved_sku") or 0) for item in allocations), sum(int(item.get("sku_count") or 0) for item in active))
    if payload.max_pallet < minimum_pallet or payload.max_sku < minimum_sku:
        raise ValueError(f"Kapasite mevcut rezervasyon veya ayrımın altına indirilemez. Minimum: {minimum_pallet} palet / {minimum_sku} SKU")
    for item in overlaps:
        _remove_slot_row(item)
    old_key = _slot_key(payload.warehouse_name, payload.date, current_slot)
    if new_slot != current_slot:
        deleted = DOCKOS_SETTINGS.setdefault("deleted_slots", [])
        if old_key not in deleted:
            deleted.append(old_key)
        _restore_deleted_slot(payload.warehouse_name, payload.date, new_slot)
        for item in allocations:
            item["slot"] = new_slot
        for hold in MOCK_SLOT_HOLDS:
            if hold.get("warehouse_name") == payload.warehouse_name and hold.get("slot_date") == payload.date and hold.get("selected_slot") == current_slot:
                hold["selected_slot"] = new_slot
    used_pallet = sum(int(item.get("pallet_count") or 0) for item in active)
    used_sku = sum(int(item.get("sku_count") or 0) for item in active)
    before = dict(row)
    row.update({"slot": new_slot, "max_pallet": payload.max_pallet, "max_sku": payload.max_sku, "remaining_pallet": max(0, payload.max_pallet - used_pallet), "remaining_sku": max(0, payload.max_sku - used_sku)})
    _audit("EDIT", "SLOT_CAPACITY", old_key, user_email, {"before": before, "after": dict(row)})
    _persist()
    return {"status": "UPDATED", "message": "Slot düzenlendi.", "row": row}


def delete_slot_capacity(warehouse_name, date_key, slot_name, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Slot silme için admin yetkisi gereklidir.")
    slot_name = _validate_slot_name(slot_name)
    row = next((item for item in MOCK_SLOT_CAPACITY if item.get("warehouse_name") == warehouse_name and item.get("date") == date_key and item.get("slot") == slot_name), None)
    if not row:
        raise ValueError("Silinecek slot bulunamadı.")
    active = _active_reservations(warehouse_name, date_key, slot_name)
    if active:
        raise ValueError("Aktif rezervasyonu bulunan slot silinemez.")
    key = _slot_key(warehouse_name, date_key, slot_name)
    _remove_slot_row(row)
    _audit("DELETE", "SLOT_CAPACITY", key, user_email)
    _persist()
    return {"status": "DELETED", "message": "Slot kalıcı olarak silindi."}


def _selected_slot_rows(warehouse_name, items):
    keys = sorted({(item.date, _validate_slot_name(item.slot)) for item in items})
    rows = []
    missing = []
    for date_key, slot_name in keys:
        row = next((item for item in MOCK_SLOT_CAPACITY if item.get("warehouse_name") == warehouse_name and item.get("date") == date_key and item.get("slot") == slot_name), None)
        if row:
            rows.append(row)
        else:
            missing.append(f"{date_key} {slot_name}")
    if missing:
        raise ValueError("Seçili slotlardan bazıları bulunamadı: " + ", ".join(missing[:5]))
    return rows


def bulk_edit_slot_capacities(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Toplu slot düzenleme için admin yetkisi gereklidir.")
    rows = _selected_slot_rows(payload.warehouse_name, payload.items)
    prepared = []
    for row in rows:
        date_key = row.get("date")
        slot_name = row.get("slot")
        active = _active_reservations(payload.warehouse_name, date_key, slot_name)
        allocations = [item for item in MOCK_SUPPLIER_CAPACITY if item.get("warehouse_name") == payload.warehouse_name and item.get("date") == date_key and item.get("slot") == slot_name]
        used_pallet = sum(int(item.get("pallet_count") or 0) for item in active)
        used_sku = sum(int(item.get("sku_count") or 0) for item in active)
        minimum_pallet = max(sum(int(item.get("reserved_pallet") or 0) for item in allocations), used_pallet)
        minimum_sku = max(sum(int(item.get("reserved_sku") or 0) for item in allocations), used_sku)
        if payload.max_pallet < minimum_pallet or payload.max_sku < minimum_sku:
            raise ValueError(f"{date_key} {slot_name} kapasitesi mevcut rezervasyon veya ayrımın altına indirilemez. Minimum: {minimum_pallet} palet / {minimum_sku} SKU")
        prepared.append((row, used_pallet, used_sku))
    for row, used_pallet, used_sku in prepared:
        row.update({
            "max_pallet": payload.max_pallet,
            "max_sku": payload.max_sku,
            "remaining_pallet": max(0, payload.max_pallet - used_pallet),
            "remaining_sku": max(0, payload.max_sku - used_sku),
        })
    _audit("BULK_EDIT", "SLOT_CAPACITY", payload.warehouse_name, user_email, {"count": len(rows), "max_pallet": payload.max_pallet, "max_sku": payload.max_sku})
    _persist()
    return {"status": "UPDATED", "count": len(rows), "message": f"Seçilen {len(rows)} slotun kapasitesi güncellendi."}


def bulk_delete_slot_capacities(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Toplu slot silme için admin yetkisi gereklidir.")
    rows = _selected_slot_rows(payload.warehouse_name, payload.items)
    conflicts = []
    for row in rows:
        active = _active_reservations(payload.warehouse_name, row.get("date"), row.get("slot"))
        if active:
            conflicts.append(f"{row.get('date')} {row.get('slot')}")
    if conflicts:
        raise ValueError("Aktif rezervasyonu bulunan seçili slotlar silinemez: " + ", ".join(conflicts[:5]))
    keys = [_slot_key(payload.warehouse_name, row.get("date"), row.get("slot")) for row in rows]
    for row in rows:
        _remove_slot_row(row)
    _audit("BULK_DELETE", "SLOT_CAPACITY", payload.warehouse_name, user_email, {"count": len(rows), "slots": keys})
    _persist()
    return {"status": "DELETED", "count": len(rows), "message": f"Seçilen {len(rows)} slot kalıcı olarak silindi."}


def bulk_update_capacity(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Kapasite yönetimi için admin yetkisi gereklidir.")
    dates = sorted(set(payload.dates))
    slots = sorted({_validate_slot_name(slot_name) for slot_name in payload.slots})
    for index, first in enumerate(slots):
        if any(_slots_overlap(first, second) for second in slots[index + 1:]):
            raise ValueError("Aynı işlemde birbiriyle çakışan iki slot açılamaz.")
    overlaps = []
    for date_key in dates:
        for existing in list(MOCK_SLOT_CAPACITY):
            if existing.get("warehouse_name") != payload.warehouse_name or existing.get("date") != date_key or existing.get("slot") in slots:
                continue
            if not any(_slots_overlap(existing.get("slot"), slot_name) for slot_name in slots):
                continue
            active = _active_reservations(payload.warehouse_name, date_key, existing.get("slot"))
            if active:
                numbers = ", ".join(row.get("reservation_no", "-") for row in active[:5])
                raise ValueError(f"Yeni blokla çakışan aktif rezervasyon var: {existing.get('slot')} ({numbers})")
            overlaps.append(existing)
    for existing in overlaps:
        _remove_slot_row(existing)
    count = 0
    for date_key in dates:
        for slot_name in slots:
            class CapacityPayload:
                pass
            row = CapacityPayload()
            row.warehouse_name = payload.warehouse_name
            row.date = date_key
            row.slot = slot_name
            row.max_pallet = payload.max_pallet
            row.max_sku = payload.max_sku
            update_slot_capacity(row, user_email, user_role, persist=False)
            count += 1
    _audit("BULK_UPSERT", "SLOT_CAPACITY", payload.warehouse_name, user_email, {"count": count, "removed_overlaps": len(overlaps)})
    _persist()
    return {"status": "UPDATED", "count": count, "removed_overlaps": len(overlaps), "message": f"{count} slot kaydedildi; çakışan {len(overlaps)} eski saatlik slot kaldırıldı."}


def _normalize_existing_overlaps():
    removed = 0
    groups = {}
    for row in MOCK_SLOT_CAPACITY:
        groups.setdefault((row.get("warehouse_name"), row.get("date")), []).append(row)
    for (warehouse_name, date_key), group in groups.items():
        anchors = [row for row in group if int(row.get("max_pallet") or 0) + int(row.get("max_sku") or 0) > 0 and (_slot_duration(row.get("slot")) > 60 or not _is_default_hour_slot(row.get("slot")))]
        anchors.sort(key=lambda row: _slot_duration(row.get("slot")), reverse=True)
        for anchor in anchors:
            if anchor not in MOCK_SLOT_CAPACITY:
                continue
            for other in list(group):
                if other is anchor or other not in MOCK_SLOT_CAPACITY or not _slots_overlap(anchor.get("slot"), other.get("slot")):
                    continue
                if not _is_default_hour_slot(other.get("slot")) and _slot_duration(other.get("slot")) >= _slot_duration(anchor.get("slot")):
                    continue
                if _active_reservations(warehouse_name, date_key, other.get("slot")):
                    continue
                _remove_slot_row(other)
                removed += 1
    if removed:
        _audit("MIGRATE", "SLOT_CAPACITY", "OVERLAP_CLEANUP", "system", {"removed": removed})
        _persist()
    return removed


_normalize_existing_overlaps()


def get_settings():
    return DOCKOS_SETTINGS


def update_settings(payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Ayar güncelleme yetkiniz yok.")
    DOCKOS_SETTINGS["supplier_cancel_hours"] = payload.supplier_cancel_hours
    _audit("UPDATE", "SETTINGS", "dockos", user_email, payload.model_dump())
    _persist()
    return {"status": "UPDATED", "message": "İptal kuralı güncellendi.", **DOCKOS_SETTINGS}


def create_manual_po(payload, user_email=None, user_role=None):
    if not is_admin(user_email,user_role): raise PermissionError("Manuel PO yalnızca admin tarafından oluşturulabilir.")
    if any(p["po_number"].casefold()==payload.po_number.casefold() for p in MOCK_PURCHASE_ORDERS): raise ValueError("PO zaten mevcut.")
    row={"po_number":payload.po_number.upper(),"supplier_name":payload.supplier_name,"warehouse_name":payload.warehouse_name,"delivery_date":payload.delivery_date,"status":"OPEN","sku_count":payload.sku_count,"pallet_count":payload.pallet_count,"source":"MANUAL"}
    MOCK_PURCHASE_ORDERS.append(row)
    _audit("CREATE", "PURCHASE_ORDER", row["po_number"], user_email)
    _persist()
    return {"status":"CREATED","message":"Manuel PO oluşturuldu.","row":row}


def update_reservation_status(reservation_no, payload, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Rezervasyon durumu güncelleme yetkiniz yok.")
    reservation = next((row for row in MOCK_RESERVATIONS if row.get("reservation_no") == reservation_no), None)
    if not reservation:
        raise ValueError("Rezervasyon bulunamadı.")
    reservation["status"] = payload.status
    reservation["status_note"] = (payload.note or "").strip()
    _audit("STATUS", "RESERVATION", reservation_no, user_email, payload.model_dump())
    _persist()
    return {"reservation_no": reservation_no, "status": payload.status, "message": "Rezervasyon durumu güncellendi."}


def get_audit_log(limit=200, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Audit kayıtlarını görüntüleme yetkiniz yok.")
    safe_limit = min(max(int(limit or 200), 1), 1000)
    return list(reversed(MOCK_AUDIT_LOG[-safe_limit:]))


def get_notification_outbox(limit=200, user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Bildirim kuyruğunu görüntüleme yetkiniz yok.")
    safe_limit = min(max(int(limit or 200), 1), 1000)
    return list(reversed(MOCK_NOTIFICATION_OUTBOX[-safe_limit:]))


def process_notifications(user_email=None, user_role=None):
    if not is_admin(user_email, user_role):
        raise PermissionError("Bildirim kuyruğunu çalıştırma yetkiniz yok.")
    result = process_due_notifications(MOCK_NOTIFICATION_OUTBOX)
    _audit("PROCESS", "NOTIFICATION_OUTBOX", "due", user_email, result)
    _persist()
    return {"status": "PROCESSED", **result}


def process_notifications_system():
    """Process due mail without an interactive admin request.

    This is used only by the in-process scheduler. The persisted outbox remains
    the source of truth, so a restart does not lose reminders.
    """
    with STATE_LOCK:
        before = [(item.get("key"), item.get("status"), item.get("attempts")) for item in MOCK_NOTIFICATION_OUTBOX]
        result = process_due_notifications(MOCK_NOTIFICATION_OUTBOX)
        after = [(item.get("key"), item.get("status"), item.get("attempts")) for item in MOCK_NOTIFICATION_OUTBOX]
        if result.get("sent") or result.get("failed"):
            _audit("AUTO_PROCESS", "NOTIFICATION_OUTBOX", "due", "system@dockos", result)
        if before != after or result.get("sent") or result.get("failed"):
            _persist()
    return {"status": "PROCESSED", **result}


def _notification_worker():
    interval = max(15, int(os.getenv("DOCKOS_NOTIFICATION_INTERVAL_SECONDS", "60") or 60))
    # Run once shortly after startup, then continuously while the API is alive.
    if not _NOTIFICATION_STOP.wait(2):
        process_notifications_system()
    while not _NOTIFICATION_STOP.wait(interval):
        process_notifications_system()


def start_notification_worker():
    global _NOTIFICATION_THREAD
    if os.getenv("DOCKOS_NOTIFICATION_AUTOMATION", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    with _NOTIFICATION_START_LOCK:
        if _NOTIFICATION_THREAD and _NOTIFICATION_THREAD.is_alive():
            return True
        _NOTIFICATION_STOP.clear()
        _NOTIFICATION_THREAD = Thread(target=_notification_worker, name="dockos-notification-worker", daemon=True)
        _NOTIFICATION_THREAD.start()
    return True


def stop_notification_worker():
    _NOTIFICATION_STOP.set()
    return True


def execute_admin_command(payload, user_email=None, user_role=None):
    if payload.action == "SET_DAILY_PALLET_LIMIT":
        return update_supplier_daily_limit(payload, user_email, user_role)
    raise ValueError("Desteklenmeyen admin komutu.")

def _analytics_rows(user_email=None, user_role=None, supplier_name=None, warehouse_name=None, date_from=None, date_to=None):
    rows = get_reservations(supplier_name, warehouse_name, None, user_email, user_role)
    if date_from:
        rows = [row for row in rows if (row.get("slot_date") or "") >= date_from]
    if date_to:
        rows = [row for row in rows if (row.get("slot_date") or "") <= date_to]
    return rows


def _has_issue(row):
    check = row.get("arrival_check") or {}
    return row.get("status") == "CANCELLED" or check.get("arrived") is False or check.get("on_time") is False or check.get("dock_compatible") is False


def _breakdown(rows, key):
    result = []
    for name in sorted({str(row.get(key) or "Belirtilmedi") for row in rows}):
        selected = [row for row in rows if str(row.get(key) or "Belirtilmedi") == name]
        total = len(selected)
        cancelled = sum(row.get("status") == "CANCELLED" for row in selected)
        late = sum((row.get("arrival_check") or {}).get("on_time") is False for row in selected)
        no_show = sum((row.get("arrival_check") or {}).get("arrived") is False for row in selected)
        incompatible = sum((row.get("arrival_check") or {}).get("dock_compatible") is False for row in selected)
        issue_rows = sum(_has_issue(row) for row in selected)
        result.append({
            "name": name,
            "total": total,
            "active": sum(row.get("status") not in {"CANCELLED", "COMPLETED"} for row in selected),
            "completed": sum(row.get("status") == "COMPLETED" for row in selected),
            "cancelled": cancelled,
            "late": late,
            "no_show": no_show,
            "dock_incompatible": incompatible,
            "success_rate": round(max(0, total - issue_rows) * 100 / total, 1) if total else 0,
        })
    return sorted(result, key=lambda row: (-row["total"], row["name"]))


def get_kpis(user_email=None, user_role=None, supplier_name=None, warehouse_name=None, date_from=None, date_to=None):
    rows = _analytics_rows(user_email, user_role, supplier_name, warehouse_name, date_from, date_to)
    total = len(rows)
    cancelled = sum(row.get("status") == "CANCELLED" for row in rows)
    completed = sum(row.get("status") == "COMPLETED" for row in rows)
    active = sum(row.get("status") not in {"CANCELLED", "COMPLETED"} for row in rows)
    no_show = sum((row.get("arrival_check") or {}).get("arrived") is False for row in rows)
    late = sum((row.get("arrival_check") or {}).get("on_time") is False for row in rows)
    incompatible = sum((row.get("arrival_check") or {}).get("dock_compatible") is False for row in rows)
    evaluated_time = [row for row in rows if (row.get("arrival_check") or {}).get("on_time") is not None]
    on_time = sum((row.get("arrival_check") or {}).get("on_time") is True for row in evaluated_time)

    daily_trend = []
    for day in sorted({row.get("slot_date") for row in rows if row.get("slot_date")}):
        selected = [row for row in rows if row.get("slot_date") == day]
        daily_trend.append({
            "name": day,
            "total": len(selected),
            "late": sum((row.get("arrival_check") or {}).get("on_time") is False for row in selected),
            "no_show": sum((row.get("arrival_check") or {}).get("arrived") is False for row in selected),
            "cancelled": sum(row.get("status") == "CANCELLED" for row in selected),
        })

    status_labels = {"APPROVED": "Onaylı", "REVISION_REQUESTED": "Revizyon", "COMPLETED": "Tamamlandı", "CANCELLED": "İptal"}
    status_breakdown = []
    for status in ["APPROVED", "REVISION_REQUESTED", "COMPLETED", "CANCELLED"]:
        count = sum(row.get("status") == status for row in rows)
        if count or total == 0:
            status_breakdown.append({"name": status_labels[status], "value": count})
    mode_breakdown = [
        {"name": "Sevkiyat", "value": sum(row.get("shipment_mode") == "SEVKIYAT" for row in rows)},
        {"name": "Kargo", "value": sum(row.get("shipment_mode") == "KARGO" for row in rows)},
    ]

    capacity_rows = get_slot_capacity(warehouse_name)
    if date_from:
        capacity_rows = [row for row in capacity_rows if row.get("date", "") >= date_from]
    if date_to:
        capacity_rows = [row for row in capacity_rows if row.get("date", "") <= date_to]
    capacity_max = sum(int(row.get("max_pallet") or 0) for row in capacity_rows)
    capacity_used = sum(max(0, int(row.get("max_pallet") or 0) - int(row.get("remaining_pallet") or 0)) for row in capacity_rows)

    return {
        "total_reservations": total,
        "active_reservations": active,
        "completed": completed,
        "cancelled": cancelled,
        "cancel_rate": round(cancelled * 100 / total, 1) if total else 0,
        "completion_rate": round(completed * 100 / total, 1) if total else 0,
        "on_time_rate": round(on_time * 100 / len(evaluated_time), 1) if evaluated_time else 0,
        "no_show": no_show,
        "late_arrivals": late,
        "dock_incompatible": incompatible,
        "avg_capacity_usage": round(capacity_used * 100 / capacity_max, 1) if capacity_max else 0,
        "supplier_breakdown": _breakdown(rows, "supplier_name"),
        "warehouse_breakdown": _breakdown(rows, "warehouse_name"),
        "daily_trend": daily_trend,
        "status_breakdown": status_breakdown,
        "mode_breakdown": mode_breakdown,
    }


def ask_analytics(payload, user_email=None, user_role=None):
    question = payload.question.strip()
    lowered = question.casefold()
    filters = dict(payload.filters or {})
    locale = filters.pop("locale", "tr") if filters.get("locale") in {"tr", "en", "de", "ar"} else "tr"
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")

    supplier_names = allowed_suppliers(user_email, user_role)
    detected_supplier = next((name for name in sorted(supplier_names, key=len, reverse=True) if name.casefold() in lowered), None)
    warehouse_names = [row.get("warehouse_name") for row in MOCK_WAREHOUSES]
    detected_warehouse = next((name for name in sorted(warehouse_names, key=len, reverse=True) if name and name.casefold() in lowered), None)

    match = re.search(r"(?:son|last|letzte[n]?|خلال آخر)\s+(\d+)\s*(?:gün|days?|tage[n]?|يوم)", lowered)
    month_match = re.search(r"(?:son|last|letzte[n]?|خلال آخر)\s+(\d+)\s*(?:ay|aylık|months?|monate[n]?|شهر)", lowered)
    if match:
        days = min(max(int(match.group(1)), 1), 365)
        date_to = str(date.today())
        date_from = str(date.today() - timedelta(days=days - 1))
    elif month_match:
        days = min(max(int(month_match.group(1)) * 30, 1), 730)
        date_to = str(date.today())
        date_from = str(date.today() - timedelta(days=days - 1))
    elif any(word in lowered for word in ["bugün", "today", "heute", "اليوم"]):
        date_from = date_to = str(date.today())
    elif any(word in lowered for word in ["bu ay", "this month", "diesen monat", "هذا الشهر"]):
        date_to = str(date.today())
        date_from = str(date.today().replace(day=1))

    effective_supplier = detected_supplier or filters.get("supplier_name")
    effective_warehouse = detected_warehouse or filters.get("warehouse_name")

    # Conversational detail intents are evaluated before the chart builder.
    # They deliberately ignore the dashboard's default historical range when
    # the user explicitly asks for the next/upcoming reservation.
    nearest_words = ["en yakın", "en yakin", "yaklaşan", "yaklasan", "sıradaki", "siradaki", "next reservation", "upcoming reservation", "nächste reservierung", "kommende reservierung", "الحجز القادم", "أقرب حجز"]
    if any(word in lowered for word in nearest_words):
        scoped = get_reservations(effective_supplier, effective_warehouse, None, user_email, user_role)
        now_key = str(date.today())
        upcoming = [row for row in scoped if row.get("status") not in {"CANCELLED", "COMPLETED"} and (row.get("slot_date") or row.get("cargo_date") or "") >= now_key]
        upcoming.sort(key=lambda row: (row.get("slot_date") or row.get("cargo_date") or "9999-99-99", row.get("selected_slot") or "99:99", row.get("reservation_no") or ""))
        nearest = upcoming[0] if upcoming else None
        nearest_copy = {
            "tr": {"title":"En Yakın Rezervasyon","none":"Yetkili olduğun kayıtlar içinde yaklaşan aktif rezervasyon bulunamadı.","summary":"En yakın aktif rezervasyon {supplier} tedarikçisine ait: {date} {slot}, {warehouse}, kayıt {no}.","supplier":"Tedarikçi","date":"Tarih / Saat","warehouse":"Merkez Depo","reservation":"Rezervasyon","pallet":"Palet / SKU","plate":"Plaka / Takip"},
            "en": {"title":"Next Reservation","none":"No upcoming active reservation was found within your authorized records.","summary":"The next active reservation belongs to {supplier}: {date} {slot}, {warehouse}, record {no}.","supplier":"Supplier","date":"Date / Time","warehouse":"Distribution Center","reservation":"Reservation","pallet":"Pallets / SKU","plate":"Plate / Tracking"},
            "de": {"title":"Nächste Reservierung","none":"In Ihren berechtigten Datensätzen wurde keine kommende aktive Reservierung gefunden.","summary":"Die nächste aktive Reservierung gehört zu {supplier}: {date} {slot}, {warehouse}, Datensatz {no}.","supplier":"Lieferant","date":"Datum / Zeit","warehouse":"Zentrallager","reservation":"Reservierung","pallet":"Paletten / SKU","plate":"Kennzeichen / Tracking"},
            "ar": {"title":"الحجز القادم","none":"لم يتم العثور على حجز نشط قادم ضمن السجلات المصرح لك بها.","summary":"الحجز النشط القادم تابع للمورد {supplier}: {date} {slot}، {warehouse}، السجل {no}.","supplier":"المورد","date":"التاريخ / الوقت","warehouse":"المستودع المركزي","reservation":"الحجز","pallet":"المنصات / SKU","plate":"اللوحة / التتبع"},
        }[locale]
        if nearest:
            when = nearest.get("slot_date") or nearest.get("cargo_date") or "-"
            slot = nearest.get("selected_slot") or "Kargo"
            summary = nearest_copy["summary"].format(supplier=nearest.get("supplier_name") or "-", date=when, slot=slot, warehouse=nearest.get("warehouse_name") or "-", no=nearest.get("reservation_no") or "-")
            cards = [
                {"label": nearest_copy["supplier"], "value": nearest.get("supplier_name") or "-"},
                {"label": nearest_copy["date"], "value": f"{when} · {slot}"},
                {"label": nearest_copy["warehouse"], "value": nearest.get("warehouse_name") or "-"},
                {"label": nearest_copy["reservation"], "value": nearest.get("reservation_no") or "-"},
                {"label": nearest_copy["pallet"], "value": f"{nearest.get('pallet_count', 0)} / {nearest.get('sku_count', 0)}"},
                {"label": nearest_copy["plate"], "value": nearest.get("vehicle_plate") or nearest.get("cargo_tracking_no") or "-"},
            ]
        else:
            summary = nearest_copy["none"]
            cards = []
        return {
            "question": question, "title": nearest_copy["title"], "summary": summary,
            "dimension": "reservation_detail", "metric": "next_reservation", "visualization": "answer",
            "date_from": None, "date_to": None, "total_records": 1 if nearest else 0,
            "total_value": 1 if nearest else 0, "rows": [], "columns": [], "answer_cards": cards,
            "detected_supplier": effective_supplier, "detected_warehouse": effective_warehouse,
            "engine": "DOCKOS_CONVERSATIONAL_ANALYTICS_V2",
            "suggestions": ["Bu ay kaç rezervasyon var?", "En yakın rezervasyonun plakası nedir?", "Eti'nin yaklaşan rezervasyonunu göster"],
        }

    reservation_match = re.search(r"\bDKS-[A-Z0-9-]+\b", question.upper())
    if reservation_match:
        reservation_no = reservation_match.group(0)
        scoped = get_reservations(effective_supplier, effective_warehouse, None, user_email, user_role)
        row = next((item for item in scoped if str(item.get("reservation_no", "")).upper() == reservation_no), None)
        if not row:
            raise ValueError("Bu rezervasyon bulunamadı veya görüntüleme yetkiniz yok.")
        summary = f"{reservation_no}: {row.get('supplier_name')} · {row.get('warehouse_name')} · {row.get('slot_date') or row.get('cargo_date')} {row.get('selected_slot') or ''} · durum {row.get('status')}."
        return {
            "question": question, "title": "Rezervasyon Detayı", "summary": summary,
            "dimension": "reservation_detail", "metric": "reservation", "visualization": "answer",
            "date_from": None, "date_to": None, "total_records": 1, "total_value": 1, "rows": [], "columns": [],
            "answer_cards": [
                {"label": "Tedarikçi", "value": row.get("supplier_name") or "-"},
                {"label": "Merkez Depo", "value": row.get("warehouse_name") or "-"},
                {"label": "Tarih / Saat", "value": f"{row.get('slot_date') or row.get('cargo_date') or '-'} · {row.get('selected_slot') or '-'}"},
                {"label": "Durum", "value": row.get("status") or "-"},
                {"label": "Plaka / Takip", "value": row.get("vehicle_plate") or row.get("cargo_tracking_no") or "-"},
                {"label": "PO", "value": row.get("po_number") or "-"},
            ],
            "engine": "DOCKOS_CONVERSATIONAL_ANALYTICS_V2", "suggestions": [],
        }

    # Admin komutları önce önizleme üretir; açık onay olmadan veri değiştirilmez.
    limit_match = re.search(r"(?:max(?:imum)?|maksimum|en fazla|limit)\D{0,30}(\d+)\s*palet", lowered)
    if limit_match and any(word in lowered for word in ["uygula", "tanımla", "ayarla", "ver", "limit"]):
        max_pallet = int(limit_match.group(1))
        if "bu ay" in lowered:
            date_from = str(date.today())
            next_month = (date.today().replace(day=28) + timedelta(days=4)).replace(day=1)
            date_to = str(next_month - timedelta(days=1))
        missing = []
        if not is_admin(user_email, user_role):
            missing.append("admin_yetkisi")
        if not effective_supplier:
            missing.append("tedarikçi")
        if not effective_warehouse:
            missing.append("merkez_depo")
        if not date_from or not date_to:
            missing.append("tarih")
        action_dates = []
        if date_from and date_to:
            cursor = date.fromisoformat(date_from)
            last = date.fromisoformat(date_to)
            while cursor <= last and len(action_dates) < 366:
                action_dates.append(str(cursor))
                cursor += timedelta(days=1)
        summary = "Komutu uygulamadan önce eksik alanları tamamla: " + ", ".join(missing) if missing else f"{effective_supplier} için {effective_warehouse} deposunda {date_from}–{date_to} arasında günlük maksimum {max_pallet} palet limiti uygulanacak."
        return {
            "question": question,
            "title": "Admin Kapasite Komutu Önizlemesi",
            "summary": summary,
            "dimension": "admin_action",
            "metric": "daily_pallet_limit",
            "visualization": "action",
            "date_from": date_from,
            "date_to": date_to,
            "total_records": 0,
            "total_value": max_pallet,
            "rows": [],
            "columns": [],
            "confirmation_required": not missing,
            "missing_fields": missing,
            "action_preview": None if missing else {"action": "SET_DAILY_PALLET_LIMIT", "warehouse_name": effective_warehouse, "supplier_name": effective_supplier, "dates": action_dates, "max_pallet": max_pallet},
            "engine": "DOCKOS_SAFE_ADMIN_COMMAND_V2",
            "suggestions": ["Eti için Ankara DC'de bu ay maksimum 20 palet limiti uygula"],
        }

    rows = _analytics_rows(user_email, user_role, effective_supplier, effective_warehouse, date_from, date_to)
    if any(word in lowered for word in ["depo", "merkez"]):
        dimension, dimension_label = "warehouse_name", "Merkez Depo"
    elif any(word in lowered for word in ["gün", "tarih", "trend"]):
        dimension, dimension_label = "slot_date", "Tarih"
    elif any(word in lowered for word in ["durum", "statü"]):
        dimension, dimension_label = "status", "Durum"
    elif any(word in lowered for word in ["kargo", "sevkiyat tür", "gönderim"]):
        dimension, dimension_label = "shipment_mode", "Gönderim Türü"
    else:
        dimension, dimension_label = "supplier_name", "Tedarikçi"

    if "geç" in lowered:
        metric, metric_label = "late", "Geç Geliş"
        predicate = lambda row: (row.get("arrival_check") or {}).get("on_time") is False
    elif "no-show" in lowered or "no show" in lowered or "gelmeyen" in lowered:
        metric, metric_label = "no_show", "No-show"
        predicate = lambda row: (row.get("arrival_check") or {}).get("arrived") is False
    elif "iptal" in lowered:
        metric, metric_label = "cancelled", "İptal"
        predicate = lambda row: row.get("status") == "CANCELLED"
    elif "tamam" in lowered:
        metric, metric_label = "completed", "Tamamlanan"
        predicate = lambda row: row.get("status") == "COMPLETED"
    elif "rampa" in lowered or "uyumsuz" in lowered:
        metric, metric_label = "dock_incompatible", "Rampa Uyumsuzluğu"
        predicate = lambda row: (row.get("arrival_check") or {}).get("dock_compatible") is False
    else:
        metric, metric_label = "total", "Rezervasyon"
        predicate = lambda row: True

    grouped = {}
    totals = {}
    labels = {"APPROVED": "Onaylı", "REVISION_REQUESTED": "Revizyon", "COMPLETED": "Tamamlandı", "CANCELLED": "İptal", "SEVKIYAT": "Sevkiyat", "KARGO": "Kargo"}
    for row in rows:
        raw_name = str(row.get(dimension) or "Belirtilmedi")
        name = labels.get(raw_name, raw_name)
        totals[name] = totals.get(name, 0) + 1
        if predicate(row):
            grouped[name] = grouped.get(name, 0) + 1
    report_rows = [{"name": name, "value": grouped.get(name, 0), "total": total, "rate": round(grouped.get(name, 0) * 100 / total, 1) if total else 0} for name, total in totals.items()]
    report_rows.sort(key=lambda item: (-item["value"], item["name"]))
    total_value = sum(item["value"] for item in report_rows)
    top = report_rows[0] if report_rows else None
    visualization = "line" if dimension == "slot_date" else "donut" if dimension in {"status", "shipment_mode"} else "bar"
    all_scoped_rows = get_reservations(effective_supplier, effective_warehouse, None, user_email, user_role) if effective_supplier else []
    future_rows = [row for row in all_scoped_rows if (row.get("slot_date") or "") > str(date_to or date.today()) and row.get("status") != "CANCELLED"]
    outside_rows = [row for row in all_scoped_rows if row not in rows]
    prefix = f"{effective_supplier} için " if effective_supplier else ""
    summary = f"{prefix}{date_from or 'başlangıç'}–{date_to or 'bugün'} döneminde {len(rows)} kayıt içinde {total_value} {metric_label.lower()} bulundu."
    if top and top["value"]:
        summary += f" En yüksek değer {top['name']}: {top['value']} (%{top['rate']})."
    context_notes = []
    if future_rows:
        context_notes.append(f"Filtre bitiş tarihinden sonra {len(future_rows)} aktif/gelecek rezervasyon var; performans hesabına dahil edilmedi.")
    elif outside_rows and not rows:
        context_notes.append(f"Tedarikçi için toplam {len(all_scoped_rows)} kayıt var ancak seçili dönemin dışında.")
    if context_notes:
        summary += " " + " ".join(context_notes)
    return {
        "question": question,
        "title": f"{dimension_label} Bazında {metric_label} Raporu",
        "summary": summary,
        "dimension": dimension,
        "metric": metric,
        "visualization": visualization,
        "date_from": date_from,
        "date_to": date_to,
        "total_records": len(rows),
        "total_value": total_value,
        "detected_supplier": effective_supplier,
        "detected_warehouse": effective_warehouse,
        "context_notes": context_notes,
        "rows": report_rows,
        "columns": [dimension_label, metric_label, "Toplam Kayıt", "Oran"],
        "engine": "DOCKOS_CONVERSATIONAL_ANALYTICS_V2",
        "suggestions": ["Son 7 gün geç gelen tedarikçileri göster", "Bu ay depo bazında iptal raporu ver", "Gönderim türüne göre rezervasyon dağılımını göster"],
    }
