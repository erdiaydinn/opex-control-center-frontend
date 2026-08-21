"""Read models for governed Workforce shift trading.

These views never mutate schedule authority. They expose only policy-safe swap
candidates to employees and warehouse-scoped approval rows to managers while
reusing the canonical eligibility rules in ``shift_trading``.
"""

from __future__ import annotations

from copy import deepcopy

from . import service, shift_trading
from .assignment_ranking import evaluate_assignment_ranking


_ACTIVE_MANAGER_STATES = {
    "PENDING_EMPLOYEE_ACCEPTANCE",
    "OPEN_FOR_ACCEPTANCE",
    "PENDING_MANAGER_APPROVAL",
}


def _shift_summary(shift: dict | None) -> dict | None:
    if not shift:
        return None
    return {
        "shift_id": str(shift.get("id") or ""),
        "date": str(shift.get("date") or ""),
        "start": str(shift.get("start") or ""),
        "end": str(shift.get("end") or ""),
        "role": str(shift.get("role") or ""),
        "warehouse_id": str(shift.get("warehouse_id") or ""),
        "warehouse": str(shift.get("warehouse") or shift.get("warehouse_name") or ""),
    }


def _assignment_ranking(
    shift: dict,
    person_id: str,
    preference_match: bool | None,
    ignored_shift_ids: set[str] | None = None,
) -> dict:
    ignored = {str(value) for value in (ignored_shift_ids or set())}
    person_shifts = [
        row
        for row in service.list_shifts(str(person_id))
        if row.get("status") != "İptal"
        and str(row.get("id") or "") not in ignored
    ]
    cohort_shifts = [
        row
        for row in service._SHIFTS
        if str(row.get("id") or "") not in ignored
    ]
    minimum_rest = service._rule_value("betweenShifts", str(shift["date"]), 660)
    return evaluate_assignment_ranking(
        offer=shift,
        person_id=str(person_id),
        person_shifts=person_shifts,
        cohort_shifts=cohort_shifts,
        preference_match=preference_match,
        minimum_rest_minutes=minimum_rest,
    ).as_record()


def _combined_swap_ranking(requester: dict, counterpart: dict) -> dict:
    fairness = min(
        int(requester["fairness_score"]),
        int(counterpart["fairness_score"]),
    )
    fatigue = max(
        int(requester["fatigue_risk_score"]),
        int(counterpart["fatigue_risk_score"]),
    )
    band_order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
    fatigue_band = max(
        (str(requester["fatigue_risk_band"]), str(counterpart["fatigue_risk_band"])),
        key=lambda value: band_order.get(value, 99),
    )
    return {
        "policy_ref": str(requester["policy_ref"]),
        "soft_only": True,
        "combined_fairness_score": fairness,
        "combined_fatigue_risk_score": fatigue,
        "combined_fatigue_risk_band": fatigue_band,
        "requester": requester,
        "counterpart": counterpart,
    }


def list_swap_candidates(person_id: str, source_shift_id: str) -> list[dict]:
    """Return only two-way eligible same-worksite swaps without employee IDs."""
    shift_trading._hydrate_schedule()
    rows = shift_trading._load_trades()
    source = shift_trading._shift(str(source_shift_id))
    if source is None:
        raise service.WorkforceRuleError("Vardiya bulunamadı.")
    shift_trading._assert_shift_tradeable(source, str(person_id))
    if shift_trading._active_trade_for_shift(rows, str(source["id"])):
        return []

    candidates: list[dict] = []
    for target in service._SHIFTS:
        target_id = str(target.get("id") or "")
        target_person_id = str(target.get("person_id") or "")
        if not target_id or not target_person_id or target_person_id == str(person_id):
            continue
        if str(target.get("status")) != "Atandı":
            continue
        if str(target.get("warehouse_id") or "") != str(source.get("warehouse_id") or ""):
            continue
        if shift_trading._active_trade_for_shift(rows, target_id):
            continue
        try:
            shift_trading._assert_shift_tradeable(target, target_person_id)
        except service.WorkforceRuleError:
            continue

        target_eval = shift_trading._evaluate_assignment(
            source,
            target_person_id,
            ignored_shift_ids={target_id},
        )
        requester_eval = shift_trading._evaluate_assignment(
            target,
            str(person_id),
            ignored_shift_ids={str(source["id"])},
        )
        if not target_eval["eligible"] or not requester_eval["eligible"]:
            continue

        requester_ranking = _assignment_ranking(
            target,
            str(person_id),
            requester_eval.get("preference_match"),
            ignored_shift_ids={str(source["id"])},
        )
        counterpart_ranking = _assignment_ranking(
            source,
            target_person_id,
            target_eval.get("preference_match"),
            ignored_shift_ids={target_id},
        )
        ranking = _combined_swap_ranking(requester_ranking, counterpart_ranking)
        person = service.resolve_person_identity(target_person_id, "EMPLOYEE_ID") or {}
        candidates.append(
            {
                **(_shift_summary(target) or {}),
                "counterpart_display_name": str(
                    person.get("full_name") or target.get("person_name") or "Çalışan"
                ),
                "requester_preference_match": requester_eval.get("preference_match"),
                "counterpart_preference_match": target_eval.get("preference_match"),
                "assignment_ranking": ranking,
                "policy_ref": shift_trading._POLICY["policy_ref"],
            }
        )

    return deepcopy(
        sorted(
            candidates,
            key=lambda row: (
                -int(row["assignment_ranking"]["combined_fairness_score"]),
                int(row["assignment_ranking"]["combined_fatigue_risk_score"]),
                str(row.get("date")),
                str(row.get("start")),
                str(row.get("counterpart_display_name")),
            ),
        )
    )


def list_manager_shift_trades(warehouse_id: str, active_only: bool = True) -> list[dict]:
    """Return enriched, warehouse-scoped rows for supervisor decisions."""
    shift_trading._hydrate_schedule()
    rows: list[dict] = []
    for trade in shift_trading._load_trades():
        if str(trade.get("warehouse_id") or "") != str(warehouse_id):
            continue
        if active_only and str(trade.get("status") or "") not in _ACTIVE_MANAGER_STATES:
            continue

        source = shift_trading._shift(str(trade.get("shift_id") or ""))
        target = shift_trading._shift(str(trade.get("target_shift_id") or ""))
        requester_id = str(trade.get("requester_person_id") or "")
        target_person_id = str(trade.get("target_person_id") or "")
        requester = service.resolve_person_identity(requester_id, "EMPLOYEE_ID") or {}
        target_person = (
            service.resolve_person_identity(target_person_id, "EMPLOYEE_ID") or {}
            if target_person_id
            else {}
        )
        rows.append(
            {
                **deepcopy(trade),
                "source_shift": _shift_summary(source),
                "target_shift": _shift_summary(target),
                "requester_display_name": str(requester.get("full_name") or requester_id),
                "target_display_name": str(
                    target_person.get("full_name") or target_person_id or "—"
                ),
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            str(row.get("date")),
            str(row.get("created_at")),
        ),
    )
