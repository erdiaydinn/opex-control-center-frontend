from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

DurationUnit = Literal["seconds", "minutes"]
RateScale = Literal["fraction", "percent"]


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DurationContract:
    metric: str
    source_unit: DurationUnit
    output_unit: Literal["seconds_per_order"] = "seconds_per_order"

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "kind": "duration",
                "metric": self.metric,
                "source_unit": self.source_unit,
                "output_unit": self.output_unit,
            }
        )

    def normalize(self, value: object) -> Decimal:
        number = _finite_non_negative_decimal(value, f"{self.metric}_duration")
        if self.source_unit == "seconds":
            return number
        if self.source_unit == "minutes":
            return number * Decimal("60")
        raise ValueError(f"unsupported_duration_unit:{self.metric}:{self.source_unit}")


@dataclass(frozen=True)
class RateContract:
    metric: str
    source_scale: RateScale

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "kind": "rate",
                "metric": self.metric,
                "source_scale": self.source_scale,
                "output_scale": "percent",
            }
        )

    def to_percent(self, value: object) -> Decimal:
        number = _finite_non_negative_decimal(value, f"{self.metric}_rate")
        if self.source_scale == "fraction":
            if number > 1:
                raise ValueError(f"rate_scale_violation:{self.metric}:fraction")
            return number * Decimal("100")
        if self.source_scale == "percent":
            if number > 100:
                raise ValueError(f"rate_scale_violation:{self.metric}:percent")
            return number
        raise ValueError(f"unsupported_rate_scale:{self.metric}:{self.source_scale}")


def _finite_non_negative_decimal(value: object, field: str) -> Decimal:
    if value is None:
        raise ValueError(f"kpi_unit_missing_value:{field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"kpi_unit_non_numeric:{field}") from exc
    if not number.is_finite():
        raise ValueError(f"kpi_unit_non_finite:{field}")
    if number < 0:
        raise ValueError(f"kpi_unit_negative:{field}")
    return number


def otp_from_late_prep(value: object, *, source_scale: RateScale) -> Decimal:
    """Calculate OTP 4.25 only when the late-prep source scale is explicitly pinned.

    The prior operational pattern of guessing scale from the value (<=1 => fraction)
    is intentionally forbidden because values such as 0.8 are valid in both scales.
    """

    late_prep_percent = RateContract("late_prep", source_scale).to_percent(value)
    otp = Decimal("100") - late_prep_percent
    if otp < 0 or otp > 100:
        raise ValueError("otp_out_of_bounds")
    return otp


def reject_heuristic_rate_scale(value: object) -> None:
    """Explicit guard against auto-detecting fraction-vs-percent from a numeric value."""

    _finite_non_negative_decimal(value, "rate")
    raise ValueError("rate_scale_must_be_explicitly_pinned")
