"""Intraday Workforce Command Center read model.

This module composes governed demand/capacity/DPI evidence with the canonical
schedule, attendance, breaks and shift-trade state. It is intentionally read-only:
it cannot apply optimizer/replan output or mutate the canonical schedule.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from . import persistence, service, shift_trade_views
from .command_center_repository import get_command_center_authority


ISTANBUL = ZoneInfo("Europe/Istanbul")
ZERO = Decimal("0")
TECHNICAL_DRIFT_TOLERANCE_MH = Decimal("0.01")
SCHEDULE_DRIFT_COMPARISON_BASIS = "GROSS_SCHEDULED_MAN_HOURS"


class CommandCenterError(RuntimeError):
    pass


def _decimal_text(value: object) -> str:
    decimal = Decimal(str(value or 0))
    if decimal == ZERO:
        return "0"
    text = format(decimal.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _iso(value: object | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _local(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=ISTANBUL)
    return value.astimezone(ISTANBUL)


def _iso_day(value: object) -> str:
    text = str(value or "")
    if "." in text:
        parts = text.split(".")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return text[:10]


def _canonical_location(value: object) -> str | None:
    from .router import _canonical_warehouse_id

    return _canonical_warehouse_id(value)


def _location_matches(value: object, location_id: str) -> bool:
    return _canonical_location(value) == location_id


def _shift_interval_local(shift: dict) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(f"{shift['date']}T{shift['start']}:00").replace(tzinfo=ISTANBUL)
    end = datetime.fromisoformat(f"{shift['date']}T{shift['end']}:00").replace(tzinfo=ISTANBUL)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _overlap_minutes(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> int:
    start = max(first_start, second_start)
    end = min(first_end, second_end)
    return max(0, int((end - start).total_seconds() // 60))


def _shift_expected_minutes(shift: dict) -> int:
    if shift.get("expected_minutes") is not None:
        return max(0, int(shift.get("expected_minutes") or 0))
    gross = service._gross_shift_minutes(str(shift["start"]), str(shift["end"]))
    return max(0, gross - int(shift.get("break_minutes") or 0))


def _scheduled_gross_overlap_minutes(shift: dict, start: datetime, end: datetime) -> Decimal:
    """Project canonical schedule on the same gross-hours basis as capacity authority.

    EffectiveCapacitySnapshot.scheduled_man_hours is the pre-deduction schedule
    quantity; absence, break and unavailable hours are represented separately.
    Drift detection must therefore compare gross scheduled overlap with gross
    scheduled authority instead of proportionally subtracting shift breaks here.
    """
    shift_start, shift_end = _shift_interval_local(shift)
    return Decimal(_overlap_minutes(shift_start, shift_end, start, end))


def _attendance_interval(row: dict) -> tuple[datetime | None, datetime | None]:
    day = _iso_day(row.get("date"))
    check_in = row.get("check_in") or row.get("checkIn")
    check_out = row.get("check_out") or row.get("checkOut")
    if not day or not check_in or str(check_in) == "—":
        return None, None
    start = datetime.fromisoformat(f"{day}T{check_in}:00").replace(tzinfo=ISTANBUL)
    end = None
    if check_out and str(check_out) != "—":
        end = datetime.fromisoformat(f"{day}T{check_out}:00").replace(tzinfo=ISTANBUL)
        if end <= start:
            end += timedelta(days=1)
    return start, end


def _attendance_location(row: dict, shifts_by_id: dict[str, dict]) -> str | None:
    shift = shifts_by_id.get(str(row.get("shift_id") or row.get("shiftId") or ""))
    if shift:
        return _canonical_location(shift.get("warehouse_id") or shift.get("warehouse"))
    return _canonical_location(row.get("warehouse_id") or row.get("warehouse"))


def _action(
    code: str,
    priority: int,
    severity: str,
    *,
    evidence: list[str],
    recommended_action_code: str,
    requires_human_approval: bool = True,
    count: int | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "code": code,
        "priority": priority,
        "severity": severity,
        "title_code": f"{code}_TITLE",
        "detail_code": f"{code}_DETAIL",
        "recommended_action_code": recommended_action_code,
        "requires_human_approval": requires_human_approval,
        "evidence_refs": [value for value in evidence if value],
    }
    if count is not None:
        row["count"] = count
    return row


def _daily_rule_risks(shifts: list[dict], day: str) -> tuple[int, int]:
    active = [row for row in shifts if row.get("status") != "İptal"]
    daily_limit = int(service._rule_value("dailyMax", day, 660))
    minimum_rest = int(service._rule_value("betweenShifts", day, 660))
    by_person: dict[str, list[dict]] = {}
    for row in active:
        by_person.setdefault(str(row.get("person_id") or ""), []).append(row)

    daily_limit_count = 0
    rest_violation_people: set[str] = set()
    for person_id, rows in by_person.items():
        day_minutes = sum(_shift_expected_minutes(row) for row in rows if str(row.get("date")) == day)
        if day_minutes > daily_limit:
            daily_limit_count += 1
        ordered = sorted(rows, key=lambda row: _shift_interval_local(row)[0])
        for previous, current in zip(ordered, ordered[1:], strict=False):
            previous_end = _shift_interval_local(previous)[1]
            current_start = _shift_interval_local(current)[0]
            gap = int((current_start - previous_end).total_seconds() // 60)
            if gap < minimum_rest:
                rest_violation_people.add(person_id)
                break
    return daily_limit_count, len(rest_violation_people)


def build_command_center(
    location_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    authority = get_command_center_authority(location_id)
    if authority is None:
        raise CommandCenterError(
            "Bu çalışma noktası için fingerprint-tutarlı demand/capacity/DPI intervali bulunamadı."
        )

    if persistence.ENABLED:
        service._hydrate_snapshot(persistence.load_snapshot(service._snapshot_kinds()))

    interval_start = _local(authority["interval_start"])
    interval_end = interval_start + timedelta(minutes=int(authority["interval_minutes"]))
    now = _local(now or datetime.now(ISTANBUL))
    if interval_start <= now < interval_end:
        interval_relation = "CURRENT"
    elif now >= interval_end:
        interval_relation = "PAST"
    else:
        interval_relation = "FUTURE"

    all_shifts = [
        row for row in service.list_shifts()
        if _location_matches(row.get("warehouse_id") or row.get("warehouse"), location_id)
        and row.get("status") != "İptal"
    ]
    interval_shifts = [
        row for row in all_shifts
        if _overlap_minutes(*_shift_interval_local(row), interval_start, interval_end) > 0
    ]
    shifts_by_id = {str(row.get("id")): row for row in all_shifts}
    scheduled_people = {str(row.get("person_id")) for row in interval_shifts if row.get("person_id")}
    operational_scheduled_gross_minutes = sum(
        (
            _scheduled_gross_overlap_minutes(row, interval_start, interval_end)
            for row in interval_shifts
        ),
        ZERO,
    )

    attendance_rows = [
        row for row in service.list_attendance()
        if _attendance_location(row, shifts_by_id) == location_id
    ]
    interval_attendance: list[tuple[dict, datetime, datetime | None]] = []
    for row in attendance_rows:
        start, end = _attendance_interval(row)
        if start is None:
            continue
        effective_end = end or max(now, start)
        if _overlap_minutes(start, effective_end, interval_start, interval_end) > 0:
            interval_attendance.append((row, start, end))

    attendance_started_people = {
        str(row.get("person_id") or row.get("personId"))
        for row, _, _ in interval_attendance
        if row.get("person_id") or row.get("personId")
    }
    actual_present_people: set[str] = set()
    if interval_relation == "CURRENT":
        for row, start, end in interval_attendance:
            if start <= now and (end is None or now < end):
                person_id = str(row.get("person_id") or row.get("personId") or "")
                if person_id:
                    actual_present_people.add(person_id)

    cutoff = min(max(now, interval_start), interval_end)
    no_show_count = 0
    if interval_relation != "FUTURE":
        for shift in interval_shifts:
            shift_start, _ = _shift_interval_local(shift)
            if shift_start >= cutoff:
                continue
            person_id = str(shift.get("person_id") or "")
            matching = any(
                str(row.get("shift_id") or row.get("shiftId") or "") == str(shift.get("id"))
                or (
                    not (row.get("shift_id") or row.get("shiftId"))
                    and str(row.get("person_id") or row.get("personId") or "") == person_id
                    and _iso_day(row.get("date")) == str(shift.get("date"))
                )
                for row, _, _ in interval_attendance
            )
            if not matching:
                no_show_count += 1

    breaks = service.list_breaks()
    interval_shift_ids = {str(row.get("id")) for row in interval_shifts}
    break_events = [
        row for row in breaks
        if str(row.get("shift_id")) in interval_shift_ids
        and interval_start <= _local(datetime.fromisoformat(str(row["started_at"]))) < interval_end
    ]
    active_breaks = 0
    if interval_relation == "CURRENT":
        active_breaks = sum(
            1 for row in break_events
            if not row.get("finished_at") and _local(datetime.fromisoformat(str(row["started_at"]))) <= now
        )

    interval_day = interval_start.date().isoformat()
    daily_limit_count, rest_violation_count = _daily_rule_risks(all_shifts, interval_day)

    trades = shift_trade_views.list_manager_shift_trades(location_id, active_only=True)
    pending_trade_count = sum(
        1 for row in trades if str(row.get("status")) == "PENDING_MANAGER_APPROVAL"
    )

    dpi = authority["dpi"]
    demand = authority["demand"]
    capacity = authority["capacity"]
    replan = authority.get("replan")
    action_queue: list[dict[str, object]] = []
    common_evidence = [
        str(dpi["snapshot_fingerprint"]),
        str(dpi["demand_snapshot_fingerprint"]),
        str(dpi["capacity_snapshot_fingerprint"]),
    ]

    if interval_relation != "CURRENT":
        action_queue.append(_action(
            "AUTHORITY_INTERVAL_NOT_CURRENT", 10, "blocker",
            evidence=common_evidence,
            recommended_action_code="REFRESH_GOVERNED_INTERVAL",
            requires_human_approval=False,
        ))
    if dpi["manpower_shortage"]:
        action_queue.append(_action(
            "CAPACITY_SHORTAGE", 20, "high", evidence=common_evidence,
            recommended_action_code="REVIEW_STAFFING_OPTIONS",
        ))
    if Decimal(str(capacity["skill_deficit_man_hours"])) > ZERO:
        action_queue.append(_action(
            "SKILL_DEFICIT", 30, "high", evidence=[str(dpi["capacity_snapshot_fingerprint"])],
            recommended_action_code="REVIEW_SKILL_COVERAGE",
        ))
    if no_show_count:
        action_queue.append(_action(
            "NO_SHOW", 40, "high", evidence=[str(dpi["capacity_snapshot_fingerprint"])],
            recommended_action_code="REVIEW_NO_SHOWS", count=no_show_count,
        ))
    if daily_limit_count:
        action_queue.append(_action(
            "DAILY_LIMIT_BREACH", 45, "high", evidence=["WORKFORCE_RULE:dailyMax"],
            recommended_action_code="REVIEW_SCHEDULE_COMPLIANCE", count=daily_limit_count,
        ))
    if rest_violation_count:
        action_queue.append(_action(
            "REST_RULE_BREACH", 46, "high", evidence=["WORKFORCE_RULE:betweenShifts"],
            recommended_action_code="REVIEW_SCHEDULE_COMPLIANCE", count=rest_violation_count,
        ))
    if dpi["kpi_bad"]:
        action_queue.append(_action(
            "KPI_PRESSURE", 50, "medium", evidence=[str(dpi["snapshot_fingerprint"])],
            recommended_action_code="REVIEW_EXECUTION_ROOT_CAUSE",
            count=len(dpi["bad_kpi_keys"]),
        ))
    if replan and replan["replan_required"]:
        action_queue.append(_action(
            "PENDING_REPLAN", 60, "medium",
            evidence=[str(replan["scenario_fingerprint"]), str(replan["proposal_fingerprint"])],
            recommended_action_code="REVIEW_REPLAN_SCENARIO",
            requires_human_approval=bool(replan["human_approval_required"]),
        ))
    if pending_trade_count:
        action_queue.append(_action(
            "PENDING_SHIFT_TRADE", 70, "info", evidence=["SHIFT_TRADE_POLICY_V1"],
            recommended_action_code="REVIEW_SHIFT_TRADES", count=pending_trade_count,
        ))

    authority_scheduled = Decimal(str(capacity["scheduled_man_hours"]))
    operational_scheduled = operational_scheduled_gross_minutes / Decimal("60")
    drift = operational_scheduled - authority_scheduled
    if interval_relation == "CURRENT" and abs(drift) > TECHNICAL_DRIFT_TOLERANCE_MH:
        action_queue.append(_action(
            "SCHEDULE_SNAPSHOT_DRIFT", 15, "blocker",
            evidence=[
                str(dpi["capacity_snapshot_fingerprint"]),
                f"SCHEDULE_DRIFT_BASIS:{SCHEDULE_DRIFT_COMPARISON_BASIS}",
            ],
            recommended_action_code="REFRESH_CAPACITY_SNAPSHOT",
            requires_human_approval=False,
        ))

    demand_contributors = sorted(
        list(demand.get("contributors") or []),
        key=lambda row: Decimal(str(row.get("man_hours") or 0)),
        reverse=True,
    )

    return {
        "location_id": location_id,
        "interval": {
            "start": interval_start.isoformat(),
            "end": interval_end.isoformat(),
            "minutes": int(authority["interval_minutes"]),
            "relation": interval_relation,
            "is_current": interval_relation == "CURRENT",
            "observed_at": now.isoformat(),
        },
        "authority": {
            "dpi_fingerprint": str(dpi["snapshot_fingerprint"]),
            "demand_fingerprint": str(dpi["demand_snapshot_fingerprint"]),
            "capacity_fingerprint": str(dpi["capacity_snapshot_fingerprint"]),
            "demand_model_version": str(demand["model_version"]),
            "capacity_model_version": str(capacity["model_version"]),
            "dpi_model_version": str(dpi["model_version"]),
            "labor_standard_refs": list(demand.get("labor_standard_refs") or []),
        },
        "demand": {
            "required_man_hours": _decimal_text(dpi["required_man_hours"]),
            "required_people": _decimal_text(demand["required_people"]),
            "contributors": demand_contributors,
        },
        "capacity": {
            "authority_scheduled_man_hours": _decimal_text(capacity["scheduled_man_hours"]),
            "operational_scheduled_man_hours": _decimal_text(operational_scheduled),
            "operational_scheduled_gross_man_hours": _decimal_text(operational_scheduled),
            "schedule_snapshot_drift_man_hours": _decimal_text(drift),
            "schedule_snapshot_comparison_basis": SCHEDULE_DRIFT_COMPARISON_BASIS,
            "absence_man_hours": _decimal_text(capacity["absence_man_hours"]),
            "break_man_hours": _decimal_text(capacity["break_man_hours"]),
            "unavailable_man_hours": _decimal_text(capacity["unavailable_man_hours"]),
            "effective_man_hours": _decimal_text(capacity["effective_man_hours"]),
            "scheduled_fte": _decimal_text(capacity["scheduled_fte"]),
            "skill_deficit_man_hours": _decimal_text(capacity["skill_deficit_man_hours"]),
            "skill_deficits": dict(capacity.get("skill_deficits") or {}),
        },
        "pressure": {
            "demand_pressure_index": _decimal_text(dpi["demand_pressure_index"]),
            "capacity_gap_man_hours": _decimal_text(dpi["capacity_gap_man_hours"]),
            "capacity_sufficient": bool(dpi["capacity_sufficient"]),
            "manpower_shortage": bool(dpi["manpower_shortage"]),
            "root_cause": str(dpi["root_cause"]),
            "kpi_bad": bool(dpi["kpi_bad"]),
            "bad_kpi_keys": list(dpi["bad_kpi_keys"]),
            "kpi_observations": list(dpi["kpi_observations"]),
            "explanation": list(dpi["explanation"]),
            "staffing_review_required": bool(dpi["staffing_review_required"]),
        },
        "operations": {
            "scheduled_people": len(scheduled_people),
            "attendance_started_people": len(attendance_started_people),
            "actual_present_people": (
                len(actual_present_people) if interval_relation == "CURRENT" else None
            ),
            "no_show_count": no_show_count,
            "active_break_count": active_breaks,
            "break_event_count": len(break_events),
            "daily_limit_breach_count": daily_limit_count,
            "rest_rule_breach_count": rest_violation_count,
            "pending_shift_trade_count": pending_trade_count,
        },
        "replan": None if replan is None else {
            "scenario_fingerprint": str(replan["scenario_fingerprint"]),
            "proposal_fingerprint": str(replan["proposal_fingerprint"]),
            "scenario_gap_man_hours": _decimal_text(replan["scenario_gap_man_hours"]),
            "scenario_dpi": _decimal_text(replan["scenario_dpi"]),
            "dpi_delta": _decimal_text(replan["dpi_delta"]),
            "predicted_kpi_deltas": dict(replan["predicted_kpi_deltas"]),
            "estimated_scenario_cost_minor_units": int(
                replan["estimated_scenario_cost_minor_units"]
            ),
            "cost_delta_minor_units": int(replan["cost_delta_minor_units"]),
            "recommendation": str(replan["recommendation"]),
            "replan_required": bool(replan["replan_required"]),
            "automatic_apply_permitted": bool(replan["automatic_apply_permitted"]),
            "human_approval_required": bool(replan["human_approval_required"]),
        },
        "action_queue": sorted(action_queue, key=lambda row: (int(row["priority"]), str(row["code"]))),
        "automatic_schedule_apply_permitted": False,
        "automatic_extra_people_permitted": bool(dpi["automatic_extra_people_permitted"]),
        "human_in_loop": True,
        "truth_boundary": {
            "live_label_permitted": interval_relation == "CURRENT",
            "schedule_mutation_performed": False,
            "predictions_are_observations": False,
            "repository_or_synthetic_evidence_is_field_proof": False,
        },
    }
