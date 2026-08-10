import pytest

from app.kpi_result_validation import (
    KpiResultValidationError,
    ResultValidatingAdapter,
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
