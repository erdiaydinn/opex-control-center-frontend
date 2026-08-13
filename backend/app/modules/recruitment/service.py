from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from email.message import EmailMessage
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
from threading import Lock
from uuid import uuid4

from app.modules.workforce import persistence
from app.modules.workforce.service import list_people, list_warehouses


_LOCK = Lock()
_EVIDENCE_DIR = Path(os.getenv("RECRUITMENT_EVIDENCE_DIR", "/var/lib/dockos/recruitment-evidence"))
_DEFAULT_SETTINGS = {
    "hr_recipients": [],
    "partner_recipients": [],
    "default_manager_capacity": 1,
    "warehouse_manager_capacity": {"Fulya (İstanbul)": 2},
    "counted_position_codes": ["STORE_STAFF", "ASSISTANT_MANAGER", "STORE_SUPPORT"],
}
_POSITION_LABELS = {
    "STORE_STAFF": "Mağaza Görevlisi",
    "ASSISTANT_MANAGER": "Mağaza Müdür Yardımcısı",
    "STORE_SUPPORT": "Mağaza Destek Görevlisi",
    "STORE_MANAGER": "Mağaza Müdürü",
}


class RecruitmentRuleError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _norm_source_path() -> Path:
    packaged = Path(__file__).resolve().parent / "data" / "staffingNorms.js"
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[4] / "src" / "modules" / "workforce" / "staffingNorms.js"


def _default_norms() -> list[dict]:
    source = _norm_source_path().read_text(encoding="utf-8-sig")
    match = re.search(r"RAW_STAFFING_NORMS\s*=\s*`(?P<body>.*?)`;", source, re.S)
    if not match:
        raise RuntimeError("Staffing norm kaynağı okunamadı.")
    rows: list[dict] = []
    for index, line in enumerate(match.group("body").strip().splitlines(), start=1):
        regional_manager, regional_executive, warehouse, norm = line.split("|")
        rows.append({
            "id": f"NORM-{index:03d}",
            "regional_manager": regional_manager,
            "regional_executive": regional_executive,
            "warehouse": warehouse,
            "norm": int(norm),
            "active": True,
        })
    return rows


def initialize() -> None:
    persistence.initialize()
    if not persistence.ENABLED:
        return
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with persistence.connection() as database, database.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS recruitment_requests (
              id text PRIMARY KEY,
              status text NOT NULL,
              warehouse_id text NOT NULL,
              created_at timestamptz NOT NULL,
              payload jsonb NOT NULL
            );
            CREATE INDEX IF NOT EXISTS recruitment_request_status_idx
              ON recruitment_requests(status, created_at DESC);
            CREATE TABLE IF NOT EXISTS recruitment_settings (
              id text PRIMARY KEY,
              payload jsonb NOT NULL,
              updated_at timestamptz NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recruitment_norms (
              id text PRIMARY KEY,
              warehouse text NOT NULL,
              payload jsonb NOT NULL,
              updated_at timestamptz NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS recruitment_norm_warehouse_idx
              ON recruitment_norms(lower(warehouse));
            CREATE TABLE IF NOT EXISTS recruitment_email_outbox (
              id text PRIMARY KEY,
              request_id text NOT NULL,
              recipient_group text NOT NULL,
              status text NOT NULL DEFAULT 'PENDING',
              attempts integer NOT NULL DEFAULT 0,
              last_error text,
              created_at timestamptz NOT NULL,
              delivered_at timestamptz,
              payload jsonb NOT NULL
            );
            """
        )
        cursor.execute("SELECT count(*) FROM recruitment_norms")
        if cursor.fetchone()[0] == 0:
            for row in _default_norms():
                cursor.execute(
                    "INSERT INTO recruitment_norms(id,warehouse,payload,updated_at) VALUES (%s,%s,%s::jsonb,%s)",
                    (row["id"], row["warehouse"], json.dumps(row, ensure_ascii=False), _now()),
                )
        cursor.execute("SELECT 1 FROM recruitment_settings WHERE id='default'")
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO recruitment_settings(id,payload,updated_at) VALUES ('default',%s::jsonb,%s)",
                (json.dumps(_DEFAULT_SETTINGS, ensure_ascii=False), _now()),
            )
        database.commit()


def _normalize(value: str | None) -> str:
    return str(value or "").strip().casefold().replace("i̇", "i")


def _position_code(person: dict) -> str:
    raw = _normalize(person.get("position") or person.get("role"))
    if raw in {"warehouse_manager", "store_manager"} or "mağaza müdürü" in raw or "magaza muduru" in raw:
        if "yardım" not in raw and "yardim" not in raw:
            return "STORE_MANAGER"
    if "yardım" in raw or "yardim" in raw or "assistant" in raw:
        return "ASSISTANT_MANAGER"
    if "destek" in raw or "support" in raw:
        return "STORE_SUPPORT"
    return "STORE_STAFF"


def _rows(query: str, params: tuple = ()) -> list[dict]:
    if not persistence.ENABLED:
        return []
    with persistence.connection() as database, database.cursor() as cursor:
        cursor.execute(query, params)
        return [row[0] for row in cursor.fetchall()]


def get_settings() -> dict:
    rows = _rows("SELECT payload FROM recruitment_settings WHERE id='default'")
    return deepcopy(rows[0] if rows else _DEFAULT_SETTINGS)


def update_settings(payload: dict, actor: str) -> dict:
    settings = {**_DEFAULT_SETTINGS, **payload}
    with persistence.connection() as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_settings(id,payload,updated_at)
               VALUES ('default',%s::jsonb,%s)
               ON CONFLICT (id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at""",
            (json.dumps(settings, ensure_ascii=False), _now()),
        )
        database.commit()
    persistence.append_audit("RECRUITMENT_SETTINGS_UPDATED", actor, recipients={"hr": len(settings["hr_recipients"]), "partner": len(settings["partner_recipients"])})
    return settings


def list_norms() -> list[dict]:
    return _rows("SELECT payload FROM recruitment_norms ORDER BY warehouse")


def upsert_norm(payload: dict, actor: str) -> dict:
    existing = next((row for row in list_norms() if _normalize(row["warehouse"]) == _normalize(payload["warehouse"])), None)
    record = {**(existing or {}), **payload, "id": (existing or {}).get("id") or f"NORM-{uuid4().hex[:12]}", "updated_at": _now().isoformat(), "updated_by": actor}
    with persistence.connection() as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_norms(id,warehouse,payload,updated_at) VALUES (%s,%s,%s::jsonb,%s)
               ON CONFLICT (id) DO UPDATE SET warehouse=excluded.warehouse,payload=excluded.payload,updated_at=excluded.updated_at""",
            (record["id"], record["warehouse"], json.dumps(record, ensure_ascii=False), _now()),
        )
        database.commit()
    persistence.append_audit("RECRUITMENT_NORM_UPDATED", actor, record_id=record["id"], warehouse=record["warehouse"], norm=record["norm"])
    return record


def list_requests() -> list[dict]:
    return _rows("SELECT payload FROM recruitment_requests ORDER BY created_at DESC")


def _find_warehouse(warehouse_id: str) -> dict:
    warehouses = list_warehouses()
    warehouse = next((row for row in warehouses if str(row.get("id")) == str(warehouse_id)), None)
    if warehouse:
        return warehouse
    warehouse = next((row for row in warehouses if _normalize(row.get("name")) == _normalize(warehouse_id)), None)
    if not warehouse:
        raise RecruitmentRuleError("Depo bulunamadı.")
    return warehouse


def _headcount(warehouse: dict) -> dict:
    settings = get_settings()
    counted_codes = set(settings["counted_position_codes"])
    aliases = {_normalize(warehouse.get("id")), _normalize(warehouse.get("name"))}
    today = datetime.now(UTC).date().isoformat()
    people = [
        person for person in list_people(False)
        if person.get("active", True)
        and (not person.get("employment_start") or str(person.get("employment_start")) <= today)
        and (not person.get("employment_end") or str(person.get("employment_end")) >= today)
        and (_normalize(person.get("warehouse_id")) in aliases or _normalize(person.get("warehouse")) in aliases)
    ]
    by_position = {code: 0 for code in _POSITION_LABELS}
    for person in people:
        by_position[_position_code(person)] += 1
    active_staff = sum(value for code, value in by_position.items() if code in counted_codes)
    active_managers = by_position["STORE_MANAGER"]
    return {"active_staff": active_staff, "active_managers": active_managers, "by_position": by_position}


def _open_positions(warehouse_name: str, position_code: str, exclude_request: str | None = None) -> int:
    return sum(
        int(row.get("quantity", 0))
        for row in list_requests()
        if row.get("id") != exclude_request
        and _normalize(row.get("warehouse_name")) == _normalize(warehouse_name)
        and row.get("position_code") == position_code
        and row.get("status") in {"PENDING_APPROVAL", "APPROVED", "SOURCING"}
    )


def evaluate(warehouse_id: str, position_code: str, quantity: int, planned_departure: dict | None = None, exclude_request: str | None = None) -> dict:
    warehouse = _find_warehouse(warehouse_id)
    norm_row = next((row for row in list_norms() if row.get("active", True) and _normalize(row["warehouse"]) == _normalize(warehouse["name"])), None)
    headcount = _headcount(warehouse)
    settings = get_settings()
    is_manager = position_code == "STORE_MANAGER"
    capacity = int(settings["warehouse_manager_capacity"].get(warehouse["name"], settings["default_manager_capacity"])) if is_manager else int((norm_row or {}).get("norm", 0))
    active = headcount["active_managers"] if is_manager else headcount["active_staff"]
    open_positions = _open_positions(warehouse["name"], position_code, exclude_request)
    departure_credit = 0
    departure_valid = False
    if planned_departure:
        departure_employee = next((person for person in list_people(False) if str(person.get("employee_id")) == str(planned_departure.get("employee_id"))), None)
        aliases = {_normalize(warehouse.get("id")), _normalize(warehouse.get("name"))}
        departure_valid = bool(
            departure_employee and departure_employee.get("active", True)
            and (_normalize(departure_employee.get("warehouse_id")) in aliases or _normalize(departure_employee.get("warehouse")) in aliases)
        )
        departure_code = _position_code(departure_employee or {})
        compatible_departure = departure_code == "STORE_MANAGER" if is_manager else departure_code in set(settings["counted_position_codes"])
        if departure_valid and compatible_departure:
            departure_credit = 1
    projected = active + open_positions - departure_credit
    available = max(0, capacity - projected)
    if capacity <= 0:
        recommendation, reason = "MANUAL_REVIEW", "Bu depo için aktif norm kaydı bulunamadı."
    elif quantity <= available:
        recommendation, reason = "APPROVE", "Norm ve projekte aktif çalışan sayısı talebi karşılıyor."
    else:
        recommendation, reason = "REJECT", "Talep, norm veya müdür kapasitesinin üzerinde kalıyor."
    return {
        "warehouse_id": warehouse["id"], "warehouse_name": warehouse["name"],
        "position_code": position_code, "position_label": _POSITION_LABELS[position_code],
        "capacity": capacity, "active": active, "active_staff": headcount["active_staff"],
        "active_managers": headcount["active_managers"], "open_positions": open_positions,
        "planned_departures": departure_credit, "projected": projected, "available": available,
        "recommendation": recommendation, "recommendation_reason": reason,
        "norm_record": norm_row, "departure_employee_valid": departure_valid,
    }


def _save_request(record: dict) -> None:
    with persistence.connection() as database, database.cursor() as cursor:
        cursor.execute(
            """INSERT INTO recruitment_requests(id,status,warehouse_id,created_at,payload)
               VALUES (%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (id) DO UPDATE SET status=excluded.status,warehouse_id=excluded.warehouse_id,payload=excluded.payload""",
            (record["id"], record["status"], record["warehouse_id"], record["created_at"], json.dumps(record, ensure_ascii=False, default=str)),
        )
        database.commit()


def create_request(payload: dict, actor: str, actor_name: str) -> dict:
    evaluation = evaluate(payload["warehouse_id"], payload["position_code"], payload["quantity"], payload.get("planned_departure"))
    now = _now()
    evidence_required = payload["reason_code"] == "PLANNED_DEPARTURE"
    record = {
        "id": f"REC-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}",
        **payload,
        **evaluation,
        "status": "EVIDENCE_REQUIRED" if evidence_required else "PENDING_APPROVAL",
        "evidence_required": evidence_required,
        "evidence": None,
        "requested_by": actor,
        "requested_by_name": actor_name,
        "created_at": now.isoformat(),
        "history": [{"at": now.isoformat(), "action": "CREATED", "actor": actor}],
    }
    _save_request(record)
    persistence.append_audit("RECRUITMENT_REQUEST_CREATED", actor, record_id=record["id"], warehouse=record["warehouse_name"], evaluation=evaluation)
    return record


def add_evidence(request_id: str, filename: str, content_type: str, content: bytes, actor: str) -> dict:
    if len(content) > 10 * 1024 * 1024:
        raise RecruitmentRuleError("Belge boyutu 10 MB sınırını aşıyor.")
    allowed = {"application/pdf", "image/jpeg", "image/png"}
    if content_type not in allowed:
        raise RecruitmentRuleError("Yalnızca PDF, JPG veya PNG istifa belgesi yüklenebilir.")
    record = next((row for row in list_requests() if row["id"] == request_id), None)
    if not record:
        raise RecruitmentRuleError("Talep bulunamadı.")
    digest = sha256(content).hexdigest()
    suffix = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[content_type]
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / f"{request_id}-{digest[:16]}{suffix}"
    path.write_bytes(content)
    record["evidence"] = {"original_name": Path(filename).name[:240], "content_type": content_type, "size": len(content), "sha256": digest, "stored_name": path.name, "uploaded_at": _now().isoformat(), "uploaded_by": actor}
    if record["status"] == "EVIDENCE_REQUIRED":
        record["status"] = "PENDING_APPROVAL"
    record["history"].append({"at": _now().isoformat(), "action": "EVIDENCE_UPLOADED", "actor": actor, "sha256": digest})
    _save_request(record)
    persistence.append_audit("RECRUITMENT_EVIDENCE_UPLOADED", actor, record_id=request_id, sha256=digest, content_type=content_type, size=len(content))
    return record


def evidence_path(request_id: str) -> tuple[Path, dict]:
    record = next((row for row in list_requests() if row["id"] == request_id), None)
    if not record or not record.get("evidence"):
        raise RecruitmentRuleError("İstifa belgesi bulunamadı.")
    path = _EVIDENCE_DIR / record["evidence"]["stored_name"]
    if not path.exists():
        raise RecruitmentRuleError("Belge dosyası arşivde bulunamadı.")
    return path, record["evidence"]


def _mail_payload(record: dict, group: str, recipients: list[str]) -> dict:
    base_url = os.getenv("OPEX_PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
    subject = f"[OPEX] Onaylanan işe alım talebi · {record['warehouse_name']} · {record['quantity']} kişi"
    body = (
        f"OPEX Control Center üzerinden bir işe alım talebi onaylandı.\n\n"
        f"Talep no: {record['id']}\nDepo: {record['warehouse_name']}\n"
        f"Pozisyon: {record['position_label']}\nAdet: {record['quantity']}\n"
        f"İhtiyaç tarihi: {record['needed_by']}\nTalep nedeni: {record['justification']}\n\n"
        f"Personel bulunması ve işe alım sürecinin başlatılması konusunda desteğinizi rica ederiz.\n"
        f"Talep ekranı: {base_url}/recruitment\n"
    )
    return {"subject": subject, "body": body, "recipients": recipients, "group": group, "request_id": record["id"]}


def _queue_emails(record: dict) -> list[dict]:
    settings = get_settings()
    queued: list[dict] = []
    with persistence.connection() as database, database.cursor() as cursor:
        for group, recipients in (("HR", settings["hr_recipients"]), ("PARTNER", settings["partner_recipients"])):
            payload = _mail_payload(record, group, recipients)
            row = {"id": f"MAIL-{uuid4().hex[:16]}", "request_id": record["id"], "recipient_group": group, "status": "PENDING" if recipients else "RECIPIENT_REQUIRED", "attempts": 0, "created_at": _now().isoformat(), "payload": payload}
            cursor.execute(
                "INSERT INTO recruitment_email_outbox(id,request_id,recipient_group,status,created_at,payload) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                (row["id"], row["request_id"], group, row["status"], row["created_at"], json.dumps(payload, ensure_ascii=False)),
            )
            queued.append(row)
        database.commit()
    return queued


def list_outbox() -> list[dict]:
    if not persistence.ENABLED:
        return []
    with persistence.connection() as database, database.cursor() as cursor:
        cursor.execute("SELECT id,request_id,recipient_group,status,attempts,last_error,created_at,delivered_at,payload FROM recruitment_email_outbox ORDER BY created_at DESC")
        return [
            {"id": row[0], "request_id": row[1], "recipient_group": row[2], "status": row[3], "attempts": row[4], "last_error": row[5], "created_at": row[6].isoformat(), "delivered_at": row[7].isoformat() if row[7] else None, "payload": row[8]}
            for row in cursor.fetchall()
        ]


def _smtp_config() -> dict:
    return {
        "host": os.getenv("RECRUITMENT_SMTP_HOST") or os.getenv("DOCKOS_SMTP_HOST", ""),
        "port": int(os.getenv("RECRUITMENT_SMTP_PORT") or os.getenv("DOCKOS_SMTP_PORT", "587")),
        "tls": (os.getenv("RECRUITMENT_SMTP_TLS") or os.getenv("DOCKOS_SMTP_TLS", "true")).lower() == "true",
        "user": os.getenv("RECRUITMENT_SMTP_USER") or os.getenv("DOCKOS_SMTP_USER", ""),
        "password": os.getenv("RECRUITMENT_SMTP_PASSWORD") or os.getenv("DOCKOS_SMTP_PASSWORD", ""),
        "sender": os.getenv("RECRUITMENT_SMTP_FROM") or os.getenv("DOCKOS_SMTP_FROM", ""),
    }


def dispatch_email(outbox_id: str, actor: str) -> dict:
    row = next((item for item in list_outbox() if item["id"] == outbox_id), None)
    if not row:
        raise RecruitmentRuleError("E-posta kuyruğu kaydı bulunamadı.")
    config = _smtp_config()
    recipients = row["payload"].get("recipients", [])
    status, error = "DELIVERED", None
    if not recipients:
        status, error = "RECIPIENT_REQUIRED", "Alıcı listesi yapılandırılmamış."
    elif not config["host"] or not config["sender"]:
        status, error = "SMTP_CONFIGURATION_REQUIRED", "SMTP sunucusu veya gönderen adresi yapılandırılmamış."
    else:
        try:
            message = EmailMessage()
            message["Subject"] = row["payload"]["subject"]
            message["From"] = config["sender"]
            message["To"] = ", ".join(recipients)
            message.set_content(row["payload"]["body"])
            with smtplib.SMTP(config["host"], config["port"], timeout=20) as smtp:
                if config["tls"]:
                    smtp.starttls(context=ssl.create_default_context())
                if config["user"]:
                    smtp.login(config["user"], config["password"])
                smtp.send_message(message)
        except Exception as exc:
            status, error = "FAILED", str(exc)[:1000]
    with persistence.connection() as database, database.cursor() as cursor:
        cursor.execute(
            """UPDATE recruitment_email_outbox SET status=%s,attempts=attempts+1,last_error=%s,
               delivered_at=CASE WHEN %s='DELIVERED' THEN %s ELSE delivered_at END WHERE id=%s""",
            (status, error, status, _now(), outbox_id),
        )
        database.commit()
    persistence.append_audit("RECRUITMENT_EMAIL_DISPATCHED", actor, record_id=outbox_id, request_id=row["request_id"], status=status, recipient_group=row["recipient_group"])
    return next(item for item in list_outbox() if item["id"] == outbox_id)


def decide_request(request_id: str, decision: str, note: str, actor: str, actor_name: str) -> dict:
    with _LOCK:
        record = next((row for row in list_requests() if row["id"] == request_id), None)
        if not record:
            raise RecruitmentRuleError("Talep bulunamadı.")
        if record["status"] != "PENDING_APPROVAL":
            raise RecruitmentRuleError("Yalnızca onay bekleyen talepler sonuçlandırılabilir.")
        if record.get("evidence_required") and not record.get("evidence"):
            raise RecruitmentRuleError("Planlı ayrılış talebi istifa belgesi olmadan onaylanamaz.")
        latest = evaluate(record["warehouse_id"], record["position_code"], record["quantity"], record.get("planned_departure"), request_id)
        record.update(latest)
        record["status"] = decision
        record["decision_note"] = note
        record["decided_at"] = _now().isoformat()
        record["decided_by"] = actor
        record["decided_by_name"] = actor_name
        record["history"].append({"at": record["decided_at"], "action": decision, "actor": actor, "note": note})
        _save_request(record)
        outbox = _queue_emails(record) if decision == "APPROVED" else []
    delivered = [dispatch_email(item["id"], actor) for item in outbox]
    persistence.append_audit("RECRUITMENT_REQUEST_DECIDED", actor, record_id=request_id, decision=decision, note=note, evaluation=latest)
    return {**record, "email_outbox": delivered}


def dashboard() -> dict:
    requests = list_requests()
    norms = list_norms()
    warehouse_rows = []
    for norm in norms:
        try:
            evaluation = evaluate(norm["warehouse"], "STORE_STAFF", 1)
        except RecruitmentRuleError:
            continue
        warehouse_rows.append(evaluation)
    return {
        "pending": sum(row["status"] == "PENDING_APPROVAL" for row in requests),
        "approved": sum(row["status"] == "APPROVED" for row in requests),
        "rejected": sum(row["status"] == "REJECTED" for row in requests),
        "evidence_required": sum(row["status"] == "EVIDENCE_REQUIRED" for row in requests),
        "norm_gap_warehouses": sum(row["available"] > 0 for row in warehouse_rows),
        "warehouse_rows": sorted(warehouse_rows, key=lambda row: row["available"], reverse=True),
    }
