from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class WorkforceSchedulingPolicy:
    """Customer/company scheduling constraints with no EAY-global numeric assumptions."""

    tenant_id: str
    policy_id: str
    version: int
    allowed_shift_minutes: tuple[int, ...]
    max_daily_work_minutes: int
    min_rest_minutes: int
    effective_from: datetime
    effective_to: datetime | None = None
    country: str | None = None
    region: str | None = None
    business_unit: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.policy_id:
            raise ValueError("tenant_id and policy_id are required")
        if self.version < 1:
            raise ValueError("policy version must be positive")
        if not self.allowed_shift_minutes or any(value <= 0 for value in self.allowed_shift_minutes):
            raise ValueError("allowed_shift_minutes must contain positive durations")
        if self.max_daily_work_minutes <= 0 or self.min_rest_minutes < 0:
            raise ValueError("daily work/rest constraints are invalid")
        if max(self.allowed_shift_minutes) > self.max_daily_work_minutes:
            raise ValueError("allowed shift duration cannot exceed max daily work")
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")


@dataclass(frozen=True, slots=True)
class PlannedShift:
    employee_id: str
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if not self.employee_id:
            raise ValueError("employee_id is required")
        if self.ends_at <= self.starts_at:
            raise ValueError("shift end must be after start")

    @property
    def duration_minutes(self) -> int:
        return int((self.ends_at - self.starts_at).total_seconds() // 60)


@dataclass(frozen=True, slots=True)
class PolicyCheckResult:
    allowed: bool
    codes: tuple[str, ...]


def validate_planned_shift(
    policy: WorkforceSchedulingPolicy,
    shift: PlannedShift,
    *,
    previous_shift: PlannedShift | None = None,
) -> PolicyCheckResult:
    codes: list[str] = []
    if shift.duration_minutes not in policy.allowed_shift_minutes:
        codes.append("shift_duration_not_allowed")
    if shift.duration_minutes > policy.max_daily_work_minutes:
        codes.append("daily_work_limit_exceeded")
    if previous_shift is not None:
        if previous_shift.employee_id != shift.employee_id:
            raise ValueError("previous shift belongs to a different employee")
        rest_minutes = int((shift.starts_at - previous_shift.ends_at).total_seconds() // 60)
        if rest_minutes < policy.min_rest_minutes:
            codes.append("minimum_rest_not_met")
    return PolicyCheckResult(allowed=not codes, codes=tuple(codes))
