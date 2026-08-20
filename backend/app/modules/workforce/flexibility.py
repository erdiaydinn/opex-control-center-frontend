from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from threading import Lock
from zoneinfo import ZoneInfo

from . import persistence, service
from .work_activity_catalog import resolve_activity_bundle


_AVAILABILITY_COLLECTION = "workforce_availability"
_OPEN_SHIFT_COLLECTION = "workforce_open_shifts"
_LOCK = Lock()


def _normal(value: object | None) -> str:
    return str(value or "").strip().casefold().replace("i̇", "i")


def _clock_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _interval(start: str, end: str) -> tuple[int, int]:
    begin = _clock_minutes(start)
    finish = _clock_minutes(end)
    if finish <= begin:
        finish += 24 * 60
    return begin, finish


def _window_contains(window_start: str, window_end: str, start: str, end: str) -> bool:
    window_begin, window_finish = _interval(window_start, window_end)
    begin, finish = _interval(start, end)
    return begin >= window_begin and finish <= window_finish


def _availability_id(person_id: str, day: str) -> str:
    digest = sha256(f"{person_id}|{day}".encode()).hexdigest()[:20]
    return f"AVA-{digest}"


def _load_availability() -> list[dict]:
    return persistence.load_collection(_AVAILABILITY_COLLECTION)


def _load_open_shifts() -> list[dict]:
    return persistence.load_collection(_OPEN_SHIFT_COLLECTION)


def _persist_collection(kind: str, rows: list[dict], event: str, actor: str, **details: object) -> None:
    try:
        persistence.persist_snapshot_with_audit({kind: rows}, event, actor, **details)
    except persistence.ConcurrentWriteError as error:
        raise service.WorkforceRuleError(
            "Workforce esneklik verisi başka bir işlem tarafından güncellendi; işlem güvenli biçimde durduruldu, tekrar deneyin."
        ) from error


def list_availability(person_id: str, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    rows = [row for row in _load_availability() if str(row.get("person_id")) == str(person_id)]
    if start_date:
        rows = [row for row in rows if str(row.get("date")) >= start_date]
    if end_date:
        rows = [row for row in rows if str(row.get("date")) <= end_date]
    return deepcopy(sorted(rows, key=lambda row: str(row.get("date"))))


def upsert_availability(payload: dict, actor: str) -> dict:
    person_id = str(payload["person_id"])
    person = service.resolve_person_identity(person_id, "EMPLOYEE_ID")
    if person is None:
        raise service.WorkforceRuleError("Employee Master kaydı bulunamadı.")
    if not service.person_has_workforce_access(person, str(payload["date"])):
        raise service.WorkforceRuleError("Pasif veya işten ayrılmış personel uygunluk kaydı oluşturamaz.")

    with _LOCK:
        rows = _load_availability()
        record_id = _availability_id(person_id, str(payload["date"]))
        now = datetime.now(ZoneInfo("UTC")).isoformat()
        record = {
            "id": record_id,
            "person_id": person_id,
            "date": str(payload["date"]),
            "available": bool(payload.get("available", True)),
            "earliest_start": payload.get("earliest_start"),
            "latest_end": payload.get("latest_end"),
            "preferred_start": payload.get("preferred_start"),
            "preferred_end": payload.get("preferred_end"),
            "note": str(payload.get("note") or "")[:500],
            "updated_at": now,
            "updated_by": actor,
        }
        existing = next((row for row in rows if row.get("id") == record_id), None)
        if existing:
            record["created_at"] = existing.get("created_at") or now
            record["created_by"] = existing.get("created_by") or actor
            existing.clear()
            existing.update(record)
        else:
            record["created_at"] = now
            record["created_by"] = actor
            rows.append(record)
        _persist_collection(
            _AVAILABILITY_COLLECTION,
            rows,
            "WORKFORCE_AVAILABILITY_UPSERTED",
            actor,
            record_id=record_id,
            person_id=person_id,
            date=record["date"],
            available=record["available"],
            has_hard_window=bool(record["earliest_start"] and record["latest_end"]),
            has_preference_window=bool(record["preferred_start"] and record["preferred_end"]),
        )
        return deepcopy(record)


def _warehouse_record(warehouse_id: str) -> dict | None:
    candidate = _normal(warehouse_id)
    for warehouse in service.list_warehouses():
        aliases = {
            _normal(warehouse.get("id")),
            _normal(warehouse.get("code")),
            _normal(warehouse.get("name")),
            _normal(str(warehouse.get("name") or "").split(" (")[0]),
        }
        if candidate in aliases:
            return warehouse
    return None


def _warehouse_matches(person: dict, offer: dict) -> bool:
    person_aliases = {
        _normal(person.get("warehouse_id")),
        _normal(person.get("warehouse")),
        _normal(str(person.get("warehouse") or "").split(" (")[0]),
    }
    offer_aliases = {
        _normal(offer.get("warehouse_id")),
        _normal(offer.get("warehouse")),
        _normal(str(offer.get("warehouse") or "").split(" (")[0]),
    }
    person_aliases.discard("")
    offer_aliases.discard("")
    return bool(person_aliases and offer_aliases and person_aliases.intersection(offer_aliases))


def _capability_keys(person: dict, field: str) -> set[str]:
    values = person.get(field) or []
    if not isinstance(values, (list, tuple, set, frozenset)):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def _activity_summary(row: dict) -> dict:
    return {
        "activity_key": str(row["activity_key"]),
        "activity_version": int(row["version"]),
        "display_name": str(row["display_name"]),
        "category": str(row["category"]),
        "unit_key": str(row["unit_key"]),
        "demand_mode": str(row["demand_mode"]),
        "required_skill_keys": list(row.get("required_skill_keys") or []),
        "required_certification_keys": list(row.get("required_certification_keys") or []),
        "required_equipment_keys": list(row.get("required_equipment_keys") or []),
        "safety_tags": list(row.get("safety_tags") or []),
        "location_types": list(row.get("location_types") or []),
        "authority_ref": str(row.get("id") or f"{row['activity_key']}:v{row['version']}"),
        "source_ref": str(row.get("source_ref") or ""),
    }


def create_open_shift(payload: dict, actor: str) -> dict:
    warehouse = _warehouse_record(str(payload["warehouse_id"]))
    if warehouse is None:
        raise service.WorkforceRuleError("Depo/çalışma konumu bulunamadı.")
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()
    if str(payload["date"]) < today:
        raise service.WorkforceRuleError("Geçmiş tarih için açık vardiya yayınlanamaz.")

    activity_keys = [str(key) for key in payload.get("activity_keys") or []]
    activity_rows = resolve_activity_bundle(activity_keys, str(payload["date"])) if activity_keys else []
    activities = [_activity_summary(row) for row in activity_rows]
    configured_location_type = _normal(warehouse.get("location_type") or warehouse.get("type"))
    for activity in activities:
        allowed_types = {_normal(value) for value in activity.get("location_types") or [] if _normal(value)}
        if configured_location_type and allowed_types and configured_location_type not in allowed_types:
            raise service.WorkforceRuleError(
                f"{activity['activity_key']} bu çalışma konumu tipi için onaylı değil."
            )

    minimum_break = service._minimum_break_minutes(payload["start"], payload["end"], payload["date"])
    break_minutes = max(int(payload.get("break_minutes", 60)), minimum_break)
    net_minutes = service._gross_shift_minutes(payload["start"], payload["end"]) - break_minutes
    if net_minutes > service._rule_value("dailyMax", payload["date"], 660):
        raise service.WorkforceRuleError("Açık vardiya günlük azami 11 saat net çalışma kuralını aşıyor.")

    normalized_activity_keys = tuple(sorted(activity_keys))
    with _LOCK:
        rows = _load_open_shifts()
        duplicate = next(
            (
                row for row in rows
                if row.get("status") == "OPEN"
                and str(row.get("warehouse_id")) == str(warehouse.get("id"))
                and row.get("date") == payload["date"]
                and row.get("start") == payload["start"]
                and row.get("end") == payload["end"]
                and _normal(row.get("role")) == _normal(payload.get("role"))
                and tuple(sorted(str(key) for key in row.get("activity_keys") or [])) == normalized_activity_keys
            ),
            None,
        )
        if duplicate:
            raise service.WorkforceRuleError("Aynı zaman, rol ve iş aktiviteleri için zaten açık vardiya bulunuyor.")
        now = datetime.now(ZoneInfo("UTC"))
        record = {
            "id": f"OPEN-{now.strftime('%Y%m%d%H%M%S%f')}",
            "warehouse_id": str(warehouse.get("id")),
            "warehouse": str(warehouse.get("name")),
            "date": str(payload["date"]),
            "start": str(payload["start"]),
            "end": str(payload["end"]),
            "break_minutes": break_minutes,
            "expected_minutes": net_minutes,
            "role": str(payload.get("role") or "Worker"),
            "activity_keys": activity_keys,
            "activities": activities,
            "capacity": int(payload.get("capacity", 1)),
            "claimed_count": 0,
            "claims": [],
            "status": "OPEN",
            "note": str(payload.get("note") or "")[:500],
            "created_at": now.isoformat(),
            "created_by": actor,
        }
        rows.append(record)
        _persist_collection(
            _OPEN_SHIFT_COLLECTION,
            rows,
            "WORKFORCE_OPEN_SHIFT_CREATED",
            actor,
            record_id=record["id"],
            warehouse_id=record["warehouse_id"],
            date=record["date"],
            capacity=record["capacity"],
            activity_keys=record["activity_keys"],
            activity_authority_refs=[item["authority_ref"] for item in activities],
        )
        return deepcopy(record)


def _availability_for(rows: list[dict], person_id: str, day: str) -> dict | None:
    return next(
        (row for row in rows if str(row.get("person_id")) == str(person_id) and row.get("date") == day),
        None,
    )


def evaluate_open_shift(offer: dict, person_id: str, availability_rows: list[dict] | None = None) -> dict:
    person = service.resolve_person_identity(str(person_id), "EMPLOYEE_ID")
    reasons: list[str] = []
    if person is None:
        return {
            "eligible": False,
            "score": 0,
            "preference_match": None,
            "reasons": ["EMPLOYEE_NOT_FOUND"],
            "missing_skill_keys": [],
            "missing_certification_keys": [],
            "missing_equipment_keys": [],
        }
    if not service.person_has_workforce_access(person, str(offer["date"])):
        reasons.append("EMPLOYMENT_INACTIVE")
    if not _warehouse_matches(person, offer):
        reasons.append("WAREHOUSE_SCOPE_MISMATCH")

    activities = list(offer.get("activities") or [])
    required_skills = {
        str(key)
        for activity in activities
        for key in activity.get("required_skill_keys") or []
        if str(key)
    }
    required_certifications = {
        str(key)
        for activity in activities
        for key in activity.get("required_certification_keys") or []
        if str(key)
    }
    required_equipment = {
        str(key)
        for activity in activities
        for key in activity.get("required_equipment_keys") or []
        if str(key)
    }
    missing_skills = sorted(required_skills - _capability_keys(person, "skill_keys"))
    missing_certifications = sorted(required_certifications - _capability_keys(person, "certification_keys"))
    missing_equipment = sorted(required_equipment - _capability_keys(person, "equipment_keys"))
    if missing_skills:
        reasons.append("SKILL_REQUIREMENT")
    if missing_certifications:
        reasons.append("CERTIFICATION_REQUIREMENT")
    if missing_equipment:
        reasons.append("EQUIPMENT_REQUIREMENT")

    availability_rows = _load_availability() if availability_rows is None else availability_rows
    availability = _availability_for(availability_rows, str(person_id), str(offer["date"]))
    if availability and not availability.get("available", True):
        reasons.append("UNAVAILABLE")
    if availability and availability.get("earliest_start") and availability.get("latest_end"):
        if not _window_contains(
            str(availability["earliest_start"]), str(availability["latest_end"]),
            str(offer["start"]), str(offer["end"]),
        ):
            reasons.append("OUTSIDE_AVAILABILITY_WINDOW")

    day_context = service._day_context(str(person_id), str(offer["date"]))
    if day_context.get("on_approved_leave"):
        reasons.append("APPROVED_LEAVE")

    existing_shifts = [
        row for row in service.list_shifts(str(person_id))
        if row.get("status") != "İptal"
    ]
    if any(row.get("date") == offer.get("date") for row in existing_shifts):
        reasons.append("ALREADY_SCHEDULED")

    candidate = {
        "date": offer["date"], "start": offer["start"], "end": offer["end"],
        "person_id": str(person_id), "status": "Atandı",
    }
    candidate_start, candidate_end = service._shift_interval(candidate)
    for existing in existing_shifts:
        existing_start, existing_end = service._shift_interval(existing)
        if candidate_start >= existing_end:
            gap = (candidate_start - existing_end).total_seconds() / 60
        elif existing_start >= candidate_end:
            gap = (existing_start - candidate_end).total_seconds() / 60
        else:
            gap = -1
        if gap < service._rule_value("betweenShifts", str(offer["date"]), 660):
            if "ALREADY_SCHEDULED" not in reasons:
                reasons.append("REST_RULE")
            break

    preference_match: bool | None = None
    score = 60
    if activities:
        score += 10
    if availability:
        score = max(score, 80)
        if availability.get("preferred_start") and availability.get("preferred_end"):
            preference_match = _window_contains(
                str(availability["preferred_start"]), str(availability["preferred_end"]),
                str(offer["start"]), str(offer["end"]),
            )
            score = 100 if preference_match else max(score, 75)
    if reasons:
        score = 0
    return {
        "eligible": not reasons,
        "score": score,
        "preference_match": preference_match,
        "availability_declared": availability is not None,
        "activity_match": not (missing_skills or missing_certifications or missing_equipment),
        "missing_skill_keys": missing_skills,
        "missing_certification_keys": missing_certifications,
        "missing_equipment_keys": missing_equipment,
        "reasons": reasons,
    }


def list_open_shifts_for_person(person_id: str) -> list[dict]:
    availability = _load_availability()
    rows = []
    for offer in _load_open_shifts():
        if offer.get("status") != "OPEN":
            continue
        if int(offer.get("claimed_count", 0)) >= int(offer.get("capacity", 1)):
            continue
        evaluation = evaluate_open_shift(offer, person_id, availability)
        if evaluation["eligible"]:
            rows.append({
                **{key: value for key, value in offer.items() if key != "claims"},
                "eligibility": evaluation,
                "remaining_capacity": int(offer.get("capacity", 1)) - int(offer.get("claimed_count", 0)),
            })
    return deepcopy(sorted(rows, key=lambda row: (row["date"], row["start"], -row["eligibility"]["score"])))


def claim_open_shift(open_shift_id: str, person_id: str, actor: str) -> dict:
    """Atomically turn one marketplace claim into a canonical Workforce shift.

    create_shift(persist=False) performs the same Employee Master, leave, daily
    maximum and between-shift checks as manager assignment. Its shift + scheduled
    notifications and the marketplace claim are then committed in one Workforce
    CAS transaction. On a stale write, process state is restored before returning
    a retryable conflict.
    """
    with _LOCK:
        if persistence.ENABLED:
            service._hydrate_snapshot(persistence.load_snapshot(service._snapshot_kinds()))
        open_rows = _load_open_shifts()
        offer = next((row for row in open_rows if row.get("id") == open_shift_id), None)
        if offer is None or offer.get("status") != "OPEN":
            raise service.WorkforceRuleError("Açık vardiya bulunamadı veya artık aktif değil.")
        if int(offer.get("claimed_count", 0)) >= int(offer.get("capacity", 1)):
            raise service.WorkforceRuleError("Açık vardiya kontenjanı doldu.")
        if any(str(claim.get("person_id")) == str(person_id) for claim in offer.get("claims", [])):
            raise service.WorkforceRuleError("Bu açık vardiya daha önce alındı.")

        availability_rows = _load_availability()
        eligibility = evaluate_open_shift(offer, person_id, availability_rows)
        if not eligibility["eligible"]:
            raise service.WorkforceRuleError(
                "Açık vardiya uygunluk, yetkinlik, sertifika, ekipman, izin, çalışma konumu veya dinlenme kurallarıyla eşleşmiyor."
            )
        person = service.resolve_person_identity(str(person_id), "EMPLOYEE_ID")
        if person is None:
            raise service.WorkforceRuleError("Employee Master kaydı bulunamadı.")

        before = service._snapshot_collections()
        try:
            shift = service.create_shift(
                {
                    "person_id": str(person_id),
                    "person_name": str(person.get("full_name") or person_id),
                    "warehouse_id": str(offer["warehouse_id"]),
                    "date": str(offer["date"]),
                    "start": str(offer["start"]),
                    "end": str(offer["end"]),
                    "break_minutes": int(offer.get("break_minutes", 60)),
                    "role": str(offer.get("role") or person.get("position") or "Worker"),
                    "activity_keys": list(offer.get("activity_keys") or []),
                    "activity_bundle": deepcopy(offer.get("activities") or []),
                    "open_shift_id": str(offer["id"]),
                },
                actor,
                persist=False,
            )
            claim = {
                "person_id": str(person_id),
                "shift_id": shift["id"],
                "claimed_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "eligibility_score": eligibility["score"],
                "preference_match": eligibility["preference_match"],
                "activity_keys": list(offer.get("activity_keys") or []),
            }
            offer.setdefault("claims", []).append(claim)
            offer["claimed_count"] = len(offer["claims"])
            if offer["claimed_count"] >= int(offer.get("capacity", 1)):
                offer["status"] = "FILLED"
                offer["filled_at"] = claim["claimed_at"]
            persistence.persist_snapshot_with_audit(
                {**service._snapshot_collections(), _OPEN_SHIFT_COLLECTION: open_rows},
                "WORKFORCE_OPEN_SHIFT_CLAIMED",
                actor,
                open_shift_id=open_shift_id,
                shift_id=shift["id"],
                person_id=str(person_id),
                warehouse_id=offer["warehouse_id"],
                date=offer["date"],
                eligibility_score=eligibility["score"],
                preference_match=eligibility["preference_match"],
                activity_keys=list(offer.get("activity_keys") or []),
                activity_authority_refs=[
                    item.get("authority_ref") for item in offer.get("activities") or []
                ],
            )
        except persistence.ConcurrentWriteError as error:
            service._hydrate_snapshot(before)
            if persistence.ENABLED:
                service._hydrate_snapshot(persistence.load_snapshot(service._snapshot_kinds()))
            raise service.WorkforceRuleError(
                "Açık vardiya başka bir işlem tarafından alındı veya Workforce verisi değişti; tekrar deneyin."
            ) from error
        except Exception:
            service._hydrate_snapshot(before)
            raise
        return {
            "open_shift": deepcopy({key: value for key, value in offer.items() if key != "claims"}),
            "shift": deepcopy(shift),
        }
