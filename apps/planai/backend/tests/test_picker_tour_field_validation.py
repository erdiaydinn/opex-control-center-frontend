from __future__ import annotations

from picker_tour_field_validation import (
    FIELD_VALIDATION_VERSION,
    validate_picker_tour_against_field,
)


def store_dna() -> dict:
    return {
        "architecture": {
            "schema_version": 1,
            "coordinate_system": "cartesian_m",
            "source": "manual_survey",
            "source_ref": "survey://FIELD/1",
            "floor_width_m": 8.0,
            "floor_depth_m": 5.0,
            "elements": [
                {
                    "element_id": "ENTRY",
                    "element_type": "picker_entry",
                    "x_m": 0.25,
                    "y_m": 0.25,
                    "width_m": 0.5,
                    "depth_m": 0.5,
                },
                {
                    "element_id": "EXIT",
                    "element_type": "picker_exit",
                    "x_m": 7.0,
                    "y_m": 0.25,
                    "width_m": 0.5,
                    "depth_m": 0.5,
                },
            ],
        }
    }


def layout() -> dict:
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": 1,
                        "x_m": 2.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "side": "L",
                        "shelves": [{"shelf_width_cm": 100, "shelf_depth_cm": 50}],
                    },
                    {
                        "module_id": 2,
                        "x_m": 5.0,
                        "y_m": 1.0,
                        "width_m": 1.0,
                        "depth_m": 0.5,
                        "side": "R",
                        "shelves": [{"shelf_width_cm": 100, "shelf_depth_cm": 50}],
                    },
                ],
            }
        ]
    }


def result() -> dict:
    return {
        "planogram": {
            "aisles": [
                {
                    "aisle_id": "A",
                    "modules": [
                        {
                            "module_id": 1,
                            "shelves": [{"products": [{"sku": "SKU-A"}]}],
                        },
                        {
                            "module_id": 2,
                            "shelves": [{"products": [{"sku": "SKU-B"}]}],
                        },
                    ],
                }
            ]
        }
    }


def orders() -> list[dict]:
    return [
        {"order_id": "FIELD-O-1", "skus": ["SKU-A"]},
        {"order_id": "FIELD-O-2", "skus": ["SKU-B"]},
    ]


def test_no_field_observation_never_produces_acceptance() -> None:
    report = validate_picker_tour_against_field(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        observations=[],
    )

    assert report["validation_version"] == FIELD_VALIDATION_VERSION
    assert report["available"] is False
    assert report["acceptance_evaluated"] is False
    assert report["acceptance_passed"] is None
    assert report["reason"] == "field_observations_missing"
    assert report["production_evidence"] is False


def test_field_comparison_without_thresholds_is_evidence_only() -> None:
    report = validate_picker_tour_against_field(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        observations=[
            {"order_id": "FIELD-O-1", "distance_m": 8.0},
            {"order_id": "FIELD-O-2", "distance_m": 9.0},
        ],
    )

    assert report["available"] is True
    assert report["acceptance_evaluated"] is False
    assert report["acceptance_passed"] is None
    assert report["acceptance_state"] == "EVIDENCE_ONLY_NO_THRESHOLDS"
    assert report["metrics"]["matched_order_count"] == 2
    assert len(report["comparisons"]) == 2
    assert all("order_id" not in row for row in report["comparisons"])
    assert all(len(row["order_ref_hash"]) == 16 for row in report["comparisons"])
    assert len(report["validation_fingerprint"]) == 64


def test_explicit_thresholds_control_acceptance() -> None:
    baseline = validate_picker_tour_against_field(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        observations=[
            {"order_id": "FIELD-O-1", "distance_m": 8.0},
            {"order_id": "FIELD-O-2", "distance_m": 9.0},
        ],
    )
    mae = baseline["metrics"]["mae_m"]
    p95 = baseline["metrics"]["p95_absolute_error_m"]
    mape = baseline["metrics"]["mape_pct"]

    passing = validate_picker_tour_against_field(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        observations=[
            {"order_id": "FIELD-O-1", "distance_m": 8.0},
            {"order_id": "FIELD-O-2", "distance_m": 9.0},
        ],
        thresholds={
            "min_match_pct": 100,
            "max_mae_m": mae,
            "max_p95_absolute_error_m": p95,
            "max_mape_pct": mape,
        },
    )
    failing = validate_picker_tour_against_field(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        observations=[
            {"order_id": "FIELD-O-1", "distance_m": 8.0},
            {"order_id": "FIELD-O-2", "distance_m": 9.0},
        ],
        thresholds={"max_mae_m": max(0.0, mae - 0.001)},
    )

    assert passing["acceptance_evaluated"] is True
    assert passing["acceptance_passed"] is True
    assert passing["acceptance_state"] == "PASS"
    assert all(passing["threshold_results"].values())
    assert failing["acceptance_passed"] is False
    assert failing["acceptance_state"] == "FAIL"


def test_unknown_threshold_fails_closed() -> None:
    report = validate_picker_tour_against_field(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        observations=[{"order_id": "FIELD-O-1", "distance_m": 8.0}],
        thresholds={"magic_score": 1.0},
    )

    assert report["available"] is False
    assert report["reason"] == "unknown_acceptance_threshold"
    assert report["unknown_thresholds"] == ["magic_score"]
    assert report["acceptance_passed"] is None


def test_unmatched_observations_do_not_fake_coverage() -> None:
    report = validate_picker_tour_against_field(
        result=result(),
        layout=layout(),
        store_dna=store_dna(),
        orders=orders(),
        observations=[{"order_id": "OTHER", "distance_m": 10.0}],
    )

    assert report["available"] is False
    assert report["reason"] == "no_matching_field_observations"
    assert report["acceptance_evaluated"] is False
