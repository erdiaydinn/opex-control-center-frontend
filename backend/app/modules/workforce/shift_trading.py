"""Governed employee shift trading over the canonical Workforce schedule.

Employees can offer a transfer or propose a swap, but ownership changes only
through manager approval after a fresh eligibility revalidation. The module
never creates a parallel schedule authority.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from . import persistence, service
from .flexibility import (
    _availability_for,
    _capability_keys,
    _load_availability,
    _warehouse_matches,
    _window_contains,
)


_SHIFT_TRADE_COLLECTION = "workforce_shift_trades"
_LOCK = Lock()
_FINAL_STATES = {"APPROVED", "REJECTED", "CANCELLED"}
_POLICY = {
    "policy_ref": "SHIFT_TRADE_POLICY_V1",
    "manager_approval_required": True,
    "minimum_notice_minutes": 120,
    "allow_open_transfer": True,
    "allow_swap": True,
    "allow_partial_shift": False,
    "allow_cross_warehouse": False,
}


class ShiftTradeCreateRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)
    shift_id: str = Field(min_length=1, max_length=100)
    mode: str = Field(pattern=r"^(TRANSFER|SWAP)$")
    target_person_id: str | None = Field(default=None, min_length=1, max_length=50)
    target_shift_id: str | None = Field(default=None, min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.mode == "SWAP" and not self.target_shift_id:
            raise ValueError("SWAP requires target_shift_id")
        if self.mode == "TRANSFER" and self.target_shift_id:
            raise ValueError("TRANSFER cannot include target_shift_id")
        return self


class ShiftTradeAcceptRequest(BaseModel):
    person_id: str = Field(min_length=1, max_length=50)


class ShiftTradeDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=500)


def _hydrate_schedule() -> None:
    if persistence.ENABLED:
        service._hydrate_snapshot(persistence.load_snapshot(service._snapshot_kinds()))


def _load_trades() -> list[dict]:
    return persistence.load_collection(_SHIFT_TRADE_COLLECTION)


def _shift(shift_id: str) -> dict | None:
    return next(
        (row for row in service._SHIFTS if str(row.get("id")) == str(shift_id)),
        None,
    )


def _trade_uses_shift(trade: dict, shift_id: str) -> bool:
    candidate = str(shift_id)
    return candidate in {
        str(trade.get("shift_id") or ""),
        str(trade.get("target_shift_id") or ""),
    }


def _active_trade_for_shift(rows: list[dict], shift_id: str) -> dict | None:
    return next(
        (
            row
            for row in rows
            if row.get("status") not in _FINAL_STATES
            and _trade_uses_shift(row, shift_id)
        ),
        None,
    )


def _assert_shift_tradeable(shift: dict, owner_id: str) -> None:
    if str(shift.get("person_id")) != str(owner_id):
        raise service.WorkforceRuleError(
            "Yalnızca kendi vardiyanız için takas/transfer talebi oluşturabilirsiniz."
        )
    if str(shift.get("status")) != "Atandı":
        raise service.WorkforceRuleError(
            "Yalnızca henüz başlamamış atanmış vardiya takas/transfer edilebilir."
        )
    if any(
        str(row.get("shift_id")) == str(shift.get("id"))
        for row in service._ATTENDANCE
    ):
        raise service.WorkforceRuleError(
            "Check-in veya puantaj kaydı oluşmuş vardiya takas/transfer edilemez."
        )
    start, _ = service._shift_interval(shift)
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    notice = (start - now).total_seconds() / 60
    if notice < int(_POLICY["minimum_notice_minutes"]):
        raise service.WorkforceRuleError(
            "Vardiya takası için minimum bildirim süresi doldu."
        )


def _activities(shift: dict) -> list[dict]:
    return list(shift.get("activity_bundle") or shift.get("activities") or [])


def _evaluate_assignment(
    shift: dict,
    person_id: str,
    *,
    ignored_shift_ids: set[str] | None = None,
) -> dict:
    """Evaluate a proposed assignment without mutating the canonical schedule."""
    ignored = {str(value) for value in (ignored_shift_ids or set())}
    person = service.resolve_person_identity(str(person_id), "EMPLOYEE_ID")
    reasons: list[str] = []
    if person is None:
        return {"eligible": False, "reasons": ["EMPLOYEE_NOT_FOUND"]}

    if not service.person_has_workforce_access(person, str(shift["date"])):
        reasons.append("EMPLOYMENT_INACTIVE")
    if not _warehouse_matches(person, shift):
        reasons.append("WAREHOUSE_SCOPE_MISMATCH")

    activities = _activities(shift)
    requirements = {
        "SKILL_REQUIREMENT": (
            {
                str(key)
                for activity in activities
                for key in activity.get("required_skill_keys") or []
                if str(key)
            },
            "skill_keys",
        ),
        "CERTIFICATION_REQUIREMENT": (
            {
                str(key)
                for activity in activities
                for key in activity.get("required_certification_keys") or []
                if str(key)
            },
            "certification_keys",
        ),
        "EQUIPMENT_REQUIREMENT": (
            {
                str(key)
                for activity in activities
                for key in activity.get("required_equipment_keys") or []
                if str(key)
            },
            "equipment_keys",
        ),
    }
    for reason, (required, capability_key) in requirements.items():
        if required - _capability_keys(person, capability_key):
            reasons.append(reason)

    availability = _availability_for(
        _load_availability(),
        str(person_id),
        str(shift["date"]),
    )
    if availability and not availability.get("available", True):
        reasons.append("UNAVAILABLE")
    if (
        availability
        and availability.get("earliest_start")
        and availability.get("latest_end")
        and not _window_contains(
            str(availability["earliest_start"]),
            str(availability["latest_end"]),
            str(shift["start"]),
            str(shift["end"]),
        )
    ):
        reasons.append("OUTSIDE_AVAILABILITY_WINDOW")

    if service._day_context(str(person_id), str(shift["date"])).get(
        "on_approved_leave"
    ):
        reasons.append("APPROVED_LEAVE")

    existing = [
        row
        for row in service.list_shifts(str(person_id))
        if row.get("status") != "İptal"
        and str(row.get("id")) not in ignored
    ]
    if any(row.get("date") == shift.get("date") for row in existing):
        reasons.append("ALREADY_SCHEDULED")

    candidate = {
        "date": shift["date"],
        "start": shift["start"],
        "end": shift["end"],
        "person_id": str(person_id),
        "status": "Atandı",
    }
    candidate_start, candidate_end = service._shift_interval(candidate)
    required_rest = service._rule_value("betweenShifts", str(shift["date"]), 660)
    for current in existing:
        current_start, current_end = service._shift_interval(current)
        if candidate_start >= current_end:
            gap = (candidate_start - current_end).total_seconds() / 60
        elif current_start >= candidate_end:
            gap = (current_start - candidate_end).total_seconds() / 60
        else:
            gap = -1
        if gap < required_rest:
            if "ALREADY_SCHEDULED" not in reasons:
                reasons.append("REST_RULE")
            break

    expected_minutes = int(
        shift.get("expected_minutes")
        or service._gross_shift_minutes(str(shift["start"]), str(shift["end"]))
        - int(shift.get("break_minutes", 0))
    )
    if expected_minutes > service._rule_value("dailyMax", str(shift["date"]), 660):
        reasons.append("DAILY_MAX")

    preference_match = None
    if (
        availability
        and availability.get("preferred_start")
        and availability.get("preferred_end")
    ):
        preference_match = _window_contains(
            str(availability["preferred_start"]),
            str(availability["preferred_end"]),
            str(shift["start"]),
            str(shift["end"]),
        )
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "preference_match": preference_match,
    }


def _revalidate_trade(trade: dict) -> dict:
    source = _shift(str(trade["shift_id"]))
    if source is None:
        raise service.WorkforceRuleError("Kaynak vardiya bulunamadı.")
    _assert_shift_tradeable(source, str(trade["requester_person_id"]))

    target_person_id = str(trade.get("target_person_id") or "")
    if not target_person_id:
        raise service.WorkforceRuleError(
            "Takas/transfer için kabul eden personel bulunamadı."
        )

    if trade["mode"] == "TRANSFER":
        result = _evaluate_assignment(source, target_person_id)
        if not result["eligible"]:
            raise service.WorkforceRuleError(
                "Transfer, hedef personelin güncel uygunluk/çalışma/izin/"
                "yetkinlik/dinlenme kurallarıyla eşleşmiyor."
            )
        return {"source": source, "target": None, "target_evaluation": result}

    target = _shift(str(trade.get("target_shift_id") or ""))
    if target is None:
        raise service.WorkforceRuleError("Takas edilecek karşı vardiya bulunamadı.")
    _assert_shift_tradeable(target, target_person_id)
    if str(source.get("warehouse_id")) != str(target.get("warehouse_id")):
        raise service.WorkforceRuleError(
            "V1 vardiya takası farklı çalışma konumları arasında yapılamaz."
        )

    target_eval = _evaluate_assignment(
        source,
        target_person_id,
        ignored_shift_ids={str(target["id"])},
    )
    requester_eval = _evaluate_assignment(
        target,
        str(trade["requester_person_id"]),
        ignored_shift_ids={str(source["id"])},
    )
    if not target_eval["eligible"] or not requester_eval["eligible"]:
        raise service.WorkforceRuleError(
            "Takas, iki çalışanın güncel uygunluk/çalışma/izin/yetkinlik/"
            "dinlenme kurallarıyla eşleşmiyor."
        )
    return {
        "source": source,
        "target": target,
        "target_evaluation": target_eval,
        "requester_evaluation": requester_eval,
    }


def create_shift_trade(payload: dict, actor: str) -> dict:
    requester = str(payload["person_id"])
    with _LOCK:
        _hydrate_schedule()
        rows = _load_trades()
        source = _shift(str(payload["shift_id"]))
        if source is None:
            raise service.WorkforceRuleError("Vardiya bulunamadı.")
        _assert_shift_tradeable(source, requester)
        if _active_trade_for_shift(rows, str(source["id"])):
            raise service.WorkforceRuleError(
                "Bu vardiya için zaten açık bir takas/transfer talebi var."
            )

        mode = str(payload["mode"])
        target_person_id = str(payload.get("target_person_id") or "").strip() or None
        target_shift_id = str(payload.get("target_shift_id") or "").strip() or None
        if mode == "SWAP":
            if not target_shift_id:
                raise service.WorkforceRuleError("SWAP için karşı vardiya zorunludur.")
            target = _shift(target_shift_id)
            if target is None:
                raise service.WorkforceRuleError(
                    "Takas edilecek karşı vardiya bulunamadı."
                )
            target_person_id = str(target.get("person_id") or "")
            if not target_person_id or target_person_id == requester:
                raise service.WorkforceRuleError(
                    "Takas için farklı bir çalışan vardiyası gerekir."
                )
            _assert_shift_tradeable(target, target_person_id)
            if _active_trade_for_shift(rows, target_shift_id):
                raise service.WorkforceRuleError(
                    "Karşı vardiya başka bir açık takas/transfer talebinde kullanılıyor."
                )
            if str(source.get("warehouse_id")) != str(target.get("warehouse_id")):
                raise service.WorkforceRuleError(
                    "V1 vardiya takası farklı çalışma konumları arasında yapılamaz."
                )
        elif target_person_id == requester:
            raise service.WorkforceRuleError("Vardiya kendinize transfer edilemez.")

        if target_person_id and service.resolve_person_identity(
            target_person_id,
            "EMPLOYEE_ID",
        ) is None:
            raise service.WorkforceRuleError(
                "Hedef Employee Master kaydı bulunamadı."
            )

        now = datetime.now(ZoneInfo("UTC"))
        record = {
            "id": f"TRADE-{now.strftime('%Y%m%d%H%M%S%f')}",
            "mode": mode,
            "shift_id": str(source["id"]),
            "requester_person_id": requester,
            "target_person_id": target_person_id,
            "target_shift_id": target_shift_id,
            "warehouse_id": str(source.get("warehouse_id") or ""),
            "date": str(source.get("date") or ""),
            "status": (
                "PENDING_EMPLOYEE_ACCEPTANCE"
                if target_person_id
                else "OPEN_FOR_ACCEPTANCE"
            ),
            "policy": deepcopy(_POLICY),
            "note": str(payload.get("note") or "")[:500],
            "created_at": now.isoformat(),
            "created_by": actor,
        }
        rows.append(record)
        persistence.persist_snapshot_with_audit(
            {_SHIFT_TRADE_COLLECTION: rows},
            "WORKFORCE_SHIFT_TRADE_CREATED",
            actor,
            trade_id=record["id"],
            shift_id=record["shift_id"],
            target_shift_id=record["target_shift_id"],
            mode=record["mode"],
            requester_person_id=requester,
            target_person_id=target_person_id,
            warehouse_id=record["warehouse_id"],
            policy_ref=_POLICY["policy_ref"],
        )
        return deepcopy(record)


def list_shift_trades_for_person(person_id: str) -> list[dict]:
    """Return employee-visible trades using a fresh canonical schedule snapshot."""
    _hydrate_schedule()
    rows: list[dict] = []
    for trade in _load_trades():
        requester = str(trade.get("requester_person_id") or "")
        target = str(trade.get("target_person_id") or "")
        if person_id in {requester, target}:
            rows.append(trade)
            continue
        if (
            trade.get("status") == "OPEN_FOR_ACCEPTANCE"
            and trade.get("mode") == "TRANSFER"
        ):
            source = _shift(str(trade["shift_id"]))
            if source and _evaluate_assignment(source, str(person_id))["eligible"]:
                rows.append(trade)
    return deepcopy(
        sorted(rows, key=lambda row: (str(row.get("date")), str(row.get("created_at"))))
    )


def accept_shift_trade(trade_id: str, person_id: str, actor: str) -> dict:
    with _LOCK:
        _hydrate_schedule()
        rows = _load_trades()
        trade = next(
            (row for row in rows if str(row.get("id")) == str(trade_id)),
            None,
        )
        if trade is None or trade.get("status") not in {
            "OPEN_FOR_ACCEPTANCE",
            "PENDING_EMPLOYEE_ACCEPTANCE",
        }:
            raise service.WorkforceRuleError(
                "Takas/transfer talebi bulunamadı veya artık kabul edilemez."
            )
        if str(trade.get("requester_person_id")) == str(person_id):
            raise service.WorkforceRuleError(
                "Talebi oluşturan çalışan kendi talebini kabul edemez."
            )
        bound_target = str(trade.get("target_person_id") or "")
        if bound_target and bound_target != str(person_id):
            raise service.WorkforceRuleError(
                "Bu takas/transfer talebi başka bir çalışan için oluşturuldu."
            )
        if not bound_target:
            trade["target_person_id"] = str(person_id)

        _revalidate_trade(trade)
        now = datetime.now(ZoneInfo("UTC")).isoformat()
        trade.update(
            {
                "status": "PENDING_MANAGER_APPROVAL",
                "accepted_at": now,
                "accepted_by": actor,
            }
        )
        persistence.persist_snapshot_with_audit(
            {_SHIFT_TRADE_COLLECTION: rows},
            "WORKFORCE_SHIFT_TRADE_ACCEPTED",
            actor,
            trade_id=trade_id,
            shift_id=trade["shift_id"],
            target_shift_id=trade.get("target_shift_id"),
            requester_person_id=trade["requester_person_id"],
            target_person_id=trade["target_person_id"],
            manager_approval_required=True,
        )
        return deepcopy(trade)


def _person_name(person_id: str) -> str:
    person = service.resolve_person_identity(person_id, "EMPLOYEE_ID") or {}
    return str(person.get("full_name") or person_id)


def _replace_assignment(
    shift: dict,
    person_id: str,
    trade: dict,
    actor: str,
) -> None:
    previous_person_id = str(shift.get("person_id") or "")
    shift["person_id"] = str(person_id)
    shift["person_name"] = _person_name(str(person_id))
    shift["trade_id"] = str(trade["id"])
    shift.setdefault("assignment_history", []).append(
        {
            "event": "SHIFT_TRADE_REASSIGNMENT",
            "trade_id": str(trade["id"]),
            "mode": str(trade["mode"]),
            "from_person_id": previous_person_id,
            "to_person_id": str(person_id),
            "at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "actor": actor,
        }
    )


def _reschedule_shift_notifications(
    shifts: list[dict],
    actor: str,
    trade_id: str,
) -> list[str]:
    shift_ids = {str(shift["id"]) for shift in shifts}
    old_ids = [
        str(row["id"])
        for row in service._NOTIFICATIONS
        if str(row.get("shift_id")) in shift_ids
    ]
    service._NOTIFICATIONS[:] = [
        row
        for row in service._NOTIFICATIONS
        if str(row.get("shift_id")) not in shift_ids
    ]
    suffix = str(trade_id).replace("TRADE-", "")[-12:]
    for shift in shifts:
        new_rows = service._schedule_shift_notifications(shift, actor)
        created_ids = {str(row["id"]) for row in new_rows}
        for row in service._NOTIFICATIONS:
            if str(row.get("id")) in created_ids:
                row["id"] = f"{row['id']}-TR-{suffix}"
                row["type"] = f"{row.get('type', 'SHIFT')}_TRADE"
    return old_ids


def approve_shift_trade(trade_id: str, actor: str, note: str = "") -> dict:
    """Atomically apply an accepted trade to shifts, notifications and audit."""
    with _LOCK:
        _hydrate_schedule()
        rows = _load_trades()
        trade = next(
            (row for row in rows if str(row.get("id")) == str(trade_id)),
            None,
        )
        if trade is None or trade.get("status") != "PENDING_MANAGER_APPROVAL":
            raise service.WorkforceRuleError(
                "Yönetici onayı bekleyen takas/transfer talebi bulunamadı."
            )

        evaluation = _revalidate_trade(trade)
        before = service._snapshot_collections()
        try:
            source = evaluation["source"]
            requester = str(trade["requester_person_id"])
            target_person = str(trade["target_person_id"])
            affected: list[dict] = []
            if trade["mode"] == "TRANSFER":
                _replace_assignment(source, target_person, trade, actor)
                affected.append(source)
            else:
                target = evaluation["target"]
                _replace_assignment(source, target_person, trade, actor)
                _replace_assignment(target, requester, trade, actor)
                affected.extend([source, target])

            cancelled_notification_ids = _reschedule_shift_notifications(
                affected,
                actor,
                trade_id,
            )
            now = datetime.now(ZoneInfo("UTC")).isoformat()
            trade.update(
                {
                    "status": "APPROVED",
                    "approved_at": now,
                    "approved_by": actor,
                    "decision_note": str(note or "")[:500],
                    "target_evaluation": evaluation.get("target_evaluation"),
                    "requester_evaluation": evaluation.get("requester_evaluation"),
                }
            )
            persistence.persist_snapshot_with_audit(
                {**service._snapshot_collections(), _SHIFT_TRADE_COLLECTION: rows},
                "WORKFORCE_SHIFT_TRADE_APPROVED",
                actor,
                cancel_notification_ids=cancelled_notification_ids,
                trade_id=trade_id,
                mode=trade["mode"],
                shift_id=trade["shift_id"],
                target_shift_id=trade.get("target_shift_id"),
                requester_person_id=requester,
                target_person_id=target_person,
                warehouse_id=trade["warehouse_id"],
                policy_ref=_POLICY["policy_ref"],
                revalidated_at=now,
            )
        except persistence.ConcurrentWriteError as error:
            service._hydrate_snapshot(before)
            if persistence.ENABLED:
                _hydrate_schedule()
            raise service.WorkforceRuleError(
                "Takas onayı sırasında Workforce verisi değişti; işlem uygulanmadı, "
                "tekrar değerlendirin."
            ) from error
        except Exception:
            service._hydrate_snapshot(before)
            raise

        return {"trade": deepcopy(trade), "shifts": deepcopy(affected)}


def reject_shift_trade(trade_id: str, actor: str, note: str = "") -> dict:
    with _LOCK:
        rows = _load_trades()
        trade = next(
            (row for row in rows if str(row.get("id")) == str(trade_id)),
            None,
        )
        if trade is None or trade.get("status") in _FINAL_STATES:
            raise service.WorkforceRuleError("Aktif takas/transfer talebi bulunamadı.")
        trade.update(
            {
                "status": "REJECTED",
                "rejected_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "rejected_by": actor,
                "decision_note": str(note or "")[:500],
            }
        )
        persistence.persist_snapshot_with_audit(
            {_SHIFT_TRADE_COLLECTION: rows},
            "WORKFORCE_SHIFT_TRADE_REJECTED",
            actor,
            trade_id=trade_id,
            shift_id=trade["shift_id"],
            reason=trade["decision_note"],
        )
        return deepcopy(trade)


def cancel_shift_trade(trade_id: str, person_id: str, actor: str) -> dict:
    with _LOCK:
        rows = _load_trades()
        trade = next(
            (row for row in rows if str(row.get("id")) == str(trade_id)),
            None,
        )
        if trade is None or trade.get("status") in _FINAL_STATES:
            raise service.WorkforceRuleError("Aktif takas/transfer talebi bulunamadı.")
        if str(trade.get("requester_person_id")) != str(person_id):
            raise service.WorkforceRuleError(
                "Yalnızca talebi oluşturan çalışan iptal edebilir."
            )
        trade.update(
            {
                "status": "CANCELLED",
                "cancelled_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "cancelled_by": actor,
            }
        )
        persistence.persist_snapshot_with_audit(
            {_SHIFT_TRADE_COLLECTION: rows},
            "WORKFORCE_SHIFT_TRADE_CANCELLED",
            actor,
            trade_id=trade_id,
            shift_id=trade["shift_id"],
            requester_person_id=person_id,
        )
        return deepcopy(trade)
