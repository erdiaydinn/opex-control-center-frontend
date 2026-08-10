from decimal import Decimal

import pytest

from app.kpi_nsfr_invariants import verify_nsfr_row


def test_nsfr_row_accepts_reviewed_precedence_decomposition():
    result = verify_nsfr_row(
        {
            "successful_orders": 1000,
            "pfr_orders": 7,
            "refund_orders": 11,
            "compensation_orders": 2,
            "nsfr_orders": 20,
        }
    )
    assert result.expected_nsfr_orders == Decimal("20")
    assert result.nsfr_rate_percent == Decimal("2.00")


def test_nsfr_row_blocks_double_count_or_precedence_drift():
    with pytest.raises(ValueError, match="nsfr_invariant_precedence_sum_mismatch"):
        verify_nsfr_row(
            {
                "successful_orders": 1000,
                "pfr_orders": 7,
                "refund_orders": 11,
                "compensation_orders": 2,
                "nsfr_orders": 21,
            }
        )


def test_nsfr_row_blocks_component_above_denominator():
    with pytest.raises(ValueError, match="nsfr_invariant_exceeds_denominator:pfr_orders"):
        verify_nsfr_row(
            {
                "successful_orders": 5,
                "pfr_orders": 6,
                "refund_orders": 0,
                "compensation_orders": 0,
                "nsfr_orders": 6,
            }
        )


@pytest.mark.parametrize("field", [
    "successful_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
])
def test_nsfr_row_blocks_null_required_fields(field):
    row = {
        "successful_orders": 100,
        "pfr_orders": 1,
        "refund_orders": 2,
        "compensation_orders": 0,
        "nsfr_orders": 3,
    }
    row[field] = None
    with pytest.raises(ValueError, match=f"nsfr_invariant_missing_field:{field}"):
        verify_nsfr_row(row)


def test_nsfr_row_blocks_negative_counts():
    with pytest.raises(ValueError, match="nsfr_invariant_negative:refund_orders"):
        verify_nsfr_row(
            {
                "successful_orders": 100,
                "pfr_orders": 1,
                "refund_orders": -1,
                "compensation_orders": 0,
                "nsfr_orders": 0,
            }
        )


def test_nsfr_row_zero_denominator_is_only_valid_with_zero_components():
    result = verify_nsfr_row(
        {
            "successful_orders": 0,
            "pfr_orders": 0,
            "refund_orders": 0,
            "compensation_orders": 0,
            "nsfr_orders": 0,
        }
    )
    assert result.nsfr_rate_percent == Decimal("0")
