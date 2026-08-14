from datetime import date

import pytest

from app.payroll_engine import (
    IncomeTaxBracketInput,
    PayrollParameterApproval,
    PayrollParameterRegistry,
    PayrollParameterSetCreate,
)
from app.payroll_period_engine import (
    PayrollEarningInput,
    PayrollPeriodCalculationRequest,
    calculate_full_month_with_wage_additions,
)


def _parameters(tmp_path):
    registry = PayrollParameterRegistry(tmp_path / "eay.db")
    draft = registry.create(PayrollParameterSetCreate(
        parameter_set_id="tr-2026",
        version="2026.1",
        effective_from=date(2026, 1, 1),
        monthly_minimum_gross=33030,
        monthly_pek_floor=33030,
        monthly_pek_ceiling=297270,
        employee_sgk_rate=0.14,
        employee_unemployment_rate=0.01,
        stamp_tax_rate=0.00759,
        income_tax_brackets=[
            IncomeTaxBracketInput(upper_bound=190000, rate=0.15),
            IncomeTaxBracketInput(upper_bound=400000, rate=0.20),
            IncomeTaxBracketInput(upper_bound=1500000, rate=0.27),
            IncomeTaxBracketInput(upper_bound=5300000, rate=0.35),
            IncomeTaxBracketInput(upper_bound=None, rate=0.40),
        ],
        source_urls=[
            "https://www.sgk.gov.tr/Content/Post/example",
            "https://www.gib.gov.tr/vergi-konulari/1_bireysel/11_ucret_geliri/11",
        ],
    ))
    return registry.approve(draft.id, PayrollParameterApproval(
        approved_by="payroll-reviewer",
        approval_reference="PAYROLL-2026-APPROVED",
    ))


def test_bonus_and_overtime_are_combined_into_one_monthly_wage_calculation(tmp_path):
    parameters = _parameters(tmp_path)
    result = calculate_full_month_with_wage_additions(
        parameters=parameters,
        request=PayrollPeriodCalculationRequest(
            as_of=date(2026, 8, 12),
            earnings=[
                PayrollEarningInput(kind="base_salary", amount=50000, source_reference="PAYSLIP-BASE"),
                PayrollEarningInput(kind="bonus", amount=5000, source_reference="BONUS-APPROVAL"),
                PayrollEarningInput(kind="overtime", amount=2500, source_reference="TIMESHEET-OT"),
            ],
        ),
    )
    assert result.base_salary == 50000
    assert result.wage_like_additions == 7500
    assert result.total_gross_pay == 57500
    assert result.payroll.gross_pay == 57500
    result.validate()


def test_monthly_exemption_is_not_reapplied_per_earning_component(tmp_path):
    parameters = _parameters(tmp_path)
    combined = calculate_full_month_with_wage_additions(
        parameters=parameters,
        request=PayrollPeriodCalculationRequest(
            as_of=date(2026, 8, 12),
            earnings=[
                PayrollEarningInput(kind="base_salary", amount=33030, source_reference="BASE"),
                PayrollEarningInput(kind="premium", amount=10000, source_reference="PREMIUM"),
            ],
        ),
    )
    assert combined.payroll.minimum_wage_income_tax_exemption > 0
    assert combined.payroll.minimum_wage_income_tax_exemption < combined.payroll.gross_income_tax


def test_partial_month_report_and_entry_exit_fail_closed_until_separate_contract_exists(tmp_path):
    _parameters(tmp_path)
    for kwargs in (
        {"paid_days": 28},
        {"report_days": 2},
        {"unpaid_leave_days": 1},
        {"employment_started_in_period": True},
        {"employment_ended_in_period": True},
    ):
        with pytest.raises(ValueError, match="payroll_period_partial_or_absence_contract_not_supported"):
            PayrollPeriodCalculationRequest(
                as_of=date(2026, 8, 12),
                earnings=[PayrollEarningInput(kind="base_salary", amount=50000, source_reference="BASE")],
                **kwargs,
            )


def test_exactly_one_base_salary_is_required():
    with pytest.raises(ValueError, match="payroll_period_exactly_one_base_salary_required"):
        PayrollPeriodCalculationRequest(
            as_of=date(2026, 8, 12),
            earnings=[PayrollEarningInput(kind="bonus", amount=5000, source_reference="BONUS")],
        )
