from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import secrets
from threading import Lock
from uuid import uuid4

from app.modules.workforce import persistence
from app.modules.workforce.service import list_people, list_warehouses, resolve_person_identity, upsert_people
from app.modules.recruitment import candidate_upload_authority


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

_OFFICIAL_DOCUMENT_TYPES = {
    "CRIMINAL_RECORD", "RESIDENCE", "SGK_SERVICE", "MILITARY_STATUS",
    "EDUCATION", "CIVIL_REGISTRY",
}

_TEMPORARY_PLUS_ONE_WAREHOUSES = {
    "Dicle", "Yenikent", "Muratpaşa", "Lara", "Yıldırım", "Çorlu", "Mimaroba",
    "Konyaaltı", "Tuzla", "Kartal Cumhuriyet", "Fatih", "Anka", "Çekmeköy",
    "Bayrampaşa", "İsmetpaşa", "Bahçeşehir 2. Kısım", "Çiğli", "Tuğba",
    "Anadolu Hisarı",
}


class RecruitmentRuleError(ValueError):
    pass


def _validate_candidate_document_bytes(content_type: str, content: bytes) -> None:
    """Reject obvious type spoofing and active-document payloads before persistence.

    This is a deterministic pre-quarantine gate, not an antivirus verdict.
    """
    if not content:
        raise RecruitmentRuleError("Boş aday belgesi yüklenemez.")
    if content_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise RecruitmentRuleError("PDF içerik imzası geçersiz.")
        lowered = content.lower()
        forbidden = (b"/javascript", b"/js", b"/launch", b"/embeddedfile", b"/richmedia", b"/xfa")
        if any(marker in lowered for marker in forbidden):
            raise RecruitmentRuleError("Aktif veya gömülü içerik taşıyan PDF kabul edilmez.")
    elif content_type == "image/png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RecruitmentRuleError("PNG içerik imzası geçersiz.")
    elif content_type == "image/jpeg":
        if not (content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")):
            raise RecruitmentRuleError("JPEG içerik imzası geçersiz.")


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
        warehouse_stem = _normalize(warehouse).split(" (")[0]
        temporary_plus_one = warehouse_stem in {_normalize(name) for name in _TEMPORARY_PLUS_ONE_WAREHOUSES}
        rows.append({
            "id": f"NORM-{index:03d}",
            "regional_manager": regional_manager,
            "regional_executive": regional_executive,
            "warehouse": warehouse,
            "norm": int(norm) + int(temporary_plus_one),
            "base_norm": int(norm),
            "temporary_adjustment": 1 if temporary_plus_one else 0,
            "temporary_effective_from": "2026-07-01" if temporary_plus_one else None,
            "temporary_effective_until": "2026-09-30" if temporary_plus_one else None,
            "reversion_mode": "AUTOMATIC_REVIEW",
            "active": True,
        })
    return rows


def initialize() -> None:
    persistence.initialize()
    if not persistence.ENABLED:
        return
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        tenant_id = persistence.tenant_id()
        cursor.execute("SELECT count(*) FROM recruitment_norms WHERE tenant_id=%s", (tenant_id,))
        if cursor.fetchone()[0] == 0:
            for row in _default_norms():
                cursor.execute(
                    """INSERT INTO recruitment_norms(tenant_id,id,warehouse,payload,updated_at)
                       VALUES (%s,%s,%s,%s::jsonb,%s)""",
                    (tenant_id, row["id"], row["warehouse"], json.dumps(row, ensure_ascii=False), _now()),
                )
        cursor.execute("SELECT 1 FROM recruitment_settings WHERE tenant_id=%s AND id='default'", (tenant_id,))
        if cursor.fetchone() is None:
            cursor.execute(
                """INSERT INTO recruitment_settings(tenant_id,id,payload,updated_at)
                   VALUES (%s,'default',%s::jsonb,%s)""",
                (tenant_id, json.dumps(_DEFAULT_SETTINGS, ensure_ascii=False), _now()),
            )
        database.commit()


def _normalize(value: str | None) -> str:
    return str(value or "").strip().casefold().replace("i̇", "i")


def _effective_norm(record: dict, on_date: str | None = None) -> tuple[int, str]:
    day = on_date or datetime.now(UTC).date().isoformat()
    base = int(record.get("base_norm", record.get("norm", 0)))
    adjustment = int(record.get("temporary_adjustment", 0))
    starts = str(record.get("temporary_effective_from") or "")
    ends = str(record.get("temporary_effective_until") or "")
    if adjustment and starts and ends and starts <= day <= ends:
        return base + adjustment, "TEMPORARY_ACTIVE"
    if adjustment and ends and day > ends:
        return base, "REVERTED_REVIEW_REQUIRED" if record.get("reversion_mode") == "AUTOMATIC_REVIEW" else "REVERTED"
    return int(record.get("norm", base)), "PERMANENT"


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
        persistence._set_tenant(cursor)
        cursor.execute(query, params)
        return [row[0] for row in cursor.fetchall()]


def get_settings() -> dict:
    rows = _rows(
        "SELECT payload FROM recruitment_settings WHERE tenant_id=%s AND id='default'",
        (persistence.tenant_id(),),
    )
    return deepcopy(rows[0] if rows else _DEFAULT_SETTINGS)


def update_settings(payload: dict, actor: str) -> dict:
    settings = {**_DEFAULT_SETTINGS, **payload}
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """INSERT INTO recruitment_settings(tenant_id,id,payload,updated_at)
               VALUES (%s,'default',%s::jsonb,%s)
               ON CONFLICT (tenant_id,id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at""",
            (persistence.tenant_id(), json.dumps(settings, ensure_ascii=False), _now()),
        )
        database.commit()
    persistence.append_audit("RECRUITMENT_SETTINGS_UPDATED", actor, recipients={"hr": len(settings["hr_recipients"]), "partner": len(settings["partner_recipients"])})
    return settings


def list_norms() -> list[dict]:
    return _rows(
        "SELECT payload FROM recruitment_norms WHERE tenant_id=%s ORDER BY warehouse",
        (persistence.tenant_id(),),
    )


def upsert_norm(payload: dict, actor: str) -> dict:
    existing = next((row for row in list_norms() if _normalize(row["warehouse"]) == _normalize(payload["warehouse"])), None)
    record = {**(existing or {}), **payload, "id": (existing or {}).get("id") or f"NORM-{uuid4().hex[:12]}", "updated_at": _now().isoformat(), "updated_by": actor}
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """INSERT INTO recruitment_norms(tenant_id,id,warehouse,payload,updated_at)
               VALUES (%s,%s,%s,%s::jsonb,%s)
               ON CONFLICT (tenant_id,id) DO UPDATE
               SET warehouse=excluded.warehouse,payload=excluded.payload,updated_at=excluded.updated_at""",
            (persistence.tenant_id(), record["id"], record["warehouse"], json.dumps(record, ensure_ascii=False), _now()),
        )
        database.commit()
    persistence.append_audit("RECRUITMENT_NORM_UPDATED", actor, record_id=record["id"], warehouse=record["warehouse"], norm=record["norm"])
    return record


def list_requests() -> list[dict]:
    return _rows(
        """SELECT payload || jsonb_build_object('revision', revision)
           FROM recruitment_requests WHERE tenant_id=%s ORDER BY created_at DESC""",
        (persistence.tenant_id(),),
    )


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
        max(0, int(row.get("quantity", 0)) - len(row.get("hires", [])))
        for row in list_requests()
        if row.get("id") != exclude_request
        and _normalize(row.get("warehouse_name")) == _normalize(warehouse_name)
        and row.get("position_code") == position_code
        and row.get("status") in {"PENDING_APPROVAL", "APPROVED", "SOURCING", "PARTIALLY_FILLED"}
    )


def evaluate(warehouse_id: str, position_code: str, quantity: int, planned_departure: dict | None = None, exclude_request: str | None = None) -> dict:
    warehouse = _find_warehouse(warehouse_id)
    norm_row = next((row for row in list_norms() if row.get("active", True) and _normalize(row["warehouse"]) == _normalize(warehouse["name"])), None)
    headcount = _headcount(warehouse)
    settings = get_settings()
    is_manager = position_code == "STORE_MANAGER"
    effective_norm, norm_status = _effective_norm(norm_row or {})
    capacity = int(settings["warehouse_manager_capacity"].get(warehouse["name"], settings["default_manager_capacity"])) if is_manager else effective_norm
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
        "norm_record": norm_row, "norm_status": norm_status, "departure_employee_valid": departure_valid,
    }


def _save_request(
    record: dict, expected_revision: int | None = None, *,
    audit_event: str | None = None, actor: str = "system", audit_details: dict | None = None,
) -> None:
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        tenant_id = persistence.tenant_id()
        if audit_event:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"workforce:{tenant_id}",))
        if expected_revision is None:
            record["revision"] = 1
            cursor.execute(
                """INSERT INTO recruitment_requests
                   (tenant_id,id,status,warehouse_id,revision,created_at,payload)
                   VALUES (%s,%s,%s,%s,1,%s,%s::jsonb)""",
                (
                    tenant_id, record["id"], record["status"], record["warehouse_id"],
                    record["created_at"], json.dumps(record, ensure_ascii=False, default=str),
                ),
            )
        else:
            next_revision = expected_revision + 1
            payload = {**record, "revision": next_revision}
            cursor.execute(
                """UPDATE recruitment_requests
                   SET status=%s,warehouse_id=%s,revision=%s,payload=%s::jsonb
                   WHERE tenant_id=%s AND id=%s AND revision=%s
                   RETURNING revision""",
                (
                    record["status"], record["warehouse_id"], next_revision,
                    json.dumps(payload, ensure_ascii=False, default=str), tenant_id,
                    record["id"], expected_revision,
                ),
            )
            if cursor.fetchone() is None:
                database.rollback()
                raise RecruitmentRuleError(
                    "İşe alım kaydı başka bir yönetici tarafından güncellendi; ekranı yenileyip tekrar deneyin."
                )
            record["revision"] = next_revision
        if audit_event:
            persistence._build_audit_record(cursor, audit_event, actor, audit_details or {})
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
    _save_request(
        record, audit_event="RECRUITMENT_REQUEST_CREATED", actor=actor,
        audit_details={"record_id": record["id"], "warehouse": record["warehouse_name"], "evaluation": evaluation},
    )
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
    expected_revision = int(record.get("revision", 1))
    digest = sha256(content).hexdigest()
    suffix = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[content_type]
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / f"{request_id}-{digest[:16]}{suffix}"
    created_file = not path.exists()
    path.write_bytes(content)
    uploaded_at = _now()
    retention_days = max(1, int(os.getenv("RECRUITMENT_EVIDENCE_RETENTION_DAYS", "365")))
    record["evidence"] = {
        "original_name": Path(filename).name[:240], "content_type": content_type,
        "size": len(content), "sha256": digest, "stored_name": path.name,
        "uploaded_at": uploaded_at.isoformat(), "uploaded_by": actor,
        "retention_until": (uploaded_at + timedelta(days=retention_days)).isoformat(),
    }
    if record["status"] == "EVIDENCE_REQUIRED":
        record["status"] = "PENDING_APPROVAL"
    record["history"].append({"at": _now().isoformat(), "action": "EVIDENCE_UPLOADED", "actor": actor, "sha256": digest})
    try:
        _save_request(
            record, expected_revision, audit_event="RECRUITMENT_EVIDENCE_UPLOADED", actor=actor,
            audit_details={"record_id": request_id, "sha256": digest, "content_type": content_type, "size": len(content)},
        )
    except Exception:
        if created_file:
            path.unlink(missing_ok=True)
        raise
    return record


def evidence_path(request_id: str) -> tuple[Path, dict]:
    record = next((row for row in list_requests() if row["id"] == request_id), None)
    if not record or not record.get("evidence"):
        raise RecruitmentRuleError("İstifa belgesi bulunamadı.")
    path = _EVIDENCE_DIR / record["evidence"]["stored_name"]
    if not path.exists():
        raise RecruitmentRuleError("Belge dosyası arşivde bulunamadı.")
    return path, record["evidence"]


def register_candidate(request_id: str, payload: dict, actor: str) -> dict:
    """Attach a PII-minimized ATS candidate reference to an approved vacancy."""
    with _LOCK:
        record = next((row for row in list_requests() if row["id"] == request_id), None)
        if not record or record["status"] not in {"APPROVED", "SOURCING", "PARTIALLY_FILLED"}:
            raise RecruitmentRuleError("Aday yalnızca onaylı ve açık bir vacancy kaydına eklenebilir.")
        expected_revision = int(record.get("revision", 1))
        candidates = list(record.get("candidates", []))
        if any(item.get("source_ref") == payload["source_ref"] for item in candidates):
            raise RecruitmentRuleError("Bu aday kaynak referansı vacancy üzerinde zaten kayıtlı.")
        now = _now().isoformat()
        pii_retention_days = max(1, int(os.getenv("RECRUITMENT_CANDIDATE_PII_RETENTION_DAYS", "730")))
        candidate = {
            "id": f"CAND-{uuid4().hex[:12]}", "full_name": payload["full_name"],
            "source_ref": payload["source_ref"], "note": payload.get("note"),
            "status": "EVIDENCE_PENDING", "evidence": [], "created_at": now, "created_by": actor,
            "pii_retention_until": (_now() + timedelta(days=pii_retention_days)).isoformat(),
        }
        candidates.append(candidate)
        record["candidates"] = candidates
        if record["status"] == "APPROVED":
            record["status"] = "SOURCING"
        record["history"].append({"at": now, "action": "CANDIDATE_REGISTERED", "actor": actor, "candidate_id": candidate["id"]})
        _save_request(
            record, expected_revision, audit_event="RECRUITMENT_CANDIDATE_REGISTERED", actor=actor,
            audit_details={"record_id": request_id, "candidate_id": candidate["id"], "source_ref": candidate["source_ref"]},
        )
        return candidate


def issue_candidate_upload_capability(
    request_id: str, candidate_id: str, document_type: str, expires_in_minutes: int, actor: str,
) -> dict:
    """Issue a one-time opaque upload secret; only its SHA-256 digest is persisted."""
    normalized_type = str(document_type or "").strip().upper()
    if normalized_type not in _OFFICIAL_DOCUMENT_TYPES | {"OTHER"}:
        raise RecruitmentRuleError("Desteklenmeyen aday belge türü.")
    if os.getenv("RECRUITMENT_CANDIDATE_UPLOAD_AUTHORITY_MODE", "disabled").strip().lower() == "postgres":
        try:
            return candidate_upload_authority.issue(
                request_id, candidate_id, normalized_type, expires_in_minutes, actor,
            )
        except candidate_upload_authority.CandidateUploadAuthorityError as error:
            raise RecruitmentRuleError(str(error)) from error
    raw_token = secrets.token_urlsafe(32)
    token_digest = sha256(raw_token.encode("utf-8")).hexdigest()
    with _LOCK:
        record = next((row for row in list_requests() if row["id"] == request_id), None)
        candidate = next((item for item in (record or {}).get("candidates", []) if item["id"] == candidate_id), None)
        if candidate is None or candidate.get("status") not in {"EVIDENCE_PENDING", "REVIEW_PENDING"}:
            raise RecruitmentRuleError("Aday bulunamadı veya belge kabul eden aşamada değil.")
        expected_revision = int(record.get("revision", 1))
        issued_at = _now()
        capability = {
            "id": f"CAP-{uuid4().hex[:12]}", "token_sha256": token_digest,
            "document_type": normalized_type, "issued_at": issued_at.isoformat(), "issued_by": actor,
            "expires_at": (issued_at + timedelta(minutes=expires_in_minutes)).isoformat(),
            "consumed_at": None,
        }
        candidate.setdefault("upload_capabilities", []).append(capability)
        record["history"].append({
            "at": issued_at.isoformat(), "action": "CANDIDATE_UPLOAD_CAPABILITY_ISSUED",
            "actor": actor, "candidate_id": candidate_id, "capability_id": capability["id"],
            "document_type": normalized_type,
        })
        _save_request(
            record, expected_revision, audit_event="RECRUITMENT_CANDIDATE_UPLOAD_CAPABILITY_ISSUED", actor=actor,
            audit_details={"record_id": request_id, "candidate_id": candidate_id,
                           "capability_id": capability["id"], "document_type": normalized_type},
        )
    return {
        "capability": raw_token, "expires_at": capability["expires_at"],
        "document_type": normalized_type, "max_uploads": 1,
    }


def consume_candidate_upload_capability(raw_token: str, document_type: str) -> tuple[str, str, str]:
    """Atomically consume a tenant-contained, single-use upload capability."""
    token = str(raw_token or "").strip()
    if len(token) < 32 or len(token) > 256:
        raise RecruitmentRuleError("Aday yükleme yetkisi geçersiz veya süresi dolmuş.")
    presented_digest = sha256(token.encode("utf-8")).hexdigest()
    normalized_type = str(document_type or "").strip().upper()
    with _LOCK:
        match = None
        for record in list_requests():
            for candidate in record.get("candidates", []):
                for capability in candidate.get("upload_capabilities", []):
                    if hmac.compare_digest(str(capability.get("token_sha256", "")), presented_digest):
                        if match is not None:
                            raise RecruitmentRuleError("Aday yükleme yetkisi bütünlük kontrolünü geçemedi.")
                        match = (record, candidate, capability)
        if match is None:
            raise RecruitmentRuleError("Aday yükleme yetkisi geçersiz veya süresi dolmuş.")
        record, candidate, capability = match
        if capability.get("consumed_at") or datetime.fromisoformat(capability["expires_at"]) <= _now():
            raise RecruitmentRuleError("Aday yükleme yetkisi geçersiz veya süresi dolmuş.")
        if candidate.get("status") not in {"EVIDENCE_PENDING", "REVIEW_PENDING"}:
            raise RecruitmentRuleError("Aday artık belge kabul eden aşamada değil.")
        if normalized_type != capability.get("document_type"):
            raise RecruitmentRuleError("Belge türü verilen aday yükleme yetkisiyle eşleşmiyor.")
        expected_revision = int(record.get("revision", 1))
        consumed_at = _now().isoformat()
        capability["consumed_at"] = consumed_at
        capability["consumed_by"] = "candidate-capability"
        record["history"].append({
            "at": consumed_at, "action": "CANDIDATE_UPLOAD_CAPABILITY_CONSUMED",
            "actor": "candidate-capability", "candidate_id": candidate["id"],
            "capability_id": capability["id"], "document_type": normalized_type,
        })
        _save_request(
            record, expected_revision, audit_event="RECRUITMENT_CANDIDATE_UPLOAD_CAPABILITY_CONSUMED",
            actor="candidate-capability", audit_details={
                "record_id": record["id"], "candidate_id": candidate["id"],
                "capability_id": capability["id"], "document_type": normalized_type,
            },
        )
        return record["id"], candidate["id"], capability["id"]


def add_candidate_evidence(
    request_id: str, candidate_id: str, filename: str, content_type: str, content: bytes, actor: str,
    *, document_type: str = "OTHER",
) -> dict:
    if len(content) > 10 * 1024 * 1024 or content_type not in {"application/pdf", "image/jpeg", "image/png"}:
        raise RecruitmentRuleError("Aday kanıtı PDF/JPG/PNG ve en fazla 10 MB olmalıdır.")
    _validate_candidate_document_bytes(content_type, content)
    with _LOCK:
        record = next((row for row in list_requests() if row["id"] == request_id), None)
        candidate = next((item for item in (record or {}).get("candidates", []) if item["id"] == candidate_id), None)
        if candidate is None or candidate["status"] not in {"EVIDENCE_PENDING", "REVIEW_PENDING"}:
            raise RecruitmentRuleError("Aday bulunamadı veya kanıt kabul eden aşamada değil.")
        normalized_document_type = str(document_type or "OTHER").strip().upper()
        if normalized_document_type not in _OFFICIAL_DOCUMENT_TYPES | {"OTHER"}:
            raise RecruitmentRuleError("Desteklenmeyen aday belge türü.")
        expected_revision = int(record.get("revision", 1))
        digest = sha256(content).hexdigest()
        suffix = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[content_type]
        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        path = _EVIDENCE_DIR / f"{request_id}-{candidate_id}-{digest[:16]}{suffix}"
        created_file = not path.exists()
        path.write_bytes(content)
        uploaded_at = _now()
        retention_days = max(1, int(os.getenv("RECRUITMENT_EVIDENCE_RETENTION_DAYS", "365")))
        requires_official_verification = normalized_document_type in _OFFICIAL_DOCUMENT_TYPES
        evidence = {
            "original_name": Path(filename).name[:240], "content_type": content_type,
            "size": len(content), "sha256": digest, "stored_name": path.name,
            "uploaded_at": uploaded_at.isoformat(), "uploaded_by": actor,
            "retention_until": (uploaded_at + timedelta(days=retention_days)).isoformat(),
            "document_type": normalized_document_type,
            "requires_official_verification": requires_official_verification,
            "verification_state": (
                "BARCODE_EXTRACTION_PENDING" if requires_official_verification else "NOT_REQUIRED"
            ),
            "official_verification": None,
            "content_safety_state": "STATIC_FORMAT_ACCEPTED_AV_PENDING",
            "content_safety_truth_boundary": "NOT_MALWARE_CLEARED",
        }
        candidate["evidence"].append(evidence)
        candidate["status"] = "REVIEW_PENDING"
        record["history"].append({"at": uploaded_at.isoformat(), "action": "CANDIDATE_EVIDENCE_UPLOADED", "actor": actor, "candidate_id": candidate_id, "sha256": digest})
        try:
            _save_request(
                record, expected_revision, audit_event="RECRUITMENT_CANDIDATE_EVIDENCE_UPLOADED", actor=actor,
                audit_details={"record_id": request_id, "candidate_id": candidate_id, "sha256": digest, "size": len(content)},
            )
        except Exception:
            if created_file:
                path.unlink(missing_ok=True)
            raise
        return candidate


def record_candidate_document_verification(
    request_id: str, candidate_id: str, payload: dict, actor: str, *, verification_method: str,
    provider_signature_verified: bool = False,
) -> dict:
    """Bind an official-document result to the exact uploaded bytes.

    Browser automation/scraping is intentionally not an authority. Until an
    approved machine-to-machine adapter exists, HR may witness the official
    portal result and record its immutable receipt metadata.
    """
    allowed_methods = {"HR_ASSISTED_OFFICIAL_PORTAL", "AUTHORIZED_OFFICIAL_API"}
    if verification_method not in allowed_methods:
        raise RecruitmentRuleError("Belge doğrulama yöntemi güvenilir değil.")
    if verification_method == "AUTHORIZED_OFFICIAL_API" and not provider_signature_verified:
        raise RecruitmentRuleError("Yetkili doğrulayıcı servis imzası doğrulanmadı.")
    with _LOCK:
        all_records = list_requests()
        record = next((row for row in all_records if row["id"] == request_id), None)
        candidate = next((item for item in (record or {}).get("candidates", []) if item["id"] == candidate_id), None)
        if candidate is None or candidate.get("status") not in {"REVIEW_PENDING", "EVIDENCE_PENDING"}:
            raise RecruitmentRuleError("Aday bulunamadı veya belge doğrulama aşamasında değil.")
        evidence = next(
            (item for item in candidate.get("evidence", []) if item.get("sha256") == payload["evidence_sha256"]),
            None,
        )
        if evidence is None:
            raise RecruitmentRuleError("Doğrulama sonucu yüklenen belge baytlarıyla eşleşmiyor.")
        if not evidence.get("requires_official_verification"):
            raise RecruitmentRuleError("Bu belge türü için resmî doğrulama kaydı kabul edilmez.")
        if evidence.get("document_type") != payload["document_type"]:
            raise RecruitmentRuleError("Doğrulama belge türü yüklenen kanıtla eşleşmiyor.")
        if evidence.get("official_verification") is not None:
            raise RecruitmentRuleError("Belge doğrulama kaydı değiştirilemez; yeni belge yüklenmelidir.")
        receipt_reused = any(
            other_evidence.get("official_verification", {}).get("official_receipt_id")
            == payload["official_receipt_id"]
            for other_record in all_records
            for other_candidate in other_record.get("candidates", [])
            for other_evidence in other_candidate.get("evidence", [])
            if other_evidence is not evidence
        )
        if receipt_reused:
            raise RecruitmentRuleError("Resmî doğrulama makbuzu daha önce kullanılmış; replay engellendi.")
        expected_revision = int(record.get("revision", 1))
        now = _now().isoformat()
        verified = payload["result"] == "VERIFIED" and payload["subject_match"] == "MATCH"
        verification = {
            **payload,
            "method": verification_method,
            "verified": verified,
            "verified_at": now,
            "verified_by": actor,
            "truth_boundary": (
                "HUMAN_WITNESSED_OFFICIAL_PORTAL"
                if verification_method == "HR_ASSISTED_OFFICIAL_PORTAL"
                else "AUTHORIZED_MACHINE_TO_MACHINE"
            ),
        }
        evidence["official_verification"] = verification
        if not verified:
            evidence["verification_state"] = "OFFICIAL_REVIEW_FAILED"
        elif verification_method == "AUTHORIZED_OFFICIAL_API":
            evidence["verification_state"] = "OFFICIAL_VERIFIED"
        else:
            evidence["verification_state"] = "HUMAN_WITNESSED_PENDING_ATTESTATION"
        record["history"].append({
            "at": now, "action": "CANDIDATE_DOCUMENT_VERIFICATION_RECORDED",
            "actor": actor, "candidate_id": candidate_id,
            "evidence_sha256": payload["evidence_sha256"], "result": payload["result"],
            "subject_match": payload["subject_match"], "method": verification_method,
        })
        _save_request(
            record, expected_revision,
            audit_event="RECRUITMENT_CANDIDATE_DOCUMENT_VERIFICATION_RECORDED", actor=actor,
            audit_details={
                "record_id": request_id, "candidate_id": candidate_id,
                "evidence_sha256": payload["evidence_sha256"],
                "official_response_sha256": payload["official_response_sha256"],
                "result": payload["result"], "subject_match": payload["subject_match"],
                "method": verification_method,
            },
        )
        return candidate


def attest_candidate_document_verification(
    request_id: str, candidate_id: str, evidence_sha256: str, note: str, actor: str,
) -> dict:
    """Apply four-eyes attestation to a witnessed official-portal result."""
    with _LOCK:
        record = next((row for row in list_requests() if row["id"] == request_id), None)
        candidate = next((item for item in (record or {}).get("candidates", []) if item["id"] == candidate_id), None)
        evidence = next(
            (item for item in (candidate or {}).get("evidence", []) if item.get("sha256") == evidence_sha256),
            None,
        )
        if evidence is None:
            raise RecruitmentRuleError("Onaylanacak belge kanıtı bulunamadı.")
        if evidence.get("verification_state") != "HUMAN_WITNESSED_PENDING_ATTESTATION":
            raise RecruitmentRuleError("Belge ikinci yetkili onayına hazır değil.")
        verification = evidence.get("official_verification") or {}
        if verification.get("verified_by") == actor:
            raise RecruitmentRuleError("Belgeyi doğrulayan kişi ikinci yetkili onayını veremez.")
        expected_revision = int(record.get("revision", 1))
        now = _now().isoformat()
        verification["attestation"] = {
            "attested_at": now, "attested_by": actor, "note": str(note).strip(),
            "four_eyes": True,
        }
        evidence["verification_state"] = "HUMAN_WITNESSED_ATTESTED"
        record["history"].append({
            "at": now, "action": "CANDIDATE_DOCUMENT_VERIFICATION_ATTESTED",
            "actor": actor, "candidate_id": candidate_id, "evidence_sha256": evidence_sha256,
        })
        _save_request(
            record, expected_revision,
            audit_event="RECRUITMENT_CANDIDATE_DOCUMENT_VERIFICATION_ATTESTED", actor=actor,
            audit_details={
                "record_id": request_id, "candidate_id": candidate_id,
                "evidence_sha256": evidence_sha256,
                "witnessed_by": verification.get("verified_by"), "four_eyes": True,
            },
        )
        return candidate


def record_candidate_content_safety_scan(
    request_id: str, candidate_id: str, evidence_sha256: str, result: str,
    scanner_receipt_id: str, scanner_engine: str, actor: str, *, provider_signature_verified: bool = False,
) -> dict:
    """Seal a signed malware-scanner result to the exact immutable evidence bytes."""
    if os.getenv("DOCKOS_ENV", "development").strip().lower() == "production":
        raise RecruitmentRuleError(
            "Production scanner sonucu kriptografik receipt otoritesi üzerinden kaydedilmelidir."
        )
    if not provider_signature_verified:
        raise RecruitmentRuleError("İçerik güvenliği sağlayıcı imzası doğrulanmadı.")
    normalized_result = str(result).strip().upper()
    if normalized_result not in {"CLEAN", "INFECTED", "ERROR"}:
        raise RecruitmentRuleError("İçerik güvenliği sonucu desteklenmiyor.")
    with _LOCK:
        all_records = list_requests()
        record = next((row for row in all_records if row["id"] == request_id), None)
        candidate = next((item for item in (record or {}).get("candidates", []) if item["id"] == candidate_id), None)
        evidence = next(
            (item for item in (candidate or {}).get("evidence", []) if item.get("sha256") == evidence_sha256), None,
        )
        if evidence is None:
            raise RecruitmentRuleError("İçerik güvenliği sonucu yüklenen belge baytlarıyla eşleşmiyor.")
        if evidence.get("content_safety_receipt") is not None:
            raise RecruitmentRuleError("İçerik güvenliği makbuzu değiştirilemez; yeni belge yüklenmelidir.")
        if any(
            other.get("content_safety_receipt", {}).get("scanner_receipt_id") == scanner_receipt_id
            for other_record in all_records
            for other_candidate in other_record.get("candidates", [])
            for other in other_candidate.get("evidence", [])
            if other is not evidence
        ):
            raise RecruitmentRuleError("İçerik güvenliği makbuzu daha önce kullanılmış; replay engellendi.")
        expected_revision = int(record.get("revision", 1))
        scanned_at = _now().isoformat()
        evidence["content_safety_state"] = {
            "CLEAN": "MALWARE_CLEARED", "INFECTED": "MALWARE_DETECTED", "ERROR": "SCAN_FAILED",
        }[normalized_result]
        evidence["content_safety_truth_boundary"] = "SIGNED_SCANNER_RECEIPT"
        evidence["content_safety_receipt"] = {
            "scanner_receipt_id": str(scanner_receipt_id).strip(),
            "scanner_engine": str(scanner_engine).strip(), "result": normalized_result,
            "evidence_sha256": evidence_sha256, "scanned_at": scanned_at, "recorded_by": actor,
        }
        record["history"].append({
            "at": scanned_at, "action": "CANDIDATE_EVIDENCE_CONTENT_SAFETY_SCANNED",
            "actor": actor, "candidate_id": candidate_id, "evidence_sha256": evidence_sha256,
            "result": normalized_result,
        })
        _save_request(
            record, expected_revision, audit_event="RECRUITMENT_CANDIDATE_EVIDENCE_CONTENT_SAFETY_SCANNED",
            actor=actor, audit_details={"record_id": request_id, "candidate_id": candidate_id,
                                        "evidence_sha256": evidence_sha256, "result": normalized_result,
                                        "scanner_engine": str(scanner_engine).strip()},
        )
        return evidence


def decide_candidate(request_id: str, candidate_id: str, decision: str, note: str, actor: str) -> dict:
    with _LOCK:
        record = next((row for row in list_requests() if row["id"] == request_id), None)
        candidate = next((item for item in (record or {}).get("candidates", []) if item["id"] == candidate_id), None)
        if candidate is None or candidate["status"] != "REVIEW_PENDING" or not candidate.get("evidence"):
            raise RecruitmentRuleError("Aday, kanıt incelemesi tamamlanmadan sonuçlandırılamaz.")
        unresolved_official = [
            evidence for evidence in candidate.get("evidence", [])
            if evidence.get("requires_official_verification")
            and evidence.get("verification_state") not in {
                "HUMAN_WITNESSED_ATTESTED", "OFFICIAL_VERIFIED",
            }
        ]
        if decision == "APPROVED" and unresolved_official:
            raise RecruitmentRuleError(
                "Resmî doğrulama gereken tüm aday belgeleri geçerli ve kişiyle eşleşmiş olmadan aday onaylanamaz."
            )
        unsafe_or_unscanned = [
            evidence for evidence in candidate.get("evidence", [])
            if evidence.get("content_safety_state") != "MALWARE_CLEARED"
        ]
        if decision == "APPROVED" and unsafe_or_unscanned:
            raise RecruitmentRuleError(
                "İçerik güvenliği taraması temiz sonuçlanmadan aday onaylanamaz."
            )
        expected_revision = int(record.get("revision", 1))
        now = _now().isoformat()
        candidate.update({"status": decision, "decision_note": note, "decided_at": now, "decided_by": actor})
        record["history"].append({"at": now, "action": f"CANDIDATE_{decision}", "actor": actor, "candidate_id": candidate_id, "note": note})
        _save_request(
            record, expected_revision, audit_event=f"RECRUITMENT_CANDIDATE_{decision}", actor=actor,
            audit_details={"record_id": request_id, "candidate_id": candidate_id, "note": note},
        )
        return candidate


def candidate_evidence_path(request_id: str, candidate_id: str, digest: str) -> tuple[Path, dict]:
    record = next((row for row in list_requests() if row["id"] == request_id), None)
    candidate = next((item for item in (record or {}).get("candidates", []) if item["id"] == candidate_id), None)
    evidence = next((item for item in (candidate or {}).get("evidence", []) if item["sha256"] == digest), None)
    if evidence is None:
        raise RecruitmentRuleError("Aday kanıtı bulunamadı.")
    if evidence.get("content_safety_state") != "MALWARE_CLEARED":
        raise RecruitmentRuleError("Aday kanıtı içerik güvenliği karantinasından çıkmadı.")
    stored = Path(str(evidence["stored_name"]))
    if stored.is_absolute() or ".." in stored.parts:
        raise RecruitmentRuleError("Aday kanıt arşiv anahtarı geçersiz.")
    path = _EVIDENCE_DIR / stored
    if not path.exists():
        raise RecruitmentRuleError("Aday kanıt dosyası arşivde bulunamadı.")
    return path, evidence


def purge_expired_recruitment_data(actor: str, now: datetime | None = None) -> dict:
    """Apply configured candidate-PII and evidence retention, with audit."""
    cutoff = now or _now()
    redacted_candidates = deleted_evidence = 0
    changed_requests = 0
    for record in list_requests():
        expected_revision = int(record.get("revision", 1))
        changed = False
        evidence_groups = []
        if record.get("evidence"):
            evidence_groups.append((record, "evidence", [record["evidence"]]))
        for candidate in record.get("candidates", []):
            retention_until = candidate.get("pii_retention_until")
            if retention_until and datetime.fromisoformat(retention_until) <= cutoff and candidate.get("full_name") != "[REDACTED]":
                candidate["full_name"] = "[REDACTED]"
                candidate["note"] = None
                candidate["source_ref"] = f"sha256:{sha256(str(candidate.get('source_ref', '')).encode()).hexdigest()}"
                candidate["pii_redacted_at"] = cutoff.isoformat()
                redacted_candidates += 1
                changed = True
            evidence_groups.append((candidate, "evidence", list(candidate.get("evidence", []))))
        for owner, key, items in evidence_groups:
            retained = []
            for evidence in items:
                retention_until = evidence.get("retention_until")
                if retention_until and datetime.fromisoformat(retention_until) <= cutoff:
                    stored = Path(str(evidence["stored_name"]))
                    if not stored.is_absolute() and ".." not in stored.parts:
                        (_EVIDENCE_DIR / stored).unlink(missing_ok=True)
                    deleted_evidence += 1
                    changed = True
                else:
                    retained.append(evidence)
            owner[key] = retained if isinstance(owner.get(key), list) else (retained[0] if retained else None)
        if changed:
            record.setdefault("history", []).append({"at": cutoff.isoformat(), "action": "RETENTION_PURGE", "actor": actor})
            _save_request(
                record, expected_revision, audit_event="RECRUITMENT_RETENTION_PURGED", actor=actor,
                audit_details={"record_id": record["id"]},
            )
            changed_requests += 1
    return {
        "changed_requests": changed_requests,
        "redacted_candidates": redacted_candidates,
        "deleted_evidence": deleted_evidence,
        "cutoff": cutoff.isoformat(),
    }


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


def _email_rows(record: dict) -> list[dict]:
    settings = get_settings()
    rows: list[dict] = []
    for group, recipients in (("HR", settings["hr_recipients"]), ("PARTNER", settings["partner_recipients"])):
        payload = _mail_payload(record, group, recipients)
        rows.append({
            "id": f"MAIL-{uuid4().hex[:16]}", "request_id": record["id"],
            "recipient_group": group, "status": "PENDING" if recipients else "RECIPIENT_REQUIRED",
            "attempts": 0, "created_at": _now().isoformat(), "payload": payload,
        })
    return rows


def _save_decision_and_queue(record: dict, expected_revision: int, actor: str, evaluation: dict) -> list[dict]:
    """CAS the human decision and create its outbox in one transaction."""
    queued = _email_rows(record) if record["status"] == "APPROVED" else []
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        tenant_id = persistence.tenant_id()
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"workforce:{tenant_id}",))
        next_revision = expected_revision + 1
        payload = {**record, "revision": next_revision}
        cursor.execute(
            """UPDATE recruitment_requests
               SET status=%s,warehouse_id=%s,revision=%s,payload=%s::jsonb
               WHERE tenant_id=%s AND id=%s AND revision=%s RETURNING revision""",
            (
                record["status"], record["warehouse_id"], next_revision,
                json.dumps(payload, ensure_ascii=False, default=str), tenant_id,
                record["id"], expected_revision,
            ),
        )
        if cursor.fetchone() is None:
            database.rollback()
            raise RecruitmentRuleError(
                "İşe alım kaydı başka bir yönetici tarafından güncellendi; ekranı yenileyip tekrar deneyin."
            )
        for row in queued:
            cursor.execute(
                """INSERT INTO recruitment_email_outbox
                   (tenant_id,id,request_id,recipient_group,status,created_at,payload)
                   VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (
                    tenant_id, row["id"], row["request_id"], row["recipient_group"],
                    row["status"], row["created_at"],
                    json.dumps(row["payload"], ensure_ascii=False),
                ),
            )
        persistence._build_audit_record(
            cursor, "RECRUITMENT_REQUEST_DECIDED", actor,
            {"record_id": record["id"], "decision": record["status"], "note": record["decision_note"], "evaluation": evaluation},
        )
        database.commit()
    record["revision"] = next_revision
    return queued


def list_outbox() -> list[dict]:
    if not persistence.ENABLED:
        return []
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT id,request_id,recipient_group,status,attempts,last_error,created_at,delivered_at,payload
               FROM recruitment_email_outbox WHERE tenant_id=%s ORDER BY created_at DESC""",
            (persistence.tenant_id(),),
        )
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
    tenant_id = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT id,request_id,recipient_group,status,attempts,payload
               FROM recruitment_email_outbox
               WHERE tenant_id=%s AND id=%s FOR UPDATE""",
            (tenant_id, outbox_id),
        )
        claimed = cursor.fetchone()
        if claimed is None:
            raise RecruitmentRuleError("E-posta kuyruğu kaydı bulunamadı.")
        row = {
            "id": claimed[0], "request_id": claimed[1], "recipient_group": claimed[2],
            "status": claimed[3], "attempts": int(claimed[4]), "payload": claimed[5],
        }
        if row["status"] == "DELIVERED":
            database.commit()
            return next(item for item in list_outbox() if item["id"] == outbox_id)
        maximum_attempts = max(1, int(os.getenv("RECRUITMENT_EMAIL_MAX_ATTEMPTS", "8")))
        if row["status"] == "DEAD_LETTER" or (row["status"] == "FAILED" and row["attempts"] >= maximum_attempts):
            database.commit()
            raise RecruitmentRuleError("E-posta kaydı azami deneme sayısına ulaştı.")
        cursor.execute(
            """UPDATE recruitment_email_outbox
               SET status='SENDING',attempts=attempts+1,locked_at=now(),last_error=NULL
               WHERE tenant_id=%s AND id=%s""",
            (tenant_id, outbox_id),
        )
        database.commit()
    attempt = row["attempts"] + 1
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
            message["Message-ID"] = f"<{outbox_id}@eay-workforce>"
            message["X-OPEX-Idempotency-Key"] = outbox_id
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
        persistence._set_tenant(cursor)
        maximum_attempts = max(1, int(os.getenv("RECRUITMENT_EMAIL_MAX_ATTEMPTS", "8")))
        dead_letter = status == "FAILED" and attempt >= maximum_attempts
        final_status = "DEAD_LETTER" if dead_letter else status
        retry_seconds = min(3600, 30 * (2 ** max(0, attempt - 1)))
        cursor.execute(
            """UPDATE recruitment_email_outbox SET status=%s,last_error=%s,locked_at=NULL,
               delivered_at=CASE WHEN %s='DELIVERED' THEN %s ELSE delivered_at END,
               next_attempt_at=CASE WHEN %s='FAILED' THEN now() + make_interval(secs => %s) ELSE NULL END,
               dead_lettered_at=CASE WHEN %s THEN now() ELSE dead_lettered_at END
               WHERE tenant_id=%s AND id=%s""",
            (
                final_status, error, final_status, _now(), final_status, retry_seconds,
                dead_letter, tenant_id, outbox_id,
            ),
        )
        database.commit()
    persistence.append_audit("RECRUITMENT_EMAIL_DISPATCHED", actor, record_id=outbox_id, request_id=row["request_id"], status=final_status, recipient_group=row["recipient_group"], attempt=attempt)
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
        expected_revision = int(record.get("revision", 1))
        record.update(latest)
        record["status"] = decision
        record["decision_note"] = note
        record["decided_at"] = _now().isoformat()
        record["decided_by"] = actor
        record["decided_by_name"] = actor_name
        record["history"].append({"at": record["decided_at"], "action": decision, "actor": actor, "note": note})
        outbox = _save_decision_and_queue(record, expected_revision, actor, latest)
    delivered = [dispatch_email(item["id"], actor) for item in outbox]
    return {**record, "email_outbox": delivered}


def activate_hire(request_id: str, payload: dict, actor: str) -> dict:
    """Activate an approved vacancy hire in Employee Master and Workforce."""
    with _LOCK:
        record = next((row for row in list_requests() if row["id"] == request_id), None)
        if not record:
            raise RecruitmentRuleError("Talep bulunamadı.")
        if record["status"] not in {"APPROVED", "SOURCING", "PARTIALLY_FILLED"}:
            raise RecruitmentRuleError("Yalnızca onaylanmış ve açık kontenjanı bulunan talebe işe giriş yapılabilir.")
        expected_revision = int(record.get("revision", 1))
        hires = list(record.get("hires", []))
        if len(hires) >= int(record["quantity"]):
            raise RecruitmentRuleError("Talebin tüm kontenjanları doldurulmuş.")
        candidates = list(record.get("candidates", []))
        candidate_id = payload.get("candidate_id")
        candidate = next((item for item in candidates if item.get("id") == candidate_id), None)
        if candidate is None or candidate.get("status") != "APPROVED":
            raise RecruitmentRuleError("İşe giriş için kanıtları onaylanmış bir candidate_id zorunludur.")
        canonical_person = resolve_person_identity(payload["tckn"], "TC") or resolve_person_identity(payload["employee_id"], "EMPLOYEE_ID")
        canonical_employee_id = str((canonical_person or {}).get("employee_id") or payload["employee_id"])
        if any(str(item.get("employee_id")) == canonical_employee_id for item in hires):
            raise RecruitmentRuleError("Bu çalışan talep üzerinden daha önce aktive edilmiş.")
        roster_ids = {str(value) for value in payload.get("roster_ids", [])}
        conflict = next((person for person in list_people(False) if str(person.get("employee_id")) != canonical_employee_id and roster_ids.intersection({str(value) for value in person.get("roster_ids", [])})), None)
        if conflict:
            raise RecruitmentRuleError("Roster ID başka bir Employee Master kaydına bağlı; aktivasyon durduruldu.")
        from app.modules.workforce import service as workforce_service
        rollback_snapshot = workforce_service._snapshot_collections()
        person = {
            **payload,
            "employment_start": str(payload["employment_start"]),
            "employment_end": None,
            "position": record["position_label"],
            "warehouse_id": record["warehouse_id"],
            "active": True,
        }
        try:
            result = upsert_people([person], actor, persist=False)
            canonical_person = resolve_person_identity(payload["tckn"], "TC") or canonical_person
            canonical_employee_id = str((canonical_person or {}).get("employee_id") or payload["employee_id"])
            now = _now().isoformat()
            activation = {
                "employee_id": canonical_employee_id, "full_name": payload["full_name"],
                "employment_start": str(payload["employment_start"]), "activated_at": now,
                "activated_by": actor, "employee_master": "ACTIVE", "workforce": "ACTIVE",
            }
            if candidate is not None:
                candidate.update({"status": "HIRED", "employee_id": canonical_employee_id, "hired_at": now})
            hires.append(activation)
            record["hires"] = hires
            record["filled_quantity"] = len(hires)
            record["remaining_quantity"] = max(0, int(record["quantity"]) - len(hires))
            record["status"] = "FILLED" if record["remaining_quantity"] == 0 else "PARTIALLY_FILLED"
            record["history"].append({"at": now, "action": "HIRE_ACTIVATED", "actor": actor, "employee_id": canonical_employee_id})
            first_shift_input = payload["first_shift"]
            if hasattr(first_shift_input, "model_dump"):
                first_shift_input = first_shift_input.model_dump(mode="json")
            if str(first_shift_input["date"]) < str(payload["employment_start"]):
                raise RecruitmentRuleError("İlk vardiya işe giriş tarihinden önce olamaz.")
            first_shift = workforce_service.create_shift({
                "person_id": canonical_employee_id,
                "person_name": payload["full_name"],
                "roster_id": first_shift_input["roster_id"],
                "warehouse_id": record["warehouse_id"],
                "date": str(first_shift_input["date"]),
                "start": first_shift_input["start"],
                "end": first_shift_input["end"],
                "break_minutes": int(first_shift_input.get("break_minutes", 60)),
                "role": record["position_label"],
            }, actor, persist=False)
            activation["first_shift_id"] = first_shift["id"]
            record["history"].append({"at": now, "action": "FIRST_SHIFT_ASSIGNED", "actor": actor, "shift_id": first_shift["id"]})
            if persistence.ENABLED:
                workforce_service._append_audit(
                    "RECRUITMENT_HIRE_ACTIVATED", actor, record_id=request_id,
                    employee_id=canonical_employee_id, workforce_status="ACTIVE",
                    first_shift_id=first_shift["id"],
                    _related_recruitment_request=record,
                    _expected_recruitment_revision=expected_revision,
                )
            else:
                _save_request(record)
                persistence.append_audit(
                    "RECRUITMENT_HIRE_ACTIVATED", actor, record_id=request_id,
                    employee_id=canonical_employee_id, workforce_status="ACTIVE",
                )
        except Exception:
            if persistence.ENABLED:
                workforce_service._hydrate_snapshot(
                    persistence.load_snapshot(workforce_service._snapshot_kinds())
                )
            else:
                workforce_service._hydrate_snapshot(rollback_snapshot)
            raise
    return {**record, "employee_master_result": result, "activation": activation, "first_shift": first_shift}


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
