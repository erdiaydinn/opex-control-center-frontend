from datetime import datetime, timedelta, timezone

from app.outcome_calibration import PredictionRecord, evaluate_calibration

UTC = timezone.utc
BASE = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def _record(index: int, probability: float, outcome: bool) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=f"p-{index}",
        category="operations-context",
        predicted_probability=probability,
        outcome_occurred=outcome,
        predicted_at=BASE + timedelta(days=index),
        resolved_at=BASE + timedelta(days=index, hours=6),
        evidence_refs=(f"evidence://{index}",),
    )


def test_well_calibrated_small_sample_produces_brier_and_gap_metrics():
    report = evaluate_calibration(
        [
            _record(1, 0.8, True),
            _record(2, 0.7, True),
            _record(3, 0.3, False),
            _record(4, 0.2, False),
        ]
    )

    assert report.sample_count == 4
    assert report.brier_score is not None
    assert report.calibration_gap is not None
    assert report.self_modifying_weights_allowed is False
    assert "calibration_sample_small" in report.warnings


def test_overconfident_predictions_are_flagged_for_calibration_drift():
    records = [_record(index, 0.95, False) for index in range(10)]

    report = evaluate_calibration(records)

    assert report.observed_rate == 0.0
    assert report.mean_predicted_probability == 0.95
    assert report.calibration_gap == 0.95
    assert "confidence_calibration_drift" in report.warnings


def test_empty_history_does_not_invent_calibration_quality():
    report = evaluate_calibration([])

    assert report.sample_count == 0
    assert report.brier_score is None
    assert "calibration_sample_missing" in report.warnings
