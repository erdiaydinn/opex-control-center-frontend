"""Candidate self-service interview scheduling with rotating capabilities.

Interview slots are shared by vacancy+pipeline stage, so candidates compete for
real capacity under PostgreSQL row locks. Candidate mutations revoke the presented
capability and return a fresh successor token; replayed mutation links fail closed.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import secrets
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.workforce import persistence


class InterviewSchedulingError(ValueError):
    pass


REQUIRED_SCHEMA_VERSION = 46


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_ready() -> None:
    if not persistence.ENABLED or (persistence.schema_version() or 0) < REQUIRED_SCHEMA_VERSION:
        raise InterviewSchedulingError(
            f"Interview scheduling PostgreSQL V{REQUIRED_SCHEMA_VERSION} olmadan kullanılamaz."
        )


def _candidate_exists(request_id: str, candidate_id: str) -> tuple[dict, dict]:
    from .service import list_requests
    record = next((row for row in list_requests() if row.get("id") == request_id), None)
    candidate = next((row for row in (record or {}).get("candidates", []) if row.get("id") == candidate_id), None)
    if record is None or candidate is None:
        raise InterviewSchedulingError("Recruitment request/candidate bulunamadı.")
    if candidate.get("status") in {"REJECTED", "HIRED"}:
        raise InterviewSchedulingError("Terminal candidate için mülakat planlanamaz.")
    return record, candidate


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise InterviewSchedulingError("Interview slot tarih/saat bilgisi timezone içermelidir.")
    return value.astimezone(UTC)


def create_schedule(
    request_id: str,
    candidate_id: str,
    *,
    title: str,
    timezone: str,
    meeting_mode: str,
    location_label: str,
    instructions: str,
    duration_minutes: int,
    slots: list[dict[str, Any]],
    actor: str,
) -> dict:
    """Create a shared vacancy/stage slot pool, using candidate_id only to resolve stage."""
    _ensure_ready()
    _candidate_exists(request_id, candidate_id)
    try:
        ZoneInfo(str(timezone))
    except ZoneInfoNotFoundError as error:
        raise InterviewSchedulingError("Geçerli bir IANA timezone gereklidir.") from error
    mode = str(meeting_mode).strip().upper()
    if mode not in {"ONSITE", "REMOTE", "PHONE"}:
        raise InterviewSchedulingError("Interview meeting mode desteklenmiyor.")
    title = str(title).strip()
    location_label = str(location_label or "").strip()
    instructions = str(instructions or "").strip()
    if not title or len(title) > 180 or len(location_label) > 500 or len(instructions) > 2000:
        raise InterviewSchedulingError("Interview başlık/lokasyon/talimat alanları geçersiz.")
    duration = int(duration_minutes)
    if duration < 10 or duration > 480 or not 1 <= len(slots) <= 40:
        raise InterviewSchedulingError("Interview duration veya slot sayısı geçersiz.")
    normalized: list[tuple[datetime, datetime, int]] = []
    now = _now()
    for raw in slots:
        starts = _aware(raw["starts_at"])
        ends = _aware(raw.get("ends_at") or (starts + timedelta(minutes=duration)))
        capacity = int(raw.get("capacity", 1))
        if starts <= now or ends <= starts or int((ends - starts).total_seconds()) != duration * 60:
            raise InterviewSchedulingError("Slot gelecekte olmalı ve schedule duration ile tam eşleşmelidir.")
        if capacity < 1 or capacity > 20:
            raise InterviewSchedulingError("Slot capacity 1-20 arasında olmalıdır.")
        normalized.append((starts, ends, capacity))
    normalized.sort(key=lambda row: row[0])
    for previous, current in zip(normalized, normalized[1:]):
        if current[0] < previous[1]:
            raise InterviewSchedulingError("Aynı interview schedule içinde slotlar çakışamaz.")

    tenant = persistence.tenant_id()
    schedule_id = uuid4()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT a.current_stage FROM recruitment.pipeline_assignments a
               WHERE a.tenant_id=%s AND a.request_id=%s AND a.candidate_id=%s""",
            (tenant, request_id, candidate_id),
        )
        stage_row = cursor.fetchone()
        if stage_row is None:
            raise InterviewSchedulingError("Interview schedule için candidate pipeline ataması zorunludur.")
        stage = str(stage_row[0])
        if stage in {"OFFER", "READY_TO_HIRE"}:
            raise InterviewSchedulingError("Offer/READY_TO_HIRE aşamasında yeni mülakat açılamaz.")
        cursor.execute(
            """INSERT INTO recruitment.interview_schedules(
                 tenant_id,schedule_id,request_id,stage,title,timezone,
                 meeting_mode,location_label,instructions,duration_minutes,created_by
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (tenant, schedule_id, request_id, stage, title, timezone, mode,
             location_label, instructions, duration, actor),
        )
        slot_rows = []
        for starts, ends, capacity in normalized:
            slot_id = uuid4()
            cursor.execute(
                """INSERT INTO recruitment.interview_slots(
                     tenant_id,slot_id,schedule_id,starts_at,ends_at,capacity
                   ) VALUES(%s,%s,%s,%s,%s,%s)""",
                (tenant, slot_id, schedule_id, starts, ends, capacity),
            )
            slot_rows.append({"slot_id": str(slot_id), "starts_at": starts.isoformat(), "ends_at": ends.isoformat(), "capacity": capacity})
        persistence._build_audit_record(
            cursor,
            "RECRUITMENT_INTERVIEW_SCHEDULE_CREATED",
            actor,
            {"record_id": request_id, "seed_candidate_id": candidate_id, "schedule_id": str(schedule_id), "stage": stage, "slot_count": len(slot_rows), "meeting_mode": mode},
        )
        database.commit()
    return {
        "schedule_id": str(schedule_id), "request_id": request_id, "stage": stage, "title": title,
        "timezone": timezone, "meeting_mode": mode, "location_label": location_label,
        "instructions": instructions, "duration_minutes": duration, "status": "OPEN", "slots": slot_rows,
        "capacity_scope": "VACANCY_STAGE_SHARED",
    }


def schedule_scope(schedule_id: str) -> str:
    _ensure_ready()
    try:
        schedule_uuid = UUID(str(schedule_id))
    except ValueError as error:
        raise InterviewSchedulingError("Interview schedule kimliği geçersiz.") from error
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            "SELECT request_id FROM recruitment.interview_schedules WHERE tenant_id=%s AND schedule_id=%s",
            (persistence.tenant_id(), schedule_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise InterviewSchedulingError("Interview schedule bulunamadı.")
        return str(row[0])


def list_candidate_schedules(request_id: str, candidate_id: str) -> list[dict]:
    _ensure_ready()
    _candidate_exists(request_id, candidate_id)
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT s.schedule_id,s.stage,s.title,s.timezone,s.meeting_mode,s.location_label,
                      s.instructions,s.duration_minutes,s.status,s.revision,s.created_at,
                      b.booking_id,b.slot_id,b.status
               FROM recruitment.interview_schedules s
               LEFT JOIN recruitment.interview_bookings b
                 ON b.tenant_id=s.tenant_id AND b.schedule_id=s.schedule_id AND b.candidate_id=%s
               WHERE s.tenant_id=%s AND s.request_id=%s
               ORDER BY s.created_at DESC""",
            (candidate_id, tenant, request_id),
        )
        return [
            {
                "schedule_id": str(row[0]), "stage": row[1], "title": row[2], "timezone": row[3],
                "meeting_mode": row[4], "location_label": row[5], "instructions": row[6],
                "duration_minutes": int(row[7]), "status": row[8], "revision": int(row[9]),
                "created_at": row[10].isoformat(),
                "booking": None if row[11] is None else {"booking_id": str(row[11]), "slot_id": str(row[12]) if row[12] else None, "status": row[13]},
            }
            for row in cursor.fetchall()
        ]


def update_schedule_status(schedule_id: str, target_status: str, actor: str) -> dict:
    _ensure_ready()
    try:
        schedule_uuid = UUID(str(schedule_id))
    except ValueError as error:
        raise InterviewSchedulingError("Interview schedule kimliği geçersiz.") from error
    target = str(target_status).strip().upper()
    if target not in {"OPEN", "CLOSED", "CANCELLED"}:
        raise InterviewSchedulingError("Interview schedule status geçersiz.")
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT request_id,status,revision FROM recruitment.interview_schedules
               WHERE tenant_id=%s AND schedule_id=%s FOR UPDATE""",
            (tenant, schedule_uuid),
        )
        row = cursor.fetchone()
        if row is None:
            raise InterviewSchedulingError("Interview schedule bulunamadı.")
        request_id, current, revision = row
        if current == "CANCELLED":
            raise InterviewSchedulingError("İptal edilmiş interview schedule yeniden açılamaz.")
        next_revision = int(revision) + 1
        cursor.execute(
            """UPDATE recruitment.interview_schedules SET status=%s,revision=%s
               WHERE tenant_id=%s AND schedule_id=%s AND revision=%s""",
            (target, next_revision, tenant, schedule_uuid, revision),
        )
        if cursor.rowcount != 1:
            raise InterviewSchedulingError("Interview schedule eşzamanlı değişiklik nedeniyle güncellenemedi.")
        persistence._build_audit_record(
            cursor, "RECRUITMENT_INTERVIEW_SCHEDULE_STATUS_CHANGED", actor,
            {"record_id": request_id, "schedule_id": str(schedule_uuid), "from_status": current, "to_status": target},
        )
        database.commit()
    return {"schedule_id": str(schedule_uuid), "request_id": request_id, "status": target, "revision": next_revision}


def issue_booking_capability(schedule_id: str, candidate_id: str, *, expires_in_hours: int, actor: str) -> dict:
    _ensure_ready()
    if expires_in_hours < 1 or expires_in_hours > 24 * 30:
        raise InterviewSchedulingError("Interview capability validity geçersiz.")
    try:
        schedule_uuid = UUID(str(schedule_id))
    except ValueError as error:
        raise InterviewSchedulingError("Interview schedule kimliği geçersiz.") from error
    tenant = persistence.tenant_id()
    now = _now()
    token = secrets.token_urlsafe(40)
    capability_id = uuid4()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        cursor.execute(
            """SELECT request_id,stage,status FROM recruitment.interview_schedules
               WHERE tenant_id=%s AND schedule_id=%s FOR UPDATE""",
            (tenant, schedule_uuid),
        )
        schedule = cursor.fetchone()
        if schedule is None or schedule[2] != "OPEN":
            raise InterviewSchedulingError("Interview schedule açık değil.")
        request_id, schedule_stage, _ = schedule
        _candidate_exists(str(request_id), candidate_id)
        cursor.execute(
            """SELECT current_stage FROM recruitment.pipeline_assignments
               WHERE tenant_id=%s AND request_id=%s AND candidate_id=%s""",
            (tenant, request_id, candidate_id),
        )
        assignment = cursor.fetchone()
        if assignment is None or str(assignment[0]) != str(schedule_stage):
            raise InterviewSchedulingError("Aday mevcut pipeline stage ile bu interview schedule arasında eşleşmiyor.")
        cursor.execute(
            """UPDATE recruitment.interview_booking_capabilities SET revoked_at=%s
               WHERE tenant_id=%s AND schedule_id=%s AND candidate_id=%s AND revoked_at IS NULL""",
            (now, tenant, schedule_uuid, candidate_id),
        )
        expires_at = now + timedelta(hours=expires_in_hours)
        cursor.execute(
            """INSERT INTO recruitment.interview_booking_capabilities(
                 tenant_id,capability_id,schedule_id,candidate_id,token_sha256,generation,
                 expires_at,issued_at,issued_by
               ) VALUES(%s,%s,%s,%s,%s,1,%s,%s,%s)""",
            (tenant, capability_id, schedule_uuid, candidate_id, sha256(token.encode()).digest(), expires_at, now, actor),
        )
        persistence._build_audit_record(
            cursor, "RECRUITMENT_INTERVIEW_CAPABILITY_ISSUED", actor,
            {"record_id": request_id, "candidate_id": candidate_id, "schedule_id": str(schedule_uuid), "capability_id": str(capability_id)},
        )
        database.commit()
    return {"capability": token, "capability_id": str(capability_id), "schedule_id": str(schedule_uuid), "candidate_id": candidate_id, "expires_at": expires_at.isoformat(), "generation": 1}


def _capability_row(cursor, tenant: str, token: str, *, lock: bool):
    if len(token) < 40 or len(token) > 256:
        raise InterviewSchedulingError("Interview capability geçersiz veya süresi dolmuş.")
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        """SELECT capability_id,schedule_id,candidate_id,generation,expires_at,revoked_at
           FROM recruitment.interview_booking_capabilities
           WHERE tenant_id=%s AND token_sha256=%s""" + suffix,
        (tenant, sha256(token.encode()).digest()),
    )
    row = cursor.fetchone()
    if row is None or row[5] is not None or row[4] <= _now():
        raise InterviewSchedulingError("Interview capability geçersiz veya süresi dolmuş.")
    return row


def _slot_snapshot(cursor, tenant: str, schedule_id: UUID) -> list[dict]:
    cursor.execute(
        """SELECT s.slot_id,s.starts_at,s.ends_at,s.capacity,s.status,
                  count(b.booking_id) FILTER (WHERE b.status='BOOKED')
           FROM recruitment.interview_slots s
           LEFT JOIN recruitment.interview_bookings b
             ON b.tenant_id=s.tenant_id AND b.slot_id=s.slot_id
           WHERE s.tenant_id=%s AND s.schedule_id=%s
           GROUP BY s.slot_id,s.starts_at,s.ends_at,s.capacity,s.status
           ORDER BY s.starts_at""",
        (tenant, schedule_id),
    )
    return [
        {"slot_id": str(row[0]), "starts_at": row[1].isoformat(), "ends_at": row[2].isoformat(),
         "capacity": int(row[3]), "status": row[4], "remaining": max(0, int(row[3]) - int(row[5] or 0))}
        for row in cursor.fetchall()
    ]


def view_candidate_schedule(raw_token: str) -> dict:
    _ensure_ready()
    token = str(raw_token or "").strip()
    tenant = persistence.tenant_id()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        _, schedule_id, candidate_id, generation, expires_at, _ = _capability_row(cursor, tenant, token, lock=False)
        cursor.execute(
            """SELECT request_id,stage,title,timezone,meeting_mode,location_label,instructions,
                      duration_minutes,status FROM recruitment.interview_schedules
               WHERE tenant_id=%s AND schedule_id=%s""",
            (tenant, schedule_id),
        )
        schedule = cursor.fetchone()
        if schedule is None:
            raise InterviewSchedulingError("Interview schedule bulunamadı.")
        cursor.execute(
            """SELECT booking_id,slot_id,status,revision FROM recruitment.interview_bookings
               WHERE tenant_id=%s AND schedule_id=%s AND candidate_id=%s""",
            (tenant, schedule_id, candidate_id),
        )
        booking = cursor.fetchone()
        slots = _slot_snapshot(cursor, tenant, schedule_id)
        database.rollback()
    return {
        "schedule_id": str(schedule_id), "stage": schedule[1], "title": schedule[2], "timezone": schedule[3],
        "meeting_mode": schedule[4], "location_label": schedule[5], "instructions": schedule[6],
        "duration_minutes": int(schedule[7]), "status": schedule[8], "slots": slots,
        "booking": None if booking is None else {"booking_id": str(booking[0]), "slot_id": str(booking[1]) if booking[1] else None, "status": booking[2], "revision": int(booking[3])},
        "capability_generation": int(generation), "capability_expires_at": expires_at.isoformat(),
        "truth_boundary": "CANDIDATE_BOUND_ROTATING_SCHEDULING_CAPABILITY_SHARED_SLOT_CAPACITY",
    }


def _rotate_capability(cursor, tenant: str, capability, now: datetime) -> tuple[str, int]:
    capability_id, schedule_id, candidate_id, generation, expires_at, _ = capability
    next_token = secrets.token_urlsafe(40)
    next_id = uuid4()
    next_generation = int(generation) + 1
    # Revoke old first; the partial unique index permits exactly one active token.
    cursor.execute(
        """UPDATE recruitment.interview_booking_capabilities
           SET revoked_at=%s,successor_capability_id=%s
           WHERE tenant_id=%s AND capability_id=%s AND revoked_at IS NULL""",
        (now, next_id, tenant, capability_id),
    )
    if cursor.rowcount != 1:
        raise InterviewSchedulingError("Interview capability replay reddedildi.")
    cursor.execute(
        """INSERT INTO recruitment.interview_booking_capabilities(
             tenant_id,capability_id,schedule_id,candidate_id,token_sha256,generation,
             expires_at,issued_at,issued_by
           ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'CAPABILITY_ROTATION')""",
        (tenant, next_id, schedule_id, candidate_id, sha256(next_token.encode()).digest(), next_generation, expires_at, now),
    )
    return next_token, next_generation


def mutate_candidate_booking(raw_token: str, action: str, slot_id: str | None = None) -> dict:
    _ensure_ready()
    token = str(raw_token or "").strip()
    operation = str(action or "").strip().upper()
    if operation not in {"BOOK", "RESCHEDULE", "CANCEL"}:
        raise InterviewSchedulingError("Interview booking işlemi desteklenmiyor.")
    tenant = persistence.tenant_id()
    now = _now()
    with persistence.connection() as database, database.cursor() as cursor:
        persistence._set_tenant(cursor)
        capability = _capability_row(cursor, tenant, token, lock=True)
        capability_id, schedule_id, candidate_id, _, _, _ = capability
        cursor.execute(
            """SELECT request_id,status FROM recruitment.interview_schedules
               WHERE tenant_id=%s AND schedule_id=%s FOR UPDATE""",
            (tenant, schedule_id),
        )
        schedule = cursor.fetchone()
        if schedule is None or schedule[1] != "OPEN":
            raise InterviewSchedulingError("Interview schedule self-service için açık değil.")
        request_id = schedule[0]
        cursor.execute(
            """SELECT booking_id,slot_id,status,revision FROM recruitment.interview_bookings
               WHERE tenant_id=%s AND schedule_id=%s AND candidate_id=%s FOR UPDATE""",
            (tenant, schedule_id, candidate_id),
        )
        booking = cursor.fetchone()
        old_slot = booking[1] if booking else None
        if operation in {"BOOK", "RESCHEDULE"}:
            try:
                target_slot = UUID(str(slot_id))
            except (TypeError, ValueError) as error:
                raise InterviewSchedulingError("Geçerli interview slot seçilmelidir.") from error
            # All candidates lock the shared slot row before counting occupancy.
            cursor.execute(
                """SELECT starts_at,ends_at,capacity,status FROM recruitment.interview_slots
                   WHERE tenant_id=%s AND schedule_id=%s AND slot_id=%s FOR UPDATE""",
                (tenant, schedule_id, target_slot),
            )
            slot = cursor.fetchone()
            if slot is None or slot[3] != "OPEN" or slot[0] <= now:
                raise InterviewSchedulingError("Interview slot artık uygun değil.")
            if operation == "BOOK" and booking is not None and booking[2] == "BOOKED":
                raise InterviewSchedulingError("Adayın aktif interview booking kaydı zaten var; yeniden planlama kullanın.")
            if operation == "RESCHEDULE" and (booking is None or booking[2] != "BOOKED"):
                raise InterviewSchedulingError("Yeniden planlama için aktif booking bulunamadı.")
            if old_slot == target_slot and booking and booking[2] == "BOOKED":
                raise InterviewSchedulingError("Yeni slot mevcut booking ile aynı.")
            cursor.execute(
                """SELECT count(*) FROM recruitment.interview_bookings
                   WHERE tenant_id=%s AND slot_id=%s AND status='BOOKED' AND candidate_id<>%s""",
                (tenant, target_slot, candidate_id),
            )
            occupied = int(cursor.fetchone()[0])
            if occupied >= int(slot[2]):
                raise InterviewSchedulingError("Seçilen interview slot doldu; başka bir slot seçin.")
            if booking is None:
                booking_id = uuid4()
                cursor.execute(
                    """INSERT INTO recruitment.interview_bookings(
                         tenant_id,booking_id,schedule_id,request_id,candidate_id,slot_id,status,booked_at,updated_at
                       ) VALUES(%s,%s,%s,%s,%s,%s,'BOOKED',%s,%s)""",
                    (tenant, booking_id, schedule_id, request_id, candidate_id, target_slot, now, now),
                )
                event_type = "BOOKED"
                revision = 1
            else:
                booking_id, _, _, current_revision = booking
                revision = int(current_revision) + 1
                cursor.execute(
                    """UPDATE recruitment.interview_bookings
                       SET slot_id=%s,status='BOOKED',revision=%s,booked_at=COALESCE(booked_at,%s),updated_at=%s
                       WHERE tenant_id=%s AND booking_id=%s AND revision=%s""",
                    (target_slot, revision, now, now, tenant, booking_id, current_revision),
                )
                if cursor.rowcount != 1:
                    raise InterviewSchedulingError("Interview booking eşzamanlı değişiklik nedeniyle reddedildi.")
                event_type = "RESCHEDULED" if operation == "RESCHEDULE" else "BOOKED"
            new_slot = target_slot
        else:
            if booking is None or booking[2] != "BOOKED":
                raise InterviewSchedulingError("İptal edilecek aktif interview booking bulunamadı.")
            booking_id, old_slot, _, current_revision = booking
            revision = int(current_revision) + 1
            cursor.execute(
                """UPDATE recruitment.interview_bookings
                   SET status='CANCELLED',revision=%s,updated_at=%s
                   WHERE tenant_id=%s AND booking_id=%s AND revision=%s""",
                (revision, now, tenant, booking_id, current_revision),
            )
            if cursor.rowcount != 1:
                raise InterviewSchedulingError("Interview booking eşzamanlı değişiklik nedeniyle reddedildi.")
            new_slot = None
            event_type = "CANCELLED"

        cursor.execute(
            """INSERT INTO recruitment.interview_booking_events(
                 tenant_id,event_id,booking_id,schedule_id,request_id,candidate_id,
                 from_slot_id,to_slot_id,event_type,actor_type,actor_ref,occurred_at,metadata
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'CANDIDATE_CAPABILITY',%s,%s,%s::jsonb)""",
            (tenant, uuid4(), booking_id, schedule_id, request_id, candidate_id, old_slot, new_slot,
             event_type, str(capability_id), now, json.dumps({"capability_generation": int(capability[3])})),
        )
        next_token, next_generation = _rotate_capability(cursor, tenant, capability, now)
        persistence._build_audit_record(
            cursor, f"RECRUITMENT_INTERVIEW_{event_type}", f"candidate-capability:{capability_id}",
            {"record_id": request_id, "candidate_id": candidate_id, "schedule_id": str(schedule_id), "booking_id": str(booking_id), "from_slot_id": str(old_slot) if old_slot else None, "to_slot_id": str(new_slot) if new_slot else None},
        )
        database.commit()
    return {
        "accepted": True, "event": event_type, "booking_id": str(booking_id), "revision": revision,
        "next_capability": next_token, "next_capability_generation": next_generation,
        "schedule": view_candidate_schedule(next_token),
    }
