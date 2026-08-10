from decimal import Decimal

import pytest

from app.kpi_unit_contracts import (
    DurationContract,
    RateContract,
    otp_from_late_prep,
    reject_heuristic_rate_scale,
)


def test_duration_minutes_are_normalized_to_seconds():
    contract = DurationContract(metric="prep", source_unit="minutes")
    assert contract.normalize("2.5") == Decimal("150.0")


def test_duration_seconds_remain_seconds():
    contract = DurationContract(metric="picking", source_unit="seconds")
    assert contract.normalize(95) == Decimal("95")


@pytest.mark.parametrize("value", [None, -1, "nan", "inf", "not-a-number"])
def test_duration_contract_rejects_invalid_values(value):
    contract = DurationContract(metric="prep", source_unit="seconds")
    with pytest.raises(ValueError):
        contract.normalize(value)


def test_fraction_rate_is_explicitly_scaled_to_percent():
    assert RateContract("late_prep", "fraction").to_percent("0.0425") == Decimal("4.2500")


def test_percent_rate_is_not_rescaled():
    assert RateContract("late_prep", "percent").to_percent("4.25") == Decimal("4.25")


def test_fraction_contract_rejects_values_above_one():
    with pytest.raises(ValueError, match="rate_scale_violation:late_prep:fraction"):
        RateContract("late_prep", "fraction").to_percent("1.01")


def test_percent_contract_rejects_values_above_100():
    with pytest.raises(ValueError, match="rate_scale_violation:late_prep:percent"):
        RateContract("late_prep", "percent").to_percent("100.01")


def test_otp_425_requires_explicit_fraction_scale():
    assert otp_from_late_prep("0.0425", source_scale="fraction") == Decimal("95.7500")


def test_otp_425_requires_explicit_percent_scale():
    assert otp_from_late_prep("4.25", source_scale="percent") == Decimal("95.75")


def test_same_numeric_value_has_different_meaning_by_reviewed_scale():
    fraction = otp_from_late_prep("0.8", source_scale="fraction")
    percent = otp_from_late_prep("0.8", source_scale="percent")
    assert fraction == Decimal("20.0")
    assert percent == Decimal("99.2")
    assert fraction != percent


def test_heuristic_scale_detection_is_forbidden_even_for_small_value():
    with pytest.raises(ValueError, match="rate_scale_must_be_explicitly_pinned"):
        reject_heuristic_rate_scale("0.8")
