"""Outcome calibration for EAY Jarvis predictions.

A strong assistant should learn whether its stated confidence is calibrated.
This module records resolved forecasts and computes Brier/calibration metrics.
It is evaluation memory only: it does not self-modify production model weights,
source weights or policies without the existing evaluation/human approval path.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

OUTCOME_CALIBRATION_CONTRACT = "eay-outcome-calibration-v1"


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class PredictionRecord(BaseModel):
    prediction_id: str = Field(min_length=1, max_length=180)
    category: str = Field(min_length=1, max_length=180)
    predicted_probability: float = Field(ge=0.0, le=1.0)
    outcome_occurred: bool
    predicted_at: datetime
    resolved_at: datetime
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_temporal_truth(self) -> "PredictionRecord":
        if not _aware(self.predicted_at) or not _aware(self.resolved_at):
            raise ValueError("prediction_calibration_timezone_required")
        if self.resolved_at < self.predicted_at:
            raise ValueError("prediction_resolved_before_prediction")
        return self


class CalibrationBucket(BaseModel):
    lower_bound: float = Field(ge=0.0, le=1.0)
    upper_bound: float = Field(ge=0.0, le=1.0)
    count: int = Field(ge=0)
    mean_predicted_probability: float | None = None
    observed_rate: float | None = None
    absolute_gap: float | None = None


class CalibrationReport(BaseModel):
    contract: str = OUTCOME_CALIBRATION_CONTRACT
    sample_count: int = Field(ge=0)
    brier_score: float | None = None
    mean_predicted_probability: float | None = None
    observed_rate: float | None = None
    calibration_gap: float | None = None
    buckets: tuple[CalibrationBucket, ...] = ()
    self_modifying_weights_allowed: bool = False
    warnings: tuple[str, ...] = ()


def evaluate_calibration(
    records: list[PredictionRecord] | tuple[PredictionRecord, ...],
    *,
    bucket_count: int = 5,
) -> CalibrationReport:
    if bucket_count < 2 or bucket_count > 20:
        raise ValueError("calibration_bucket_count_out_of_range")
    if not records:
        return CalibrationReport(
            sample_count=0,
            warnings=("calibration_sample_missing",),
        )

    probabilities = [item.predicted_probability for item in records]
    outcomes = [1.0 if item.outcome_occurred else 0.0 for item in records]
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(records)
    mean_probability = sum(probabilities) / len(records)
    observed_rate = sum(outcomes) / len(records)

    buckets: list[CalibrationBucket] = []
    width = 1.0 / bucket_count
    for index in range(bucket_count):
        lower = index * width
        upper = 1.0 if index == bucket_count - 1 else (index + 1) * width
        selected = [
            (p, y)
            for p, y in zip(probabilities, outcomes)
            if p >= lower and (p <= upper if index == bucket_count - 1 else p < upper)
        ]
        if not selected:
            buckets.append(
                CalibrationBucket(
                    lower_bound=round(lower, 6),
                    upper_bound=round(upper, 6),
                    count=0,
                )
            )
            continue
        mean_p = sum(p for p, _ in selected) / len(selected)
        rate = sum(y for _, y in selected) / len(selected)
        buckets.append(
            CalibrationBucket(
                lower_bound=round(lower, 6),
                upper_bound=round(upper, 6),
                count=len(selected),
                mean_predicted_probability=round(mean_p, 6),
                observed_rate=round(rate, 6),
                absolute_gap=round(abs(mean_p - rate), 6),
            )
        )

    warnings: list[str] = []
    gap = abs(mean_probability - observed_rate)
    if len(records) < 30:
        warnings.append("calibration_sample_small")
    if gap > 0.15:
        warnings.append("confidence_calibration_drift")

    return CalibrationReport(
        sample_count=len(records),
        brier_score=round(brier, 6),
        mean_predicted_probability=round(mean_probability, 6),
        observed_rate=round(observed_rate, 6),
        calibration_gap=round(gap, 6),
        buckets=tuple(buckets),
        warnings=tuple(warnings),
    )
