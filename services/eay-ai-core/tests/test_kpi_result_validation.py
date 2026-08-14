import pytest

from app.kpi_result_validation import (
    KPI_RESULT_CONTRACTS,
    KpiResultValidationError,
    ResultValidatingAdapter,
    get_result_contract_fingerprint,
    validate_kpi_result,
)


VALID_ROW = {
    "successful_orders": 100,
    "pfr_orders": 3,
    "refund_orders": 2,
    "compensation_orders": 1,
    "nsfr_orders": 6,
}


class FakeAdapter:
    def __init__(self, rows):
        self.rows = rows

    def dry_run(self, sql, parameters, *, timeout_ms):
        return 10

    def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
        return self.rows


def test_nsfr_family_result_contract_accepts_precedence_consistent_rows():
    validate_kpi_result("nsfr", [VALID_ROW])
    validate_kpi_result("pfr", [VALID_ROW])
    validate_kpi_result("refund", [VALID_ROW])


def test_nsfr_family_result_contract_rejects_missing_invariant_fields():
    with pytest.raises(KpiResultValidationError, match="kpi_result_contract_missing_fields"):
        validate_kpi_result("nsfr", [{"successful_orders": 100, "nsfr_orders": 6}])


def test_nsfr_family_result_contract_rejects_precedence_sum_drift():
    bad = dict(VALID_ROW)
    bad["nsfr_orders"] = 7
    with pytest.raises(KpiResultValidationError, match="precedence_sum_mismatch"):
        validate_kpi_result("nsfr", [bad])


def test_result_validating_adapter_blocks_bad_rows_before_return():
    bad = dict(VALID_ROW)
    bad["refund_orders"] = 200
    adapter = ResultValidatingAdapter(FakeAdapter([bad]), metric="refund")
    with pytest.raises(KpiResultValidationError, match="exceeds_denominator"):
        adapter.execute("SELECT 1", {}, timeout_ms=1000, maximum_bytes_billed=1000)


def test_unregistered_metric_has_no_result_contract_side_effect():
    validate_kpi_result("orders", [{"orders": 5}])


def test_result_contract_fingerprint_is_deterministic_and_metric_bound():
    nsfr = get_result_contract_fingerprint("nsfr")
    refund = get_result_contract_fingerprint("refund")
    assert nsfr is not None and len(nsfr) == 64
    assert nsfr == KPI_RESULT_CONTRACTS["nsfr"].fingerprint
    assert nsfr != refund
    assert KPI_RESULT_CONTRACTS["nsfr"].version == "2"
    assert get_result_contract_fingerprint("orders") is None


def test_nsfr_family_reconciles_returned_rates_exactly_at_six_decimals():
    row = dict(VALID_ROW)
    row.update(
        pfr_rate_percent="3.000000",
        refund_rate_percent="2.000000",
        compensation_rate_percent="1.000000",
        nsfr_rate_percent="6.000000",
    )
    validate_kpi_result("nsfr", [row])


def test_nsfr_family_rejects_rate_denominator_drift_without_tolerance():
    row = dict(VALID_ROW)
    row["nsfr_rate_percent"] = "6.000001"
    with pytest.raises(KpiResultValidationError, match="rate_reconciliation_mismatch"):
        validate_kpi_result("nsfr", [row])


def test_nsfr_family_rejects_excess_rate_precision():
    row = dict(VALID_ROW)
    row["refund_rate_percent"] = "2.0000001"
    with pytest.raises(KpiResultValidationError, match="rate_precision_exceeded"):
        validate_kpi_result("refund", [row])


def test_nsfr_family_reconciles_repeating_decimal_with_half_up_precision():
    row = {
        "successful_orders": 3,
        "pfr_orders": 1,
        "refund_orders": 0,
        "compensation_orders": 0,
        "nsfr_orders": 1,
        "pfr_rate_percent": "33.333333",
        "nsfr_rate_percent": "33.333333",
    }
    validate_kpi_result("pfr", [row])


def test_zero_denominator_requires_zero_returned_rates():
    row = {
        "successful_orders": 0,
        "pfr_orders": 0,
        "refund_orders": 0,
        "compensation_orders": 0,
        "nsfr_orders": 0,
        "nsfr_rate_percent": "0.000000",
    }
    validate_kpi_result("nsfr", [row])

    bad = dict(row)
    bad["nsfr_rate_percent"] = "0.000001"
    with pytest.raises(KpiResultValidationError, match="rate_reconciliation_mismatch"):
        validate_kpi_result("nsfr", [bad])
