from copy import deepcopy
from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from math import asin, cos, radians, sin, sqrt
import os
from pathlib import Path
from secrets import token_urlsafe
import sqlite3
from threading import Lock
from zoneinfo import ZoneInfo

from . import persistence
from .attestation import AttestationError, verify as verify_attestation
from .pii import decrypt as decrypt_pii, encrypt as encrypt_pii


_WAREHOUSE_DATA_PATH = Path(__file__).resolve().parent / "data" / "warehouses.json"
_WAREHOUSE_SEED = json.loads(_WAREHOUSE_DATA_PATH.read_text(encoding="utf-8"))
_WAREHOUSES = {row["id"]: row for row in _WAREHOUSE_SEED}
# Backward-compatible ids used by the demo rows; coordinates still come from
# the validated corporate warehouse source.
_WAREHOUSES["fulya"] = next(row for row in _WAREHOUSE_SEED if row["name"] == "Fulya (İstanbul)")
_WAREHOUSES["uskudar"] = next(row for row in _WAREHOUSE_SEED if row["name"] == "Üsküdar (İstanbul)")

_TODAY_ISTANBUL = datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()

_RULES = [
    {"id": "dailyMax-v1", "engine_key": "dailyMax", "title": "Günlük azami net çalışma", "value": 660, "level": "Sert blok", "effective_from": "2026-01-01", "active": True},
    {"id": "betweenShifts-v1", "engine_key": "betweenShifts", "title": "Vardiyalar arası dinlenme", "value": 660, "level": "Sert blok", "effective_from": "2026-01-01", "active": True},
    {"id": "breakShort-v1", "engine_key": "breakShort", "title": "0-4 saat çalışma molası", "value": 15, "level": "Otomatik", "effective_from": "2026-01-01", "active": True},
    {"id": "breakMedium-v1", "engine_key": "breakMedium", "title": "4-7,5 saat çalışma molası", "value": 30, "level": "Otomatik", "effective_from": "2026-01-01", "active": True},
    {"id": "breakLong-v1", "engine_key": "breakLong", "title": "7,5 saat üzeri çalışma molası", "value": 60, "level": "Otomatik", "effective_from": "2026-01-01", "active": True},
]

_AUDIT_LOCK = Lock()
_AUDIT_DB_PATH = Path(os.getenv("WORKFORCE_AUDIT_DB", str(Path(__file__).resolve().parents[3] / "data" / "workforce_audit.db")))

_DEVICE_BINDINGS = [
    {"person_id": "100184", "device_id": "DEVICE-1", "device_key_id": "legacy-test-key-1", "status": "ACTIVE", "signed_challenge_required": False, "attestation_provider": "LEGACY_TEST"},
    {"person_id": "100221", "device_id": "DEV-4418", "device_key_id": "seed-key-4418", "status": "ACTIVE", "signed_challenge_required": False, "attestation_provider": "SEED"},
    {"person_id": "100287", "device_id": "DEV-7781", "device_key_id": "seed-key-7781", "status": "ACTIVE", "signed_challenge_required": False, "attestation_provider": "SEED"},
]

_ENROLLMENT_TOKENS: dict[str, dict] = {}

_CORRECTION_REQUESTS: list[dict] = []
_LEAVE_REQUESTS: list[dict] = []
_ANNOUNCEMENTS: list[dict] = []
_ANNOUNCEMENT_RECEIPTS: list[dict] = []
_FEATURE_FLAGS: dict = {
    "breaks": True, "leave_requests": True, "appeals": True,
    "announcements": True, "notifications": True, "archive": True,
    "manager_tasks": True, "qr_check_in": False, "live_break_activity": True,
    "employee_experience": True,
}
_NOTIFICATION_POLICY: dict = {
    "shift_published": True,
    "check_in_reminder": True,
    "check_in_reminder_minutes": 15,
    "check_out_reminder": True,
    "check_out_reminder_minutes": 15,
}
_NOTIFICATIONS: list[dict] = []
_BREAK_SESSIONS: list[dict] = []
_PEOPLE: list[dict] = []
_LEAVES: list[dict] = []


_STATE_COLLECTIONS = {
    "rules": _RULES,
    "devices": _DEVICE_BINDINGS,
    "correction_requests": _CORRECTION_REQUESTS,
    "leave_requests": _LEAVE_REQUESTS,
    "announcements": _ANNOUNCEMENTS,
    "announcement_receipts": _ANNOUNCEMENT_RECEIPTS,
    "notifications": _NOTIFICATIONS,
    "break_sessions": _BREAK_SESSIONS,
    "people": _PEOPLE,
    "leaves": _LEAVES,
}


def _persist_state() -> None:
    if not persistence.ENABLED:
        return
    for kind, rows in _STATE_COLLECTIONS.items():
        persistence.replace_collection(kind, rows)
    persistence.replace_collection("shifts", _SHIFTS)
    persistence.replace_collection("attendance", _ATTENDANCE)
    persistence.replace_collection("warehouses", _WAREHOUSE_SEED)
    persistence.save_document("feature_flags", _FEATURE_FLAGS)
    persistence.save_document("notification_policy", _NOTIFICATION_POLICY)
    persistence.save_document("enrollment_tokens", _ENROLLMENT_TOKENS)


def initialize_workforce() -> None:
    """Create schema and hydrate process state from PostgreSQL once."""
    persistence.initialize()
    if not persistence.ENABLED:
        return
    stored_shifts = persistence.load_collection("shifts")
    if not stored_shifts:
        _persist_state()
        return
    for kind, target in _STATE_COLLECTIONS.items():
        target[:] = persistence.load_collection(kind)
    _SHIFTS[:] = stored_shifts
    _ATTENDANCE[:] = persistence.load_collection("attendance")
    _FEATURE_FLAGS.clear()
    _FEATURE_FLAGS.update({key: value for key, value in persistence.load_document("feature_flags", _FEATURE_FLAGS).items() if key != "id"})
    _NOTIFICATION_POLICY.clear()
    _NOTIFICATION_POLICY.update({key: value for key, value in persistence.load_document("notification_policy", _NOTIFICATION_POLICY).items() if key != "id"})
    _ENROLLMENT_TOKENS.clear()
    _ENROLLMENT_TOKENS.update({key: value for key, value in persistence.load_document("enrollment_tokens", {}).items() if key != "id"})


def list_warehouses() -> list[dict]:
    return deepcopy(_WAREHOUSE_SEED)


def upsert_warehouse(payload: dict, actor: str) -> dict:
    now = datetime.now(UTC)
    warehouse_id = payload.get("id") or f"WH-{now.strftime('%Y%m%d%H%M%S%f')}"
    record = {**payload, "id": warehouse_id, "updated_at": now.isoformat(), "updated_by": actor, "coordinate_source": payload.get("coordinate_source", "admin")}
    existing = next((item for item in _WAREHOUSE_SEED if item["id"] == warehouse_id), None)
    if existing:
        before = deepcopy(existing); existing.update(record); record = existing; event = "WAREHOUSE_UPDATED"
    else:
        before = None; _WAREHOUSE_SEED.append(record); event = "WAREHOUSE_CREATED"
    _WAREHOUSES[warehouse_id] = record
    _append_audit(event, actor, record_id=warehouse_id, before=before, after=deepcopy(record))
    return deepcopy(record)


def bulk_patch_warehouses(ids: list[str], patch: dict, actor: str) -> list[dict]:
    changed = []
    values = {key: value for key, value in patch.items() if value is not None}
    for item in _WAREHOUSE_SEED:
        if item["id"] in ids:
            item.update(values); item["updated_at"] = datetime.now(UTC).isoformat(); item["updated_by"] = actor; changed.append(item)
    _append_audit("WAREHOUSES_BULK_UPDATED", actor, record_ids=ids, patch=values, changed=len(changed))
    return deepcopy(changed)


def upsert_people(rows: list[dict], actor: str) -> dict:
    created = updated = 0
    roster_conflicts: list[dict] = []
    by_tckn_hash = {item.get("tckn_hash"): item for item in _PEOPLE if item.get("tckn_hash")}
    by_employee_id = {str(item.get("employee_id")): item for item in _PEOPLE if item.get("employee_id") is not None}
    roster_owner = {
        str(roster_id): item
        for item in _PEOPLE
        for roster_id in item.get("roster_ids", [])
        if str(roster_id).strip()
    }
    for payload in rows:
        payload = deepcopy(payload)
        employee_id = payload["employee_id"]
        incoming_roster_ids = list(dict.fromkeys(
            str(value).strip() for value in payload.pop("roster_ids", []) if str(value).strip()
        ))
        tckn = payload.pop("tckn")
        tckn_hash = sha256(tckn.encode()).hexdigest()
        existing = by_tckn_hash.get(tckn_hash)
        if existing is None:
            existing = by_employee_id.get(str(employee_id))
        canonical_employee_id = existing["employee_id"] if existing else employee_id
        accepted_roster_ids = []
        for roster_id in incoming_roster_ids:
            owner = roster_owner.get(roster_id)
            if owner is existing:
                owner = None
            if owner:
                roster_conflicts.append({"roster_id": roster_id, "employee_id": canonical_employee_id, "existing_employee_id": owner["employee_id"]})
            else:
                accepted_roster_ids.append(roster_id)
                roster_owner[roster_id] = existing or payload
        roster_ids = list(dict.fromkeys([*(existing or {}).get("roster_ids", []), *accepted_roster_ids]))
        protected = {
            **payload,
            "id": canonical_employee_id,
            "employee_id": canonical_employee_id,
            "roster_ids": roster_ids,
            "source_employee_id": employee_id if employee_id != canonical_employee_id else payload.get("source_employee_id"),
            "tckn_hash": tckn_hash,
            "tckn_ciphertext": encrypt_pii(tckn, canonical_employee_id),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": actor,
        }
        if existing:
            existing.update(protected)
            updated += 1
        else:
            protected["created_at"] = protected["updated_at"]
            _PEOPLE.append(protected)
            existing = protected
            created += 1
        by_tckn_hash[tckn_hash] = existing
        by_employee_id[str(canonical_employee_id)] = existing
        for roster_id in roster_ids:
            roster_owner[roster_id] = existing
    _append_audit("PEOPLE_BULK_UPSERTED", actor, created=created, updated=updated, count=len(rows), roster_conflict_count=len(roster_conflicts))
    return {"created": created, "updated": updated, "total": len(rows), "roster_conflicts": roster_conflicts}


def update_employment_lifecycle(rows: list[dict], actor: str, file_name: str = "") -> dict:
    matched = unmatched = 0
    for payload in rows:
        person = next((item for item in _PEOPLE if item.get("employee_id") == payload["person_id"]), None)
        if person is None:
            unmatched += 1
            continue
        if payload.get("employment_start"):
            person["employment_start"] = payload["employment_start"]
        if payload.get("employment_end"):
            person["employment_end"] = payload["employment_end"]
            person["active"] = False
        person["updated_at"] = datetime.now(UTC).isoformat()
        person["updated_by"] = actor
        matched += 1
    _append_audit("EMPLOYMENT_LIFECYCLE_IMPORTED", actor, file_name=file_name, matched=matched, unmatched=unmatched)
    return {"matched": matched, "unmatched": unmatched, "total": len(rows)}


def list_people(can_view_sensitive: bool = False) -> list[dict]:
    result = []
    for item in _PEOPLE:
        row = {key: value for key, value in item.items() if key not in {"tckn_ciphertext", "tckn_hash"}}
        try:
            tckn = decrypt_pii(item["tckn_ciphertext"], item["employee_id"])
        except Exception:
            tckn = None
        row["tckn"] = tckn if can_view_sensitive else (f"{tckn[:2]}*******{tckn[-2:]}" if tckn and len(tckn) >= 4 else "****")
        result.append(row)
    return deepcopy(result)


def list_leaves() -> list[dict]:
    return deepcopy(_LEAVES)


def import_leaves(rows: list[dict], actor: str, file_name: str = "") -> dict:
    existing_keys = {(str(item.get("person_id")), str(item.get("date"))) for item in _LEAVES}
    inserted = skipped = 0
    for payload in rows:
        key = (str(payload["person_id"]), str(payload["date"]))
        if key in existing_keys:
            skipped += 1
            continue
        record = {**deepcopy(payload), "entered_by": actor, "entered_at": datetime.now(UTC).isoformat()}
        _LEAVES.append(record)
        existing_keys.add(key)
        inserted += 1
    _append_audit("TIME_OFF_IMPORTED", actor, file_name=file_name, inserted=inserted, skipped=skipped)
    return {"inserted": inserted, "skipped": skipped, "total": len(rows)}


def _audit_connection() -> sqlite3.Connection:
    _AUDIT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_AUDIT_DB_PATH, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS workforce_audit (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        at TEXT NOT NULL,
        event TEXT NOT NULL,
        actor TEXT NOT NULL,
        record_json TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        hash TEXT NOT NULL UNIQUE
        )"""
    )
    connection.execute("CREATE TRIGGER IF NOT EXISTS workforce_audit_no_update BEFORE UPDATE ON workforce_audit BEGIN SELECT RAISE(ABORT, 'workforce audit is append-only'); END")
    connection.execute("CREATE TRIGGER IF NOT EXISTS workforce_audit_no_delete BEFORE DELETE ON workforce_audit BEGIN SELECT RAISE(ABORT, 'workforce audit is append-only'); END")
    return connection


def _append_audit(event: str, actor: str, **details: object) -> dict:
    postgres_record = persistence.append_audit(event, actor, **details)
    if postgres_record is not None:
        _persist_state()
        return deepcopy(postgres_record)
    with _AUDIT_LOCK, closing(_audit_connection()) as connection:
        previous = connection.execute("SELECT hash FROM workforce_audit ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = previous[0] if previous else "GENESIS"
        record = {
            "id": f"AUD-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            "at": datetime.now(UTC).isoformat(),
            "event": event,
            "actor": actor,
            "previous_hash": previous_hash,
            **details,
        }
        canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        record["hash"] = sha256(f"{previous_hash}|{canonical}".encode("utf-8")).hexdigest()
        connection.execute(
            "INSERT INTO workforce_audit (id, at, event, actor, record_json, previous_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record["id"], record["at"], event, actor, json.dumps(record, ensure_ascii=False, sort_keys=True), previous_hash, record["hash"]),
        )
        connection.commit()
        return deepcopy(record)


def list_audit(limit: int = 500) -> list[dict]:
    postgres_rows = persistence.list_audit(max(1, min(limit, 5000)))
    if postgres_rows is not None:
        return postgres_rows
    with _AUDIT_LOCK, closing(_audit_connection()) as connection:
        rows = connection.execute("SELECT record_json FROM workforce_audit ORDER BY sequence DESC LIMIT ?", (max(1, min(limit, 5000)),)).fetchall()
    return [json.loads(row[0]) for row in rows]


def list_rules() -> list[dict]:
    return deepcopy(_RULES)


def _rule_value(engine_key: str, effective_date: str, fallback: int) -> int:
    versions = sorted(
        (row for row in _RULES if row["engine_key"] == engine_key and row["active"] and row["effective_from"] <= effective_date),
        key=lambda row: row["effective_from"],
        reverse=True,
    )
    return int(versions[0]["value"] if versions else fallback)


def create_rule_version(payload: dict, actor: str) -> dict:
    now = datetime.now(UTC)
    for row in _RULES:
        if row["engine_key"] == payload["engine_key"] and row["active"]:
            row["active"] = False
            row["superseded_at"] = now.isoformat()
    record = {"id": f"RULE-{now.strftime('%Y%m%d%H%M%S%f')}", **payload, "active": True, "created_at": now.isoformat(), "created_by": actor}
    _RULES.append(record)
    _append_audit("RULE_VERSION_CREATED", actor, record_id=record["id"], engine_key=record["engine_key"], value=record["value"], effective_from=record["effective_from"])
    return deepcopy(record)

_SHIFTS = [
    {"id": "SHIFT-1407-001", "person_id": "100184", "person_name": "Erdi Aydın", "warehouse_id": "fulya", "date": _TODAY_ISTANBUL, "start": "08:00", "end": "17:00", "break_minutes": 60, "role": "Picker", "status": "Atandı"},
    {"id": "SHIFT-1407-002", "person_id": "100221", "person_name": "Efe Yılmaz", "warehouse_id": "fulya", "date": _TODAY_ISTANBUL, "start": "07:00", "end": "16:00", "break_minutes": 60, "role": "Picker", "status": "Tamamlandı"},
    {"id": "SHIFT-1407-003", "person_id": "100287", "person_name": "Kerim Atayolu", "warehouse_id": "uskudar", "date": _TODAY_ISTANBUL, "start": "08:00", "end": "17:00", "break_minutes": 60, "role": "Picker", "status": "Tamamlandı"},
]


class WorkforceRuleError(ValueError):
    """Raised when a server-side workforce rule blocks an operation."""


_ATTENDANCE = [
    {
        "id": "ATT-1407-002",
        "person_id": "100221",
        "name": "Efe Yılmaz",
        "warehouse": "Fulya (İstanbul)",
        "date": "14.07.2026",
        "planned": "07:00–16:00",
        "check_in": "06:58",
        "check_out": "16:11",
        "break_minutes": 60,
        "net_minutes": 493,
        "expected_minutes": 480,
        "missing_minutes": 0,
        "overtime_minutes": 13,
        "status": "Tamamlandı",
        "approval": "Onay bekliyor",
        "source": "Mobil",
        "audit": [],
    },
    {
        "id": "ATT-1407-003",
        "person_id": "100287",
        "name": "Kerim Atayolu",
        "warehouse": "Üsküdar (İstanbul)",
        "date": "14.07.2026",
        "planned": "08:00–17:00",
        "check_in": "08:24",
        "check_out": "16:42",
        "break_minutes": 60,
        "net_minutes": 438,
        "expected_minutes": 480,
        "missing_minutes": 42,
        "overtime_minutes": 0,
        "status": "Eksik çalışma",
        "approval": "İnceleme gerekli",
        "source": "Mobil",
        "audit": [],
    },
]


def list_attendance() -> list[dict]:
    return deepcopy(_ATTENDANCE)


def _attendance_iso_date(value: str) -> str:
    text = str(value or "")
    if len(text) == 10 and text[4] == "-":
        return text
    parts = text.split(".")
    return f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else text


def import_attendance(rows: list[dict], actor: str, file_name: str = "") -> dict:
    inserted = updated = protected = 0
    for payload in rows:
        existing = next(
            (item for item in _ATTENDANCE if str(item.get("person_id")) == str(payload["person_id"]) and _attendance_iso_date(item.get("date")) == _attendance_iso_date(payload["date"])),
            None,
        )
        if existing and not str(existing.get("source", "")).startswith("Puantaj Dosyası"):
            protected += 1
            continue
        record = {**deepcopy(payload), "imported_by": actor, "imported_at": datetime.now(UTC).isoformat(), "audit": deepcopy(existing.get("audit", [])) if existing else []}
        record["audit"].append({"event": "ATTENDANCE_FILE_IMPORTED", "actor": actor, "at": record["imported_at"], "file_name": file_name})
        if existing:
            existing.clear()
            existing.update(record)
            updated += 1
        else:
            _ATTENDANCE.append(record)
            inserted += 1
    _append_audit("ATTENDANCE_FILE_IMPORTED", actor, file_name=file_name, inserted=inserted, updated=updated, protected=protected)
    return {"inserted": inserted, "updated": updated, "protected": protected, "total": len(rows)}


def list_shifts(person_id: str | None = None, date: str | None = None) -> list[dict]:
    rows = _SHIFTS
    if person_id:
        rows = [row for row in rows if row["person_id"] == person_id]
    if date:
        rows = [row for row in rows if row["date"] == date]
    return deepcopy(rows)


def _gross_shift_minutes(start: str, end: str) -> int:
    return ((_minutes(end) or 0) - (_minutes(start) or 0)) % (24 * 60)


def _minimum_break_minutes(start: str, end: str, effective_date: str) -> int:
    gross = _gross_shift_minutes(start, end)
    if gross <= 240:
        return _rule_value("breakShort", effective_date, 15)
    if gross <= 450:
        return _rule_value("breakMedium", effective_date, 30)
    return _rule_value("breakLong", effective_date, 60)


def _shift_interval(row: dict) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(f'{row["date"]}T{row["start"]}:00+03:00')
    end = datetime.fromisoformat(f'{row["date"]}T{row["end"]}:00+03:00')
    if end <= start:
        from datetime import timedelta
        end += timedelta(days=1)
    return start, end


def create_shift(payload: dict, actor: str) -> dict:
    warehouse = _WAREHOUSES.get(payload["warehouse_id"])
    if warehouse is None:
        raise WorkforceRuleError("Depo konumu bulunamadı.")
    duplicate = next(
        (row for row in _SHIFTS if row["person_id"] == payload["person_id"] and row["date"] == payload["date"] and row["status"] != "İptal"),
        None,
    )
    if duplicate:
        raise WorkforceRuleError("Personelin bu tarihte aktif bir vardiyası zaten var.")
    payload["break_minutes"] = max(payload["break_minutes"], _minimum_break_minutes(payload["start"], payload["end"], payload["date"]))
    expected_minutes = _gross_shift_minutes(payload["start"], payload["end"]) - payload["break_minutes"]
    if expected_minutes > _rule_value("dailyMax", payload["date"], 660):
        raise WorkforceRuleError("Günlük azami 11 saat net çalışma kuralı aşılıyor.")
    candidate_start, candidate_end = _shift_interval(payload)
    for existing in _SHIFTS:
        if existing["person_id"] != payload["person_id"] or existing["status"] == "İptal":
            continue
        existing_start, existing_end = _shift_interval(existing)
        gap = (candidate_start - existing_end).total_seconds() / 60 if candidate_start >= existing_end else (existing_start - candidate_end).total_seconds() / 60 if existing_start >= candidate_end else -1
        if gap < _rule_value("betweenShifts", payload["date"], 660):
            raise WorkforceRuleError("Vardiyalar arasında en az 11 saat dinlenme olmalıdır.")
    row = {
        "id": f"SHIFT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
        **payload,
        "warehouse": warehouse["name"],
        "status": "Atandı",
        "created_by": actor,
        "created_at": datetime.now(UTC).isoformat(),
        "expected_minutes": expected_minutes,
    }
    _SHIFTS.append(row)
    _schedule_shift_notifications(row, actor)
    _append_audit("SHIFT_CREATED", actor, record_id=row["id"], person_id=row["person_id"], warehouse_id=row["warehouse_id"])
    return deepcopy(row)


def _schedule_shift_notifications(shift: dict, actor: str) -> list[dict]:
    start, end = _shift_interval(shift)
    now = datetime.now(UTC)
    rows: list[dict] = []
    if _NOTIFICATION_POLICY["shift_published"]:
        rows.append({"type": "SHIFT_PUBLISHED", "title": "Vardiyanız yayınlandı", "scheduled_at": now.isoformat()})
    if _NOTIFICATION_POLICY["check_in_reminder"]:
        rows.append({"type": "CHECK_IN_REMINDER", "title": "Check-in yapmayı unutmayın", "scheduled_at": (start - timedelta(minutes=_NOTIFICATION_POLICY["check_in_reminder_minutes"])).astimezone(UTC).isoformat()})
    if _NOTIFICATION_POLICY["check_out_reminder"]:
        rows.append({"type": "CHECK_OUT_REMINDER", "title": "Check-out yapmayı unutmayın", "scheduled_at": (end - timedelta(minutes=_NOTIFICATION_POLICY["check_out_reminder_minutes"])).astimezone(UTC).isoformat()})
    for index, notification in enumerate(rows):
        binding = next((item for item in _DEVICE_BINDINGS if item["person_id"] == shift["person_id"] and item["status"] == "ACTIVE"), {})
        notification.update({"id": f"NTF-{shift['id']}-{index}", "person_id": shift["person_id"], "shift_id": shift["id"], "message": f"{shift['warehouse']} · {shift['date']} · {shift['start']}–{shift['end']}", "created_at": now.isoformat(), "created_by": actor, "read": False, "platform": binding.get("platform"), "push_token": binding.get("push_token")})
        persistence.enqueue_notification(notification)
    _NOTIFICATIONS[0:0] = rows
    return deepcopy(rows)


def list_notifications(person_id: str | None = None) -> list[dict]:
    rows = _NOTIFICATIONS if not person_id else [row for row in _NOTIFICATIONS if row["person_id"] == person_id]
    return deepcopy(rows)


def _distance_meters(latitude_1: float, longitude_1: float, latitude_2: float, longitude_2: float) -> float:
    radius = 6_371_000
    lat_1, lat_2 = radians(latitude_1), radians(latitude_2)
    delta_lat = lat_2 - lat_1
    delta_lon = radians(longitude_2 - longitude_1)
    value = sin(delta_lat / 2) ** 2 + cos(lat_1) * cos(lat_2) * sin(delta_lon / 2) ** 2
    return 2 * radius * asin(sqrt(value))


def _validate_device(payload: dict) -> dict:
    if not payload["device_trusted"]:
        raise WorkforceRuleError("Cihaz kayıtlı veya güvenilir değil.")
    binding = next((row for row in _DEVICE_BINDINGS if row["person_id"] == payload["person_id"] and row["device_id"] == payload["device_id"] and row["status"] == "ACTIVE"), None)
    if binding is None:
        raise WorkforceRuleError("Bu cihaz personele kayıtlı değil veya sıfırlama sonrası iptal edildi.")
    if binding.get("signed_challenge_required"):
        if payload.get("device_key_id") != binding.get("device_key_id") or not payload.get("challenge_id") or not payload.get("signature"):
            raise WorkforceRuleError("Cihaz imzası veya tek kullanımlık doğrulama challenge değeri geçersiz.")
    return binding


def _validate_presence(warehouse: dict, payload: dict) -> float:
    _validate_device(payload)
    if payload["accuracy_meters"] > warehouse["max_accuracy"]:
        raise WorkforceRuleError("GPS doğruluğu depo kuralının dışında.")
    distance = _distance_meters(payload["latitude"], payload["longitude"], warehouse["latitude"], warehouse["longitude"])
    if distance > warehouse["radius"]:
        raise WorkforceRuleError("Depo konumunun dışındasınız; işlem yapılamaz.")
    return distance


def _validate_local_authentication(payload: dict) -> None:
    """Validate a device-local user-presence assertion without biometric data.

    The mobile client must bind this result to the already required signed,
    single-use device challenge. Face images/templates never reach Workforce.
    """
    method = payload.get("local_auth_method", "NONE")
    if method == "NONE":
        if os.getenv("WORKFORCE_REQUIRE_LOCAL_AUTH", "false").lower() == "true":
            raise WorkforceRuleError("İşlem için cihaz üzerinde Face ID, biyometri veya cihaz parolası doğrulaması gerekir.")
        return
    authenticated_at = payload.get("local_auth_at")
    if authenticated_at is None:
        raise WorkforceRuleError("Yerel kullanıcı doğrulama zamanı eksik.")
    if isinstance(authenticated_at, str):
        authenticated_at = datetime.fromisoformat(authenticated_at.replace("Z", "+00:00"))
    if authenticated_at.tzinfo is None:
        authenticated_at = authenticated_at.replace(tzinfo=UTC)
    age_seconds = abs((datetime.now(UTC) - authenticated_at.astimezone(UTC)).total_seconds())
    if age_seconds > 120:
        raise WorkforceRuleError("Yerel kullanıcı doğrulaması eskimiş; tekrar doğrulayın.")


def check_in(shift_id: str, payload: dict, actor: str) -> dict:
    shift = next((row for row in _SHIFTS if row["id"] == shift_id and row["status"] != "İptal"), None)
    if shift is None:
        raise WorkforceRuleError("Atanmış vardiya bulunamadı; check-in yapılamaz.")
    if shift["person_id"] != payload["person_id"]:
        raise WorkforceRuleError("Bu vardiya başka bir personele atanmış.")
    pilot_date_override = bool(payload.get("pilot_simulation")) and os.getenv("DOCKOS_ENV", "development").lower() != "production"
    if shift["date"] != datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat() and not pilot_date_override:
        raise WorkforceRuleError("Yalnızca bugünkü atanmış vardiya için check-in yapılabilir.")
    warehouse = _WAREHOUSES[shift["warehouse_id"]]
    distance = _validate_presence(warehouse, payload)
    _validate_local_authentication(payload)
    existing = next((row for row in _ATTENDANCE if row.get("shift_id") == shift_id and row.get("check_out") in (None, "—")), None)
    if existing:
        raise WorkforceRuleError("Bu vardiya için açık bir check-in zaten var.")
    now = datetime.now(UTC)
    row = {
        "id": f"ATT-{now.strftime('%Y%m%d%H%M%S%f')}",
        "shift_id": shift_id,
        "person_id": shift["person_id"],
        "name": shift["person_name"],
        "warehouse": warehouse["name"],
        "date": shift["date"],
        "planned": f'{shift["start"]}–{shift["end"]}',
        "check_in": now.isoformat(),
        "check_out": None,
        "break_minutes": 0,
        "net_minutes": 0,
        "expected_minutes": max(0, (((_minutes(shift["end"]) or 0) - (_minutes(shift["start"]) or 0)) % (24 * 60)) - shift["break_minutes"]),
        "status": "Vardiyada",
        "approval": "Canlı",
        "source": "Mobil",
        "pilot_simulation": bool(payload.get("pilot_simulation")),
        "device_id": payload["device_id"],
        "distance_meters": round(distance, 1),
        "local_auth_method": payload.get("local_auth_method", "NONE"),
        "audit": [{"event": "CHECK_IN", "actor": actor, "at": now.isoformat()}],
    }
    _ATTENDANCE.append(row)
    shift["status"] = "Vardiyada"
    _append_audit("CHECK_IN", actor, record_id=row["id"], shift_id=shift_id, person_id=row["person_id"], device_id=payload["device_id"], distance_meters=row["distance_meters"], local_auth_method=row["local_auth_method"], biometric_data_stored=False, pilot_simulation=row["pilot_simulation"])
    return deepcopy(row)


def check_out(shift_id: str, payload: dict, actor: str) -> dict:
    row = next((item for item in _ATTENDANCE if item.get("shift_id") == shift_id and item.get("check_out") in (None, "—")), None)
    if row is None:
        raise WorkforceRuleError("Açık check-in bulunamadı; check-out yapılamaz.")
    if row["person_id"] != payload["person_id"]:
        raise WorkforceRuleError("Bu vardiya başka bir personele ait.")
    shift = next((item for item in _SHIFTS if item["id"] == shift_id), None)
    if shift is None:
        raise WorkforceRuleError("Atanmış vardiya bulunamadı.")
    warehouse = _WAREHOUSES[shift["warehouse_id"]]
    distance = _validate_presence(warehouse, payload)
    _validate_local_authentication(payload)
    now = datetime.now(UTC)
    row["check_out"] = now.isoformat()
    row["status"] = "Onay bekliyor"
    row["approval"] = "Onay bekliyor"
    row["check_out_distance_meters"] = round(distance, 1)
    row["check_out_local_auth_method"] = payload.get("local_auth_method", "NONE")
    row["pilot_simulation"] = bool(row.get("pilot_simulation") or payload.get("pilot_simulation"))
    row["audit"].append({"event": "CHECK_OUT", "actor": actor, "at": now.isoformat()})
    _append_audit("CHECK_OUT", actor, record_id=row["id"], shift_id=shift_id, person_id=row["person_id"], device_id=payload["device_id"], distance_meters=row["check_out_distance_meters"], local_auth_method=row["check_out_local_auth_method"], biometric_data_stored=False, pilot_simulation=row["pilot_simulation"])
    return deepcopy(row)


def change_break(shift_id: str, person_id: str, action: str, actor: str) -> dict:
    shift = next((item for item in _SHIFTS if item["id"] == shift_id and item["person_id"] == person_id), None)
    if shift is None:
        raise WorkforceRuleError("Mola işlemi için personele atanmış vardiya bulunamadı.")
    attendance = next((item for item in _ATTENDANCE if item.get("shift_id") == shift_id and item.get("check_out") in (None, "—")), None)
    if attendance is None:
        raise WorkforceRuleError("Mola yalnızca açık check-in bulunan vardiyada yönetilebilir.")
    active = next((item for item in reversed(_BREAK_SESSIONS) if item["shift_id"] == shift_id and item.get("finished_at") is None), None)
    now = datetime.now(UTC)
    if action == "START":
        if active:
            raise WorkforceRuleError("Bu vardiyada devam eden mola zaten var.")
        active = {"id": f"BRK-{now.strftime('%Y%m%d%H%M%S%f')}", "shift_id": shift_id, "attendance_id": attendance["id"], "person_id": person_id, "started_at": now.isoformat(), "started_by": actor}
        _BREAK_SESSIONS.append(active)
        _append_audit("BREAK_STARTED", actor, record_id=active["id"], shift_id=shift_id, person_id=person_id)
        return deepcopy(active)
    if action == "FINISH":
        if not active:
            raise WorkforceRuleError("Bitirilecek aktif mola bulunamadı.")
        active["finished_at"] = now.isoformat()
        active["finished_by"] = actor
        active["minutes"] = max(0, round((now - datetime.fromisoformat(active["started_at"])).total_seconds() / 60))
        attendance["break_minutes"] = sum(int(item.get("minutes", 0)) for item in _BREAK_SESSIONS if item["attendance_id"] == attendance["id"])
        _append_audit("BREAK_FINISHED", actor, record_id=active["id"], shift_id=shift_id, person_id=person_id, minutes=active["minutes"])
        return deepcopy(active)
    raise WorkforceRuleError("Geçersiz mola işlemi.")


def list_breaks(person_id: str | None = None, shift_id: str | None = None) -> list[dict]:
    rows = _BREAK_SESSIONS
    if person_id:
        rows = [item for item in rows if item["person_id"] == person_id]
    if shift_id:
        rows = [item for item in rows if item["shift_id"] == shift_id]
    return deepcopy(rows)


def _find(attendance_id: str) -> dict | None:
    return next((item for item in _ATTENDANCE if item["id"] == attendance_id), None)


def _minutes(clock: str | None) -> int | None:
    if not clock:
        return None
    hour, minute = map(int, clock.split(":"))
    return hour * 60 + minute


def correct_attendance(attendance_id: str, payload: dict, actor: str) -> dict | None:
    row = _find(attendance_id)
    if row is None:
        return None

    before = {key: row.get(key) for key in ("check_in", "check_out", "break_minutes", "net_minutes")}
    check_in = payload.get("check_in")
    check_out = payload.get("check_out")
    break_minutes = int(payload.get("break_minutes", 0))
    start = _minutes(check_in)
    end = _minutes(check_out)

    net_minutes = row["net_minutes"]
    if start is not None and end is not None:
        gross = end - start
        if gross < 0:
            gross += 24 * 60
        net_minutes = max(0, gross - break_minutes)

    row.update(
        {
            "check_in": check_in,
            "check_out": check_out,
            "break_minutes": break_minutes,
            "net_minutes": net_minutes,
            "missing_minutes": max(0, row["expected_minutes"] - net_minutes),
            "overtime_minutes": max(0, net_minutes - row["expected_minutes"]),
            "approval": "Düzeltme onayında",
            "source": "Admin düzeltmesi",
        }
    )
    row["audit"].append(
        {
            "event": "MANUAL_CORRECTION",
            "actor": actor,
            "at": datetime.now(UTC).isoformat(),
            "reason": payload["reason"],
            "before": before,
            "after": {key: row.get(key) for key in ("check_in", "check_out", "break_minutes", "net_minutes")},
        }
    )
    _append_audit("MANUAL_CORRECTION", actor, record_id=attendance_id, reason=payload["reason"], before=before, after={key: row.get(key) for key in ("check_in", "check_out", "break_minutes", "net_minutes")})
    return deepcopy(row)


def approve_attendance(attendance_id: str, actor: str, note: str = "") -> dict | None:
    row = _find(attendance_id)
    if row is None:
        return None
    row["approval"] = "İK onaylı"
    row["audit"].append(
        {
            "event": "ATTENDANCE_APPROVED",
            "actor": actor,
            "at": datetime.now(UTC).isoformat(),
            "note": note,
        }
    )
    _append_audit("ATTENDANCE_APPROVED", actor, record_id=attendance_id, note=note)
    return deepcopy(row)


def bulk_approve_attendance(attendance_ids: list[str], actor: str, note: str = "") -> list[dict]:
    approved = []
    for attendance_id in attendance_ids:
        row = approve_attendance(attendance_id, actor, note)
        if row is not None:
            approved.append(row)
    return approved


def list_device_bindings() -> list[dict]:
    return deepcopy(_DEVICE_BINDINGS)


def reset_device_binding(person_id: str, payload: dict, actor: str) -> dict:
    now = datetime.now(UTC)
    revoked = []
    for binding in _DEVICE_BINDINGS:
        if binding["person_id"] == person_id and binding["status"] == "ACTIVE":
            binding["status"] = "REVOKED"
            binding["revoked_at"] = now.isoformat()
            binding["revoked_by"] = actor
            revoked.append(binding["device_id"])
    enrollment_token = token_urlsafe(32)
    _ENROLLMENT_TOKENS[enrollment_token] = {"person_id": person_id, "created_at": now.isoformat(), "created_by": actor, "used": False}
    _append_audit("DEVICE_BINDING_RESET", actor, person_id=person_id, revoked_device_ids=revoked, reason=payload["reason"])
    return {"person_id": person_id, "revoked_device_ids": revoked, "enrollment_token": enrollment_token, "status": "NEW_DEVICE_ENROLLMENT_PENDING"}


def register_device(payload: dict, actor: str) -> dict:
    enrollment = _ENROLLMENT_TOKENS.get(payload["enrollment_token"])
    if not enrollment or enrollment["used"] or enrollment["person_id"] != payload["person_id"]:
        raise WorkforceRuleError("Yeni cihaz kayıt bağlantısı geçersiz veya daha önce kullanılmış.")
    try:
        attestation_result = verify_attestation(
            payload["attestation_provider"], payload["attestation_token"],
            person_id=payload["person_id"], device_id=payload["device_id"], key_id=payload["device_key_id"],
        )
    except AttestationError as error:
        raise WorkforceRuleError(str(error)) from error
    enrollment["used"] = True
    now = datetime.now(UTC)
    record = {
        "person_id": payload["person_id"],
        "device_id": payload["device_id"],
        "device_key_id": payload["device_key_id"],
        "public_key": payload["public_key"],
        "attestation_provider": payload["attestation_provider"],
        "attestation_digest": sha256(payload["attestation_token"].encode("utf-8")).hexdigest(),
        "attestation_environment": attestation_result.get("environment", "production"),
        "model": payload["model"],
        "os_version": payload["os_version"],
        "app_version": payload["app_version"],
        "platform": payload.get("platform"),
        "push_token": payload.get("push_token"),
        "live_activity_token": payload.get("live_activity_token"),
        "status": "ACTIVE",
        "signed_challenge_required": True,
        "registered_at": now.isoformat(),
        "registered_by": actor,
    }
    for binding in _DEVICE_BINDINGS:
        if binding["person_id"] == payload["person_id"] and binding["status"] == "ACTIVE":
            binding["status"] = "REVOKED"
            binding["revoked_at"] = now.isoformat()
    _DEVICE_BINDINGS.append(record)
    _append_audit("DEVICE_REGISTERED", actor, person_id=payload["person_id"], device_id=payload["device_id"], device_key_id=payload["device_key_id"], attestation_provider=payload["attestation_provider"])
    return deepcopy(record)


def list_manager_tasks() -> list[dict]:
    return deepcopy(_CORRECTION_REQUESTS)


def create_correction_request(payload: dict, actor: str) -> dict:
    shift = next((row for row in _SHIFTS if row["id"] == payload["shift_id"] and row["person_id"] == payload["person_id"]), None)
    if not shift:
        raise WorkforceRuleError("Düzeltme talebi için personele ait vardiya bulunamadı.")
    now = datetime.now(UTC)
    record = {
        "id": f"CR-{now.strftime('%Y%m%d%H%M%S%f')}",
        **payload,
        "person_name": shift["person_name"],
        "warehouse_id": shift["warehouse_id"],
        "warehouse": _WAREHOUSES[shift["warehouse_id"]]["name"],
        "status": "MANAGER_REVIEW",
        "created_at": now.isoformat(),
        "created_by": actor,
    }
    _CORRECTION_REQUESTS.insert(0, record)
    _append_audit("CORRECTION_REQUEST_CREATED", actor, record_id=record["id"], shift_id=record["shift_id"], person_id=record["person_id"], request_type=record["request_type"])
    return deepcopy(record)


def resolve_manager_task(task_id: str, payload: dict, actor: str) -> dict | None:
    task = next((row for row in _CORRECTION_REQUESTS if row["id"] == task_id), None)
    if task is None:
        return None
    before = deepcopy(task)
    task.update({
        "status": payload["decision"],
        "manager_note": payload["manager_note"],
        "requested_check_in": payload.get("requested_check_in") or task.get("requested_check_in"),
        "requested_check_out": payload.get("requested_check_out") or task.get("requested_check_out"),
        "resolved_at": datetime.now(UTC).isoformat(),
        "resolved_by": actor,
    })
    if payload["decision"] in {"APPROVED", "CORRECTED"}:
        attendance = next((row for row in _ATTENDANCE if row.get("shift_id") == task["shift_id"]), None)
        if attendance:
            correction = {
                "check_in": task.get("requested_check_in") or attendance.get("check_in"),
                "check_out": task.get("requested_check_out") or attendance.get("check_out"),
                "break_minutes": attendance.get("break_minutes", 0),
                "reason": payload["manager_note"],
            }
            correct_attendance(attendance["id"], correction, actor)
    _append_audit("MANAGER_TASK_RESOLVED", actor, record_id=task_id, decision=payload["decision"], before=before, after=deepcopy(task))
    return deepcopy(task)


def list_announcements() -> list[dict]:
    return deepcopy(_ANNOUNCEMENTS)


def create_announcement(payload: dict, actor: str) -> dict:
    now = datetime.now(UTC)
    record = {
        "id": f"ANN-{now.strftime('%Y%m%d%H%M%S%f')}",
        **payload,
        "publish_at": payload.get("publish_at") or now.isoformat(),
        "active": True,
        "created_at": now.isoformat(),
        "created_by": actor,
    }
    if hasattr(record["publish_at"], "isoformat"):
        record["publish_at"] = record["publish_at"].isoformat()
    _ANNOUNCEMENTS.insert(0, record)
    _append_audit("ANNOUNCEMENT_PUBLISHED", actor, record_id=record["id"], target_type=record["target_type"], target_value=record["target_value"], publish_at=record["publish_at"])
    return deepcopy(record)


def dismiss_announcement(announcement_id: str, person_id: str, actor: str) -> dict:
    if not any(item["id"] == announcement_id for item in _ANNOUNCEMENTS):
        raise WorkforceRuleError("Duyuru bulunamadı.")
    record = {"id": f"{announcement_id}:{person_id}", "announcement_id": announcement_id, "person_id": person_id, "dismissed_at": datetime.now(UTC).isoformat(), "actor": actor}
    _ANNOUNCEMENT_RECEIPTS[:] = [item for item in _ANNOUNCEMENT_RECEIPTS if item["id"] != record["id"]]
    _ANNOUNCEMENT_RECEIPTS.append(record)
    _append_audit("ANNOUNCEMENT_DISMISSED", actor, record_id=announcement_id, person_id=person_id)
    return deepcopy(record)


def list_announcement_receipts(person_id: str) -> list[dict]:
    return deepcopy([item for item in _ANNOUNCEMENT_RECEIPTS if item["person_id"] == person_id])


def get_notification_policy() -> dict:
    return deepcopy(_NOTIFICATION_POLICY)


def update_notification_policy(payload: dict, actor: str) -> dict:
    before = deepcopy(_NOTIFICATION_POLICY)
    _NOTIFICATION_POLICY.update(payload)
    _append_audit("NOTIFICATION_POLICY_UPDATED", actor, before=before, after=deepcopy(_NOTIFICATION_POLICY))
    return deepcopy(_NOTIFICATION_POLICY)


def mark_notification_read(notification_id: str, person_id: str, actor: str) -> dict | None:
    row = next((item for item in _NOTIFICATIONS if item["id"] == notification_id and item["person_id"] == person_id), None)
    if row is None:
        return None
    row.update({"read": True, "read_at": datetime.now(UTC).isoformat()})
    _append_audit("NOTIFICATION_MARKED_READ", actor, record_id=notification_id, person_id=person_id)
    return deepcopy(row)


def delete_notification(notification_id: str, person_id: str, actor: str) -> bool:
    before = len(_NOTIFICATIONS)
    _NOTIFICATIONS[:] = [item for item in _NOTIFICATIONS if not (item["id"] == notification_id and item["person_id"] == person_id)]
    deleted = len(_NOTIFICATIONS) != before
    if deleted:
        _append_audit("NOTIFICATION_DELETED", actor, record_id=notification_id, person_id=person_id)
    return deleted


def clear_notifications(person_id: str, actor: str) -> int:
    before = len(_NOTIFICATIONS)
    _NOTIFICATIONS[:] = [item for item in _NOTIFICATIONS if item["person_id"] != person_id]
    count = before - len(_NOTIFICATIONS)
    _append_audit("NOTIFICATIONS_CLEARED", actor, person_id=person_id, count=count)
    return count


def create_leave_request(payload: dict, actor: str) -> dict:
    start = datetime.fromisoformat(payload["start_date"]).date()
    end = datetime.fromisoformat(payload["end_date"]).date()
    if end < start:
        raise WorkforceRuleError("İzin bitiş tarihi başlangıç tarihinden önce olamaz.")
    now = datetime.now(UTC)
    record = {"id": f"LR-{now.strftime('%Y%m%d%H%M%S%f')}", **payload, "days": (end - start).days + 1, "status": "MANAGER_REVIEW", "created_at": now.isoformat(), "created_by": actor}
    _LEAVE_REQUESTS.insert(0, record)
    _append_audit("LEAVE_REQUEST_CREATED", actor, record_id=record["id"], person_id=record["person_id"], start_date=record["start_date"], end_date=record["end_date"])
    return deepcopy(record)


def list_leave_requests(person_id: str | None = None, warehouse: str | None = None) -> list[dict]:
    rows = _LEAVE_REQUESTS
    if person_id:
        rows = [item for item in rows if item["person_id"] == person_id]
    if warehouse:
        rows = [item for item in rows if item["warehouse"] == warehouse]
    return deepcopy(rows)


def resolve_leave_request(request_id: str, payload: dict, actor: str) -> dict | None:
    row = next((item for item in _LEAVE_REQUESTS if item["id"] == request_id), None)
    if row is None:
        return None
    before = deepcopy(row)
    row.update({"status": payload["decision"], "manager_note": payload["manager_note"], "resolved_at": datetime.now(UTC).isoformat(), "resolved_by": actor})
    binding = next((item for item in _DEVICE_BINDINGS if item["person_id"] == row["person_id"] and item["status"] == "ACTIVE"), {})
    notification = {"id": f"NTF-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}", "person_id": row["person_id"], "type": "MANAGER_DECISION", "title": f"İzin talebiniz {payload['decision']}", "message": payload["manager_note"], "created_at": datetime.now(UTC).isoformat(), "scheduled_at": datetime.now(UTC).isoformat(), "read": False, "platform": binding.get("platform"), "push_token": binding.get("push_token")}
    _NOTIFICATIONS.insert(0, notification)
    persistence.enqueue_notification(notification)
    _append_audit("LEAVE_REQUEST_RESOLVED", actor, record_id=request_id, before=before, after=deepcopy(row))
    return deepcopy(row)


def get_feature_flags() -> dict:
    return deepcopy(_FEATURE_FLAGS)


def update_feature_flags(payload: dict, actor: str) -> dict:
    before = deepcopy(_FEATURE_FLAGS)
    _FEATURE_FLAGS.update(payload)
    _append_audit("FEATURE_FLAGS_UPDATED", actor, before=before, after=deepcopy(_FEATURE_FLAGS))
    return deepcopy(_FEATURE_FLAGS)
