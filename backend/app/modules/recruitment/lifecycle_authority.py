"""Hiring V47 lifecycle authorities.

Repository-controlled lifecycle layer for:
- four-eyes offer approval before candidate capability issuance,
- PII-minimized candidate communication outbox,
- consent-bound talent pools,
- cross-functional offboarding completion.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any
from uuid import UUID, uuid4

from app.modules.workforce import persistence
from .orchestration import (
    RecruitmentOrchestrationError,
    _assignment_locked,
    _candidate,
    _canonical_offer_package,
    issue_offer_decision_capability,
)


class RecruitmentLifecycleError(ValueError):
    pass


REQUIRED_SCHEMA_VERSION = 47
_OFFER_APPROVAL_QUORUM = 2
_MESSAGE_TYPES = {
    "INTERVIEW_INVITE",
    "INTERVIEW_REMINDER",
    "OFFER_READY",
    "OFFER_REMINDER",
    "ONBOARDING_REMINDER",
    "PROCESS_UPDATE",
    "TALENT_POOL_REENGAGE",
}
_CHANNELS = {"EMAIL", "SMS", "IN_APP"}
_FORBIDDEN_COMMUNICATION_KEYS = {
    "email", "e_mail", "phone", "telephone", "mobile", "tckn", "tc", "national_id",
    "full_name", "name", "address", "birth_date", "birthdate",
}
_OFFBOARDING_TASKS = (
    ("HR_EXIT_RECORD", "Exit record and statutory HR packet", "HR", []),
    ("IT_REVOKE_ACCESS", "Identity, SSO and application access revocation", "IT", ["HR_EXIT_RECORD"]),
    ("ADMIN_RETURN_ASSETS", "Device, asset, key and uniform return", "ADMIN", ["HR_EXIT_RECORD"]),
    ("PAYROLL_FINAL_SETTLEMENT", "Final payroll and entitlement settlement", "PAYROLL", ["HR_EXIT_RECORD"]),
    ("ACADEMY_CLOSE_LEARNING", "Close mandatory learning assignments", "ACADEMY", ["HR_EXIT_RECORD"]),
    ("OPS_REMOVE_ROSTER", "Remove future roster and operational assignments", "OPERATIONS", ["HR_EXIT_RECORD"]),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_ready() -> None:
    if not persistence.ENABLED or (persistence.schema_version() or 0) < REQUIRED_SCHEMA_VERSION:
        raise RecruitmentLifecycleError(
            f"Hiring lifecycle PostgreSQL V{REQUIRED_SCHEMA_VERSION} olmadan kullanılamaz."
        )


def _uuid(value: str, label: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as error:
        raise RecruitmentLifecycleError(f"{label} kimliği geçersiz.") from error


def _audit(cursor, event: str, actor: str, payload: dict[str, Any]) -> None:
    persistence._build_audit_record(cursor, event, actor, payload)


def create_offer_for_approval(
    request_id: str,
    candidate_id: str,
    *,
    package: dict[str, Any],
    expires_in_hours: int,
    actor: str,
) -> dict:
    """Create immutable offer package without issuing it to the candidate."""
    _ensure_ready()
    _candidate(request_id, candidate_id)
    if expires_in_hours < 1 or expires_in_hours > 24 * 30:
        raise RecruitmentLifecycleError("Offer validity 1 saat ile 30 gün arasında olmalıdır.")
    try:
        normalized, digest = _canonical_offer_package(package)
    except RecruitmentOrchestrationError as error:
        raise RecruitmentLifecycleError(str(error)) from error
    tenant = persistence.tenant_id()
    offer_id = uuid4()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        _, current_stage, _, _, _ = _assignment_locked(cursor, tenant, request_id, candidate_id)
        if current_stage != "OFFER":
            raise RecruitmentLifecycleError("Offer yalnız OFFER pipeline stage içinde hazırlanabilir.")
        cursor.execute(
            "SELECT COALESCE(max(version),0)+1 FROM recruitment.offer_packages WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s",
            (tenant, request_id, candidate_id),
        )
        version = int(cursor.fetchone()[0])
        expires_at = now + timedelta(hours=expires_in_hours)
        cursor.execute(
            """INSERT INTO recruitment.offer_packages(
                 tenant_id,offer_id,request_id,candidate_id,version,package_sha256,package,expires_at,created_at,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
            (tenant, offer_id, request_id, candidate_id, version, digest,
             json.dumps(normalized, ensure_ascii=False), expires_at, now, actor),
        )
        cursor.execute(
            """INSERT INTO recruitment.offer_approval_workflows(
                 tenant_id,offer_id,request_id,candidate_id,required_approvals,status,requested_by,requested_at
               ) VALUES(%s,%s,%s,%s,%s,'PENDING',%s,%s)""",
            (tenant, offer_id, request_id, candidate_id, _OFFER_APPROVAL_QUORUM, actor, now),
        )
        _audit(cursor, "RECRUITMENT_OFFER_APPROVAL_REQUESTED", actor, {
            "record_id": request_id, "candidate_id": candidate_id, "offer_id": str(offer_id),
            "version": version, "package_sha256": digest.hex(), "required_approvals": _OFFER_APPROVAL_QUORUM,
        })
        database.commit()
    return {
        "offer_id": str(offer_id), "version": version, "package_sha256": digest.hex(),
        "expires_at": expires_at.isoformat(), "approval_status": "PENDING",
        "required_approvals": _OFFER_APPROVAL_QUORUM, "approval_count": 0,
        "candidate_delivery_allowed": False, "immutable_package": True,
    }


def decide_offer_approval(offer_id: str, *, decision: str, reason: str, actor: str) -> dict:
    _ensure_ready()
    offer_uuid = _uuid(offer_id, "Offer")
    normalized = str(decision).strip().upper()
    if normalized not in {"APPROVED", "REJECTED"}:
        raise RecruitmentLifecycleError("Offer approval kararı APPROVED veya REJECTED olmalıdır.")
    note = str(reason or "").strip()
    if normalized == "REJECTED" and not note:
        raise RecruitmentLifecycleError("Offer rejection gerekçesi zorunludur.")
    if len(note) > 2000:
        raise RecruitmentLifecycleError("Offer approval gerekçesi çok uzun.")
    tenant = persistence.tenant_id()
    now = _now()
    approval_id = uuid4()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT request_id,candidate_id,required_approvals,status,requested_by,revision
               FROM recruitment.offer_approval_workflows
               WHERE tenant_id=%s AND offer_id=%s FOR UPDATE""",
            (tenant, offer_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Offer approval workflow bulunamadı.")
        request_id, candidate_id, required, status, requested_by, revision = row
        if status != "PENDING":
            raise RecruitmentLifecycleError("Offer approval workflow terminal state içinde.")
        if str(actor).strip().lower() == str(requested_by).strip().lower():
            raise RecruitmentLifecycleError("Offer hazırlayan kişi kendi teklifini onaylayamaz.")
        try:
            cursor.execute(
                """INSERT INTO recruitment.offer_approval_events(
                     tenant_id,approval_id,offer_id,approver_id,decision,reason,occurred_at
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                (tenant, approval_id, offer_uuid, actor, normalized, note, now),
            )
        except Exception as error:
            raise RecruitmentLifecycleError("Aynı approver bu teklif için daha önce karar vermiş.") from error
        if normalized == "REJECTED":
            cursor.execute(
                """UPDATE recruitment.offer_approval_workflows
                   SET status='REJECTED',decided_at=%s,revision=%s
                   WHERE tenant_id=%s AND offer_id=%s AND revision=%s""",
                (now, int(revision) + 1, tenant, offer_uuid, revision),
            )
            final_status = "REJECTED"
            approved_count = 0
        else:
            cursor.execute(
                """SELECT count(*) FROM recruitment.offer_approval_events
                   WHERE tenant_id=%s AND offer_id=%s AND decision='APPROVED'""",
                (tenant, offer_uuid),
            )
            approved_count = int(cursor.fetchone()[0])
            final_status = "APPROVED" if approved_count >= int(required) else "PENDING"
            cursor.execute(
                """UPDATE recruitment.offer_approval_workflows
                   SET status=%s,decided_at=%s,revision=%s
                   WHERE tenant_id=%s AND offer_id=%s AND revision=%s""",
                (final_status, now if final_status == "APPROVED" else None,
                 int(revision) + 1, tenant, offer_uuid, revision),
            )
            if cursor.rowcount != 1:
                raise RecruitmentLifecycleError("Offer approval concurrent update nedeniyle reddedildi.")
            if final_status == "APPROVED":
                cursor.execute(
                    "SELECT version,package_sha256 FROM recruitment.offer_packages WHERE tenant_id=%s AND offer_id=%s",
                    (tenant, offer_uuid),
                )
                package_row = cursor.fetchone()
                if package_row is None:
                    raise RecruitmentLifecycleError("Offer package bulunamadı.")
                version, package_digest = package_row
                cursor.execute(
                    """INSERT INTO recruitment.offer_events(
                         tenant_id,event_id,offer_id,request_id,candidate_id,decision,actor_type,actor_ref,occurred_at,metadata
                       ) VALUES(%s,%s,%s,%s,%s,'ISSUED','HR',%s,%s,%s::jsonb)""",
                    (tenant, uuid4(), offer_uuid, request_id, candidate_id,
                     f"approval-quorum:{approval_id}", now,
                     json.dumps({"version": int(version), "package_sha256": bytes(package_digest).hex(),
                                 "approval_count": approved_count}, ensure_ascii=False)),
                )
        _audit(cursor, f"RECRUITMENT_OFFER_APPROVAL_{normalized}", actor, {
            "record_id": request_id, "candidate_id": candidate_id, "offer_id": str(offer_uuid),
            "approval_id": str(approval_id), "approval_status": final_status,
            "approval_count": approved_count, "required_approvals": int(required),
        })
        database.commit()
    return {
        "offer_id": str(offer_uuid), "approval_id": str(approval_id), "decision": normalized,
        "approval_status": final_status, "approval_count": approved_count,
        "required_approvals": int(required), "candidate_delivery_allowed": final_status == "APPROVED",
    }


def offer_approval_summary(offer_id: str) -> dict:
    _ensure_ready()
    offer_uuid = _uuid(offer_id, "Offer")
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT request_id,candidate_id,required_approvals,status,requested_by,requested_at,decided_at,revision
               FROM recruitment.offer_approval_workflows WHERE tenant_id=%s AND offer_id=%s""",
            (tenant, offer_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Offer approval workflow bulunamadı.")
        cursor.execute(
            """SELECT approver_id,decision,reason,occurred_at FROM recruitment.offer_approval_events
               WHERE tenant_id=%s AND offer_id=%s ORDER BY occurred_at,approval_id""",
            (tenant, offer_uuid),
        )
        approvals = [
            {"approver_id": item[0], "decision": item[1], "reason": item[2], "occurred_at": item[3].isoformat()}
            for item in cursor.fetchall()
        ]
    return {
        "offer_id": str(offer_uuid), "request_id": row[0], "candidate_id": row[1],
        "required_approvals": int(row[2]), "status": row[3], "requested_by": row[4],
        "requested_at": row[5].isoformat(), "decided_at": row[6].isoformat() if row[6] else None,
        "revision": int(row[7]), "approvals": approvals,
        "candidate_delivery_allowed": row[3] == "APPROVED",
    }


def issue_approved_offer_capability(offer_id: str, *, expires_in_hours: int, actor: str) -> dict:
    summary = offer_approval_summary(offer_id)
    if summary["status"] != "APPROVED":
        raise RecruitmentLifecycleError("İki bağımsız offer approval tamamlanmadan candidate capability üretilemez.")
    try:
        result = issue_offer_decision_capability(offer_id, expires_in_hours=expires_in_hours, actor=actor)
    except RecruitmentOrchestrationError as error:
        raise RecruitmentLifecycleError(str(error)) from error
    return {**result, "approval_status": "APPROVED", "approval_count": len([a for a in summary["approvals"] if a["decision"] == "APPROVED"])}


def _assert_pii_minimized(payload: dict[str, Any]) -> None:
    def walk(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).strip().lower().replace("-", "_")
                if normalized in _FORBIDDEN_COMMUNICATION_KEYS:
                    raise RecruitmentLifecycleError(
                        f"Communication outbox ham PII taşıyamaz: {'.'.join((*path, str(key)))}"
                    )
                walk(child, (*path, str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))
    walk(payload)


def queue_candidate_communication(
    request_id: str,
    candidate_id: str,
    *,
    message_type: str,
    channel: str,
    locale: str,
    template_key: str,
    payload: dict[str, Any],
    idempotency_key: str,
    available_at: datetime | None,
    actor: str,
) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    message_type = str(message_type).strip().upper()
    channel = str(channel).strip().upper()
    if message_type not in _MESSAGE_TYPES or channel not in _CHANNELS:
        raise RecruitmentLifecycleError("Communication message_type/channel desteklenmiyor.")
    locale = str(locale or "tr-TR").strip()
    template_key = str(template_key).strip()
    key = str(idempotency_key).strip()
    if not locale or len(locale) > 20 or not template_key or len(template_key) > 120:
        raise RecruitmentLifecycleError("Communication locale/template geçersiz.")
    if not key or len(key) > 160:
        raise RecruitmentLifecycleError("Communication idempotency_key geçersiz.")
    _assert_pii_minimized(payload)
    when = available_at or _now()
    if when.tzinfo is None:
        raise RecruitmentLifecycleError("Communication available_at timezone-aware olmalıdır.")
    tenant = persistence.tenant_id()
    message_id = uuid4()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """INSERT INTO recruitment.candidate_communication_outbox(
                 tenant_id,message_id,request_id,candidate_id,message_type,channel,locale,template_key,payload,
                 idempotency_key,available_at,status,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,'QUEUED',%s)
               ON CONFLICT (tenant_id,idempotency_key) DO NOTHING RETURNING message_id""",
            (tenant, message_id, request_id, candidate_id, message_type, channel, locale, template_key,
             json.dumps(payload, ensure_ascii=False), key, when, actor),
        )
        inserted = cursor.fetchone()
        if inserted is None:
            cursor.execute(
                """SELECT message_id,status FROM recruitment.candidate_communication_outbox
                   WHERE tenant_id=%s AND idempotency_key=%s""",
                (tenant, key),
            )
            existing = cursor.fetchone()
            database.rollback()
            return {"message_id": str(existing[0]), "status": existing[1], "idempotent_replay": True}
        _audit(cursor, "RECRUITMENT_CANDIDATE_COMMUNICATION_QUEUED", actor, {
            "record_id": request_id, "candidate_id": candidate_id, "message_id": str(message_id),
            "message_type": message_type, "channel": channel, "template_key": template_key,
        })
        database.commit()
    return {"message_id": str(message_id), "status": "QUEUED", "idempotent_replay": False, "pii_minimized": True}


def list_candidate_communications(request_id: str, candidate_id: str) -> list[dict]:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT message_id,message_type,channel,locale,template_key,payload,available_at,status,attempts,
                      delivered_at,failure_code,created_at,created_by
               FROM recruitment.candidate_communication_outbox
               WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s
               ORDER BY created_at DESC""",
            (persistence.tenant_id(), request_id, candidate_id),
        )
        return [{
            "message_id": str(row[0]), "message_type": row[1], "channel": row[2], "locale": row[3],
            "template_key": row[4], "payload": row[5], "available_at": row[6].isoformat(), "status": row[7],
            "attempts": int(row[8]), "delivered_at": row[9].isoformat() if row[9] else None,
            "failure_code": row[10], "created_at": row[11].isoformat(), "created_by": row[12],
        } for row in cursor.fetchall()]


def claim_candidate_communications(*, worker: str, limit: int = 20) -> list[dict]:
    _ensure_ready()
    if not str(worker).strip() or limit < 1 or limit > 100:
        raise RecruitmentLifecycleError("Communication worker/limit geçersiz.")
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT message_id FROM recruitment.candidate_communication_outbox
               WHERE tenant_id=%s AND status IN ('QUEUED','FAILED') AND available_at<=%s AND attempts<20
               ORDER BY available_at,created_at
               FOR UPDATE SKIP LOCKED LIMIT %s""",
            (tenant, now, limit),
        )
        ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            database.commit()
            return []
        cursor.execute(
            """UPDATE recruitment.candidate_communication_outbox
               SET status='CLAIMED',claimed_at=%s,claimed_by=%s,attempts=attempts+1,revision=revision+1
               WHERE tenant_id=%s AND message_id=ANY(%s)
               RETURNING message_id,request_id,candidate_id,message_type,channel,locale,template_key,payload,attempts""",
            (now, worker, tenant, ids),
        )
        rows = cursor.fetchall()
        database.commit()
    return [{
        "message_id": str(row[0]), "request_id": row[1], "candidate_id": row[2], "message_type": row[3],
        "channel": row[4], "locale": row[5], "template_key": row[6], "payload": row[7], "attempt": int(row[8]),
        "recipient_resolution": "SECURE_CANDIDATE_PROFILE_LOOKUP_REQUIRED",
    } for row in rows]


def settle_candidate_communication(message_id: str, *, delivered: bool, failure_code: str, worker: str) -> dict:
    _ensure_ready()
    message_uuid = _uuid(message_id, "Message")
    failure = str(failure_code or "").strip()[:200]
    if not delivered and not failure:
        raise RecruitmentLifecycleError("Failed communication için failure_code zorunludur.")
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """UPDATE recruitment.candidate_communication_outbox
               SET status=%s,delivered_at=%s,failure_code=%s,revision=revision+1
               WHERE tenant_id=%s AND message_id=%s AND status='CLAIMED' AND claimed_by=%s
               RETURNING request_id,candidate_id,status""",
            ("SENT" if delivered else "FAILED", now if delivered else None, None if delivered else failure,
             tenant, message_uuid, worker),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Communication claim bulunamadı veya worker eşleşmiyor.")
        _audit(cursor, "RECRUITMENT_CANDIDATE_COMMUNICATION_SETTLED", worker, {
            "record_id": row[0], "candidate_id": row[1], "message_id": str(message_uuid), "status": row[2],
        })
        database.commit()
    return {"message_id": str(message_uuid), "status": row[2]}


def add_to_talent_pool(
    request_id: str,
    candidate_id: str,
    *,
    pool_key: str,
    tags: list[str],
    consent_basis: str,
    consent_record_ref: str,
    consent_days: int,
    actor: str,
) -> dict:
    _ensure_ready()
    _candidate(request_id, candidate_id)
    pool = str(pool_key).strip().upper()
    basis = str(consent_basis).strip().upper()
    ref = str(consent_record_ref).strip()
    clean_tags = sorted({str(tag).strip().upper() for tag in tags if str(tag).strip()})
    if not pool or len(pool) > 80 or len(clean_tags) > 20 or any(len(tag) > 80 for tag in clean_tags):
        raise RecruitmentLifecycleError("Talent pool key/tags geçersiz.")
    if basis not in {"EXPLICIT_CANDIDATE_CONSENT", "LEGITIMATE_INTEREST_REVIEWED"}:
        raise RecruitmentLifecycleError("Talent pool consent basis geçersiz.")
    if not ref or len(ref) > 240 or consent_days < 1 or consent_days > 730:
        raise RecruitmentLifecycleError("Talent pool consent reference/expiry geçersiz.")
    tenant = persistence.tenant_id()
    membership_id = uuid4()
    subject_key = uuid4()
    expires_at = _now() + timedelta(days=consent_days)
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT membership_id,subject_key,status,consent_expires_at FROM recruitment.talent_pool_memberships
               WHERE tenant_id=%s AND source_request_id=%s AND source_candidate_id=%s AND pool_key=%s
               ORDER BY created_at DESC LIMIT 1""",
            (tenant, request_id, candidate_id, pool),
        )
        existing = cursor.fetchone()
        if existing and existing[2] == "ACTIVE" and existing[3] > _now():
            return {"membership_id": str(existing[0]), "subject_key": str(existing[1]), "status": "ACTIVE", "idempotent_replay": True}
        cursor.execute(
            """INSERT INTO recruitment.talent_pool_memberships(
                 tenant_id,membership_id,subject_key,source_request_id,source_candidate_id,pool_key,tags,
                 consent_basis,consent_record_ref,consent_expires_at,status,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,'ACTIVE',%s)""",
            (tenant, membership_id, subject_key, request_id, candidate_id, pool,
             json.dumps(clean_tags), basis, ref, expires_at, actor),
        )
        _audit(cursor, "RECRUITMENT_TALENT_POOL_ADDED", actor, {
            "record_id": request_id, "candidate_id": candidate_id, "membership_id": str(membership_id),
            "subject_key": str(subject_key), "pool_key": pool, "consent_basis": basis,
        })
        database.commit()
    return {"membership_id": str(membership_id), "subject_key": str(subject_key), "status": "ACTIVE", "consent_expires_at": expires_at.isoformat(), "idempotent_replay": False}


def withdraw_talent_pool_membership(membership_id: str, *, actor: str) -> dict:
    _ensure_ready()
    membership_uuid = _uuid(membership_id, "Talent membership")
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """UPDATE recruitment.talent_pool_memberships
               SET status='WITHDRAWN',withdrawn_at=%s,withdrawn_by=%s,revision=revision+1
               WHERE tenant_id=%s AND membership_id=%s AND status='ACTIVE'
               RETURNING source_request_id,source_candidate_id,pool_key""",
            (now, actor, tenant, membership_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Aktif talent pool membership bulunamadı.")
        _audit(cursor, "RECRUITMENT_TALENT_POOL_WITHDRAWN", actor, {
            "record_id": row[0], "candidate_id": row[1], "membership_id": str(membership_uuid), "pool_key": row[2],
        })
        database.commit()
    return {"membership_id": str(membership_uuid), "status": "WITHDRAWN"}


def list_talent_pool(pool_key: str | None = None) -> list[dict]:
    _ensure_ready()
    tenant = persistence.tenant_id()
    params: list[Any] = [tenant]
    where = "tenant_id=%s"
    if pool_key:
        where += " AND pool_key=%s"
        params.append(str(pool_key).strip().upper())
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            f"""SELECT membership_id,subject_key,source_request_id,source_candidate_id,pool_key,tags,consent_basis,
                       consent_record_ref,consent_expires_at,status,created_at,created_by
                FROM recruitment.talent_pool_memberships WHERE {where}
                ORDER BY pool_key,created_at DESC""",
            tuple(params),
        )
        now = _now()
        return [{
            "membership_id": str(row[0]), "subject_key": str(row[1]), "source_request_id": row[2],
            "source_candidate_id": row[3], "pool_key": row[4], "tags": row[5], "consent_basis": row[6],
            "consent_record_ref": row[7], "consent_expires_at": row[8].isoformat(),
            "status": "EXPIRED" if row[9] == "ACTIVE" and row[8] <= now else row[9],
            "created_at": row[10].isoformat(), "created_by": row[11],
        } for row in cursor.fetchall()]


def create_offboarding_case(
    employee_id: str, *, effective_at: datetime, reason_code: str, note: str, actor: str
) -> dict:
    _ensure_ready()
    employee = str(employee_id).strip()
    reason = str(reason_code).strip().upper()
    if not employee or len(employee) > 80:
        raise RecruitmentLifecycleError("Employee id geçersiz.")
    if effective_at.tzinfo is None:
        raise RecruitmentLifecycleError("Offboarding effective_at timezone-aware olmalıdır.")
    if reason not in {"RESIGNATION", "TERMINATION", "TRANSFER", "CONTRACT_END", "OTHER"}:
        raise RecruitmentLifecycleError("Offboarding reason_code geçersiz.")
    if len(str(note or "")) > 2000:
        raise RecruitmentLifecycleError("Offboarding note çok uzun.")
    tenant = persistence.tenant_id()
    case_id = uuid4()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT 1 FROM recruitment.offboarding_cases
               WHERE tenant_id=%s AND employee_id=%s AND status IN ('OPEN','READY_TO_CLOSE') LIMIT 1""",
            (tenant, employee),
        )
        if cursor.fetchone() is not None:
            raise RecruitmentLifecycleError("Employee için açık offboarding case zaten mevcut.")
        cursor.execute(
            """INSERT INTO recruitment.offboarding_cases(
                 tenant_id,case_id,employee_id,effective_at,reason_code,note,status,created_at,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s,'OPEN',%s,%s)""",
            (tenant, case_id, employee, effective_at, reason, str(note or "").strip(), now, actor),
        )
        for task_key, title, owner_role, dependencies in _OFFBOARDING_TASKS:
            cursor.execute(
                """INSERT INTO recruitment.offboarding_tasks(
                     tenant_id,task_id,case_id,task_key,title,owner_role,required,dependencies,due_at,status
                   ) VALUES(%s,%s,%s,%s,%s,%s,true,%s::jsonb,%s,'PENDING')""",
                (tenant, uuid4(), case_id, task_key, title, owner_role,
                 json.dumps(dependencies), effective_at),
            )
        cursor.execute(
            """INSERT INTO recruitment.offboarding_events(tenant_id,event_id,case_id,event_type,actor_ref,metadata)
               VALUES(%s,%s,%s,'CREATED',%s,%s::jsonb)""",
            (tenant, uuid4(), case_id, actor, json.dumps({"employee_id": employee, "reason_code": reason})),
        )
        _audit(cursor, "RECRUITMENT_OFFBOARDING_CREATED", actor, {
            "employee_id": employee, "case_id": str(case_id), "reason_code": reason,
        })
        database.commit()
    return offboarding_summary(str(case_id))


def update_offboarding_task(task_id: str, *, status: str, note: str, actor: str) -> dict:
    _ensure_ready()
    task_uuid = _uuid(task_id, "Offboarding task")
    target = str(status).strip().upper()
    if target not in {"IN_PROGRESS", "BLOCKED", "COMPLETED", "WAIVED"}:
        raise RecruitmentLifecycleError("Offboarding task status geçersiz.")
    text = str(note or "").strip()
    if target == "WAIVED" and not text:
        raise RecruitmentLifecycleError("Offboarding waiver gerekçesi zorunludur.")
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT case_id,task_key,dependencies,status,revision FROM recruitment.offboarding_tasks
               WHERE tenant_id=%s AND task_id=%s FOR UPDATE""",
            (tenant, task_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Offboarding task bulunamadı.")
        case_id, task_key, dependencies, current, revision = row
        if current in {"COMPLETED", "WAIVED"}:
            raise RecruitmentLifecycleError("Terminal offboarding task tekrar değiştirilemez.")
        if target == "COMPLETED" and dependencies:
            cursor.execute(
                """SELECT task_key,status FROM recruitment.offboarding_tasks
                   WHERE tenant_id=%s AND case_id=%s AND task_key=ANY(%s)""",
                (tenant, case_id, list(dependencies)),
            )
            states = {key: state for key, state in cursor.fetchall()}
            missing = [key for key in dependencies if states.get(key) not in {"COMPLETED", "WAIVED"}]
            if missing:
                raise RecruitmentLifecycleError(f"Offboarding dependencies tamamlanmadı: {', '.join(missing)}")
        cursor.execute(
            """UPDATE recruitment.offboarding_tasks
               SET status=%s,completion_note=%s,completed_at=%s,completed_by=%s,revision=revision+1
               WHERE tenant_id=%s AND task_id=%s AND revision=%s""",
            (target, text or None, now if target in {"COMPLETED", "WAIVED"} else None,
             actor if target in {"COMPLETED", "WAIVED"} else None, tenant, task_uuid, revision),
        )
        if cursor.rowcount != 1:
            raise RecruitmentLifecycleError("Offboarding task concurrent update nedeniyle reddedildi.")
        cursor.execute(
            """INSERT INTO recruitment.offboarding_events(tenant_id,event_id,case_id,event_type,actor_ref,metadata)
               VALUES(%s,%s,%s,'TASK_UPDATED',%s,%s::jsonb)""",
            (tenant, uuid4(), case_id, actor, json.dumps({"task_id": str(task_uuid), "task_key": task_key, "status": target})),
        )
        cursor.execute(
            """SELECT count(*) FILTER (WHERE required),
                      count(*) FILTER (WHERE required AND status IN ('COMPLETED','WAIVED'))
               FROM recruitment.offboarding_tasks WHERE tenant_id=%s AND case_id=%s""",
            (tenant, case_id),
        )
        required, done = cursor.fetchone()
        if int(required) > 0 and int(required) == int(done):
            cursor.execute(
                """UPDATE recruitment.offboarding_cases SET status='READY_TO_CLOSE',revision=revision+1
                   WHERE tenant_id=%s AND case_id=%s AND status='OPEN'""",
                (tenant, case_id),
            )
            if cursor.rowcount:
                cursor.execute(
                    """INSERT INTO recruitment.offboarding_events(tenant_id,event_id,case_id,event_type,actor_ref,metadata)
                       VALUES(%s,%s,%s,'READY_TO_CLOSE',%s,'{}'::jsonb)""",
                    (tenant, uuid4(), case_id, actor),
                )
        _audit(cursor, "RECRUITMENT_OFFBOARDING_TASK_UPDATED", actor, {
            "case_id": str(case_id), "task_id": str(task_uuid), "task_key": task_key, "status": target,
        })
        database.commit()
    return offboarding_summary(str(case_id))


def close_offboarding_case(case_id: str, *, actor: str) -> dict:
    _ensure_ready()
    case_uuid = _uuid(case_id, "Offboarding case")
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT employee_id,status,revision FROM recruitment.offboarding_cases
               WHERE tenant_id=%s AND case_id=%s FOR UPDATE""",
            (tenant, case_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Offboarding case bulunamadı.")
        employee_id, status, revision = row
        if status != "READY_TO_CLOSE":
            raise RecruitmentLifecycleError("Tüm required offboarding task tamamlanmadan case kapatılamaz.")
        cursor.execute(
            """UPDATE recruitment.offboarding_cases
               SET status='CLOSED',closed_at=%s,closed_by=%s,revision=%s
               WHERE tenant_id=%s AND case_id=%s AND revision=%s""",
            (now, actor, int(revision) + 1, tenant, case_uuid, revision),
        )
        if cursor.rowcount != 1:
            raise RecruitmentLifecycleError("Offboarding case concurrent update nedeniyle reddedildi.")
        cursor.execute(
            """INSERT INTO recruitment.offboarding_events(tenant_id,event_id,case_id,event_type,actor_ref,metadata)
               VALUES(%s,%s,%s,'CLOSED',%s,%s::jsonb)""",
            (tenant, uuid4(), case_uuid, actor, json.dumps({"employee_id": employee_id})),
        )
        _audit(cursor, "RECRUITMENT_OFFBOARDING_CLOSED", actor, {"employee_id": employee_id, "case_id": str(case_uuid)})
        database.commit()
    return offboarding_summary(str(case_uuid))


def offboarding_summary(case_id: str) -> dict:
    _ensure_ready()
    case_uuid = _uuid(case_id, "Offboarding case")
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT employee_id,effective_at,reason_code,note,status,created_at,created_by,closed_at,closed_by,revision
               FROM recruitment.offboarding_cases WHERE tenant_id=%s AND case_id=%s""",
            (tenant, case_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecruitmentLifecycleError("Offboarding case bulunamadı.")
        cursor.execute(
            """SELECT task_id,task_key,title,owner_role,required,dependencies,due_at,status,completion_note,
                      completed_at,completed_by,revision
               FROM recruitment.offboarding_tasks WHERE tenant_id=%s AND case_id=%s ORDER BY task_key""",
            (tenant, case_uuid),
        )
        tasks = [{
            "task_id": str(item[0]), "task_key": item[1], "title": item[2], "owner_role": item[3],
            "required": bool(item[4]), "dependencies": item[5], "due_at": item[6].isoformat() if item[6] else None,
            "status": item[7], "completion_note": item[8],
            "completed_at": item[9].isoformat() if item[9] else None, "completed_by": item[10], "revision": int(item[11]),
        } for item in cursor.fetchall()]
    return {
        "case_id": str(case_uuid), "employee_id": row[0], "effective_at": row[1].isoformat(),
        "reason_code": row[2], "note": row[3], "status": row[4], "created_at": row[5].isoformat(),
        "created_by": row[6], "closed_at": row[7].isoformat() if row[7] else None, "closed_by": row[8],
        "revision": int(row[9]), "tasks": tasks,
        "close_allowed": row[4] == "READY_TO_CLOSE",
    }


def list_offboarding_cases() -> list[dict]:
    _ensure_ready()
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT case_id FROM recruitment.offboarding_cases
               WHERE tenant_id=%s ORDER BY effective_at DESC,created_at DESC""",
            (tenant,),
        )
        ids = [str(row[0]) for row in cursor.fetchall()]
    return [offboarding_summary(case_id) for case_id in ids]
