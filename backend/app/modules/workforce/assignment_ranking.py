"""Deterministic soft ranking for eligible Workforce assignments.

This module never grants eligibility and never overrides a hard scheduling rule.
It ranks already-eligible options using explainable employee preference, relative
recent workload, rest buffer and recovery-streak signals. Thresholds here are
ranking bands, not legal or contractual working-time limits.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from statistics import median


POLICY_REF = "WORKFORCE_ASSIGNMENT_RANKING_V1"


@dataclass(frozen=True, slots=True)
class AssignmentRanking:
    policy_ref: str
    soft_only: bool
    fairness_score: int
    fatigue_risk_score: int
    fatigue_risk_band: str
    preference_score: int
    workload_balance_score: int
    rest_buffer_score: int
    recovery_score: int
    recent_minutes: int
    cohort_median_recent_minutes: int
    consecutive_workdays_before: int
    minimum_rest_minutes: int
    nearest_rest_gap_minutes: int | None
    reason_codes: tuple[str, ...]

    def as_record(self) -> dict:
        record = asdict(self)
        record["reason_codes"] = list(self.reason_codes)
        return record


def _day(value: object) -> date:
    return date.fromisoformat(str(value))


def _clock(value: object) -> tuple[int, int]:
    hour, minute = (int(part) for part in str(value).split(":")[:2])
    return hour, minute


def _interval(row: dict) -> tuple[datetime, datetime]:
    shift_day = _day(row["date"])
    start_hour, start_minute = _clock(row["start"])
    end_hour, end_minute = _clock(row["end"])
    start = datetime.combine(shift_day, datetime.min.time()).replace(
        hour=start_hour,
        minute=start_minute,
    )
    end = datetime.combine(shift_day, datetime.min.time()).replace(
        hour=end_hour,
        minute=end_minute,
    )
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _minutes(row: dict) -> int:
    expected = row.get("expected_minutes")
    if expected not in (None, ""):
        return max(0, int(expected))
    start, end = _interval(row)
    gross = int((end - start).total_seconds() // 60)
    return max(0, gross - int(row.get("break_minutes") or 0))


def _active(rows: list[dict]) -> list[dict]:
    return [row for row in rows if str(row.get("status") or "") != "İptal"]


def _recent_minutes(rows: list[dict], person_id: str, target_day: date) -> int:
    window_start = target_day - timedelta(days=7)
    return sum(
        _minutes(row)
        for row in _active(rows)
        if str(row.get("person_id") or "") == str(person_id)
        and window_start <= _day(row["date"]) < target_day
    )


def _cohort_median(rows: list[dict], target_day: date) -> int:
    people = {
        str(row.get("person_id") or "")
        for row in _active(rows)
        if row.get("person_id")
    }
    samples = [_recent_minutes(rows, person_id, target_day) for person_id in people]
    positive_samples = [value for value in samples if value > 0]
    return int(round(median(positive_samples))) if positive_samples else 0


def _consecutive_days_before(rows: list[dict], person_id: str, target_day: date) -> int:
    worked = {
        _day(row["date"])
        for row in _active(rows)
        if str(row.get("person_id") or "") == str(person_id)
        and _day(row["date"]) < target_day
    }
    streak = 0
    cursor = target_day - timedelta(days=1)
    while cursor in worked:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _nearest_rest_gap(
    rows: list[dict],
    person_id: str,
    offer: dict,
) -> int | None:
    candidate_start, candidate_end = _interval(offer)
    gaps: list[int] = []
    for row in _active(rows):
        if str(row.get("person_id") or "") != str(person_id):
            continue
        existing_start, existing_end = _interval(row)
        if candidate_start >= existing_end:
            gaps.append(int((candidate_start - existing_end).total_seconds() // 60))
        elif existing_start >= candidate_end:
            gaps.append(int((existing_start - candidate_end).total_seconds() // 60))
        else:
            gaps.append(0)
    return min(gaps) if gaps else None


def _preference_component(preference_match: bool | None) -> tuple[int, str]:
    if preference_match is True:
        return 25, "PREFERENCE_MATCH"
    if preference_match is False:
        return 5, "PREFERENCE_MISMATCH"
    return 15, "PREFERENCE_UNDECLARED"


def _workload_component(recent: int, cohort_median: int) -> tuple[int, int, str]:
    if cohort_median <= 0:
        return 20, 0, "WORKLOAD_COHORT_BASELINE_UNAVAILABLE"
    ratio = recent / cohort_median
    if ratio <= 0.75:
        return 25, 0, "WORKLOAD_BELOW_COHORT"
    if ratio <= 1.0:
        return 22, 5, "WORKLOAD_BALANCED"
    if ratio <= 1.25:
        return 16, 15, "WORKLOAD_ABOVE_COHORT"
    if ratio <= 1.5:
        return 10, 28, "WORKLOAD_HIGH_RELATIVE_TO_COHORT"
    return 4, 40, "WORKLOAD_VERY_HIGH_RELATIVE_TO_COHORT"


def _rest_component(gap: int | None, minimum: int) -> tuple[int, int, str]:
    if gap is None:
        return 25, 0, "REST_BUFFER_NO_ADJACENT_SHIFT"
    minimum = max(1, int(minimum))
    ratio = gap / minimum
    if ratio >= 2.0:
        return 25, 0, "REST_BUFFER_STRONG"
    if ratio >= 1.5:
        return 22, 5, "REST_BUFFER_GOOD"
    if ratio >= 1.25:
        return 18, 12, "REST_BUFFER_MODERATE"
    if ratio >= 1.0:
        return 12, 25, "REST_BUFFER_TIGHT"
    return 0, 50, "REST_BELOW_HARD_MINIMUM"


def _recovery_component(streak: int) -> tuple[int, int, str]:
    if streak <= 2:
        return 25, streak * 3, "RECOVERY_STREAK_LOW"
    if streak == 3:
        return 21, 12, "RECOVERY_STREAK_MODERATE"
    if streak == 4:
        return 16, 18, "RECOVERY_STREAK_ELEVATED"
    if streak == 5:
        return 10, 26, "RECOVERY_STREAK_HIGH"
    return 5, min(35, 26 + (streak - 5) * 5), "RECOVERY_STREAK_VERY_HIGH"


def _fatigue_band(score: int) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 55:
        return "HIGH"
    if score >= 30:
        return "MODERATE"
    return "LOW"


def evaluate_assignment_ranking(
    *,
    offer: dict,
    person_id: str,
    person_shifts: list[dict],
    cohort_shifts: list[dict],
    preference_match: bool | None,
    minimum_rest_minutes: int,
) -> AssignmentRanking:
    """Rank one already-eligible assignment without changing authority."""
    target_day = _day(offer["date"])
    recent = _recent_minutes(person_shifts, person_id, target_day)
    cohort_median = _cohort_median(cohort_shifts, target_day)
    streak = _consecutive_days_before(person_shifts, person_id, target_day)
    nearest_gap = _nearest_rest_gap(person_shifts, person_id, offer)

    preference_score, preference_reason = _preference_component(preference_match)
    workload_score, workload_risk, workload_reason = _workload_component(
        recent,
        cohort_median,
    )
    rest_score, rest_risk, rest_reason = _rest_component(
        nearest_gap,
        minimum_rest_minutes,
    )
    recovery_score, recovery_risk, recovery_reason = _recovery_component(streak)

    fairness_score = max(
        0,
        min(100, preference_score + workload_score + rest_score + recovery_score),
    )
    fatigue_risk = max(0, min(100, workload_risk + rest_risk + recovery_risk))
    return AssignmentRanking(
        policy_ref=POLICY_REF,
        soft_only=True,
        fairness_score=fairness_score,
        fatigue_risk_score=fatigue_risk,
        fatigue_risk_band=_fatigue_band(fatigue_risk),
        preference_score=preference_score,
        workload_balance_score=workload_score,
        rest_buffer_score=rest_score,
        recovery_score=recovery_score,
        recent_minutes=recent,
        cohort_median_recent_minutes=cohort_median,
        consecutive_workdays_before=streak,
        minimum_rest_minutes=int(minimum_rest_minutes),
        nearest_rest_gap_minutes=nearest_gap,
        reason_codes=(
            preference_reason,
            workload_reason,
            rest_reason,
            recovery_reason,
        ),
    )
