from __future__ import annotations

import pytest

from app.modules.planogram.execution import PlanogramExecutionError
from app.modules.planogram.shelf_scan import evaluate_shelf_scan


def plan() -> dict:
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": "1",
                        "shelves": [
                            {
                                "shelf_no": "1",
                                "products": [
                                    {"sku": "MILK", "facing_count": 3},
                                    {"sku": "YOGURT", "facing_count": 2},
                                ],
                            },
                            {
                                "shelf_no": "2",
                                "products": [
                                    {"sku": "JUICE", "facing_count": 2},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }


def shelf_evidence(
    shelf_no: str,
    *,
    complete: bool = True,
    quality: float = 0.95,
    occlusion: float = 5.0,
) -> dict:
    return {
        "aisle_id": "A",
        "module_id": "1",
        "shelf_no": shelf_no,
        "source_ref": f"image://A-1-{shelf_no}",
        "coverage_complete": complete,
        "image_quality_score": quality,
        "occlusion_pct": occlusion,
    }


def observation(
    sku: str,
    shelf_no: str,
    *,
    facing: int,
    confidence: float = 0.99,
) -> dict:
    return {
        "sku": sku,
        "aisle_id": "A",
        "module_id": "1",
        "shelf_no": shelf_no,
        "facing_count": facing,
        "confidence": confidence,
        "source_ref": f"detector://{sku}-{shelf_no}",
    }


def test_low_confidence_detection_never_becomes_compliance_or_deviation() -> None:
    result = evaluate_shelf_scan(
        plan_payload=plan(),
        shelves=[shelf_evidence("1", complete=False)],
        observations=[observation("MILK", "1", facing=3, confidence=0.61)],
    )

    assert result["compliant_count"] == 0
    assert result["deviation_count"] == 0
    assert result["review_required_count"] >= 1
    assert any(
        row.get("reason") == "detection_confidence_below_threshold"
        for row in result["review_required"]
    )
    assert result["auto_accept_allowed"] is False
    assert result["field_truth"] is False


def test_incomplete_scan_never_invents_missing_sku() -> None:
    result = evaluate_shelf_scan(
        plan_payload=plan(),
        shelves=[shelf_evidence("1", complete=False)],
        observations=[observation("MILK", "1", facing=3)],
    )

    assert result["compliant_count"] == 1
    assert result["missing_expected_sku_count"] == 0
    assert not any(
        row.get("deviation_code") == "expected_sku_not_detected"
        for row in result["deviations"]
    )
    assert any(
        row.get("reason") == "shelf_absence_not_provable"
        for row in result["review_required"]
    )


def test_low_quality_or_occluded_scan_never_invents_missing_sku() -> None:
    for shelf in (
        shelf_evidence("1", quality=0.4),
        shelf_evidence("1", occlusion=70.0),
    ):
        result = evaluate_shelf_scan(
            plan_payload=plan(),
            shelves=[shelf],
            observations=[observation("MILK", "1", facing=3)],
        )

        assert result["missing_expected_sku_count"] == 0
        assert any(
            row.get("reason") == "shelf_absence_not_provable"
            for row in result["review_required"]
        )


def test_complete_high_quality_scan_can_mark_expected_sku_missing() -> None:
    result = evaluate_shelf_scan(
        plan_payload=plan(),
        shelves=[shelf_evidence("1")],
        observations=[observation("MILK", "1", facing=3)],
    )

    assert result["compliant_count"] == 1
    assert result["missing_expected_sku_count"] == 1
    missing = next(
        row
        for row in result["deviations"]
        if row.get("deviation_code") == "expected_sku_not_detected"
    )
    assert missing["sku"] == "YOGURT"
    assert missing["absence_evidence"]["coverage_complete"] is True
    assert result["production_evidence"] is False


def test_facing_mismatch_and_misplacement_are_distinct() -> None:
    result = evaluate_shelf_scan(
        plan_payload=plan(),
        shelves=[shelf_evidence("1"), shelf_evidence("2")],
        observations=[
            observation("MILK", "1", facing=1),
            observation("JUICE", "1", facing=2),
            observation("YOGURT", "1", facing=2),
        ],
    )

    codes = {row.get("deviation_code") for row in result["deviations"]}
    assert "facing_mismatch" in codes
    assert "sku_misplaced" in codes
    misplaced = next(
        row
        for row in result["deviations"]
        if row.get("deviation_code") == "sku_misplaced"
    )
    assert misplaced["sku"] == "JUICE"
    assert misplaced["expected_locations"] == [
        {"aisle_id": "A", "module_id": "1", "shelf_no": "2"}
    ]


def test_unknown_high_confidence_sku_is_deviation_not_silent_extra() -> None:
    result = evaluate_shelf_scan(
        plan_payload=plan(),
        shelves=[shelf_evidence("1")],
        observations=[
            observation("MILK", "1", facing=3),
            observation("YOGURT", "1", facing=2),
            observation("UNKNOWN", "1", facing=1),
        ],
    )

    unknown = next(
        row
        for row in result["deviations"]
        if row.get("sku") == "UNKNOWN"
    )
    assert unknown["deviation_code"] == "sku_not_in_approved_plan"


def test_duplicate_high_confidence_detection_blocks_automatic_interpretation() -> None:
    result = evaluate_shelf_scan(
        plan_payload=plan(),
        shelves=[shelf_evidence("1")],
        observations=[
            observation("MILK", "1", facing=3),
            observation("MILK", "1", facing=3),
            observation("YOGURT", "1", facing=2),
        ],
    )

    assert result["available"] is False
    assert "duplicate_high_confidence_observation" in result["blockers"]
    assert result["candidate_ready_for_human_review"] is False
    assert result["auto_correct_allowed"] is False


def test_invalid_thresholds_and_observations_fail_closed() -> None:
    with pytest.raises(PlanogramExecutionError):
        evaluate_shelf_scan(
            plan_payload=plan(),
            shelves=[shelf_evidence("1")],
            observations=[],
            min_detection_confidence=0.2,
        )

    result = evaluate_shelf_scan(
        plan_payload=plan(),
        shelves=[shelf_evidence("1")],
        observations=[
            {
                "sku": "MILK",
                "aisle_id": "A",
                "module_id": "1",
                "shelf_no": "1",
                "facing_count": 0,
                "confidence": 0.99,
            }
        ],
    )
    assert result["available"] is False
    assert "invalid_scan_observation" in result["blockers"]
    assert result["invalid_observations"] == ["index:0"]
