from datetime import datetime, timedelta, timezone

import pytest

from app.modules.workforce.policy_model import PlannedShift, WorkforceSchedulingPolicy, validate_planned_shift

NOW = datetime(2026, 8, 16, 6, 0, tzinfo=timezone.utc)


def policy():
    return WorkforceSchedulingPolicy(
        tenant_id="tenant-a",
        policy_id="tr-darkstore-standard",
        version=3,
        allowed_shift_minutes=(360, 450, 480),
        max_daily_work_minutes=480,
        min_rest_minutes=660,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        country="TR",
    )


def shift(employee="e1", start=NOW, minutes=480):
    return PlannedShift(employee_id=employee, starts_at=start, ends_at=start + timedelta(minutes=minutes))


def test_company_policy_accepts_only_configured_shift_lengths():
    assert validate_planned_shift(policy(), shift(minutes=480)).allowed is True
    result = validate_planned_shift(policy(), shift(minutes=420))
    assert result.allowed is False
    assert "shift_duration_not_allowed" in result.codes


def test_minimum_rest_is_policy_driven_not_eay_global_constant():
    previous = shift(start=NOW - timedelta(hours=16), minutes=480)
    current = shift(start=NOW)
    result = validate_planned_shift(policy(), current, previous_shift=previous)
    assert result.allowed is False
    assert "minimum_rest_not_met" in result.codes


def test_invalid_policy_fails_closed():
    with pytest.raises(ValueError, match="cannot exceed"):
        WorkforceSchedulingPolicy(
            tenant_id="tenant-a",
            policy_id="bad",
            version=1,
            allowed_shift_minutes=(600,),
            max_daily_work_minutes=480,
            min_rest_minutes=0,
            effective_from=NOW,
        )
