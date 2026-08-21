from datetime import date
from decimal import Decimal

import pytest

from app.payroll_engine import (
    IncomeTaxBracketInput,
    PayrollCalculationRequest,
    PayrollParameterApproval,
    PayrollParameterRegistry,
    PayrollParameterSetCreate,
    calculate_standard_4a_full_month,
)


def _payload():
    return PayrollParameterSetCreate(
        parameter_set_id="tr-4a-private-standard",
        version="2026.1",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        monthly_minimum_gross=33030.00,
        monthly_pek_floor=33030.00,
        monthly_pek_ceiling=297270.00,
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
            "https://www.sgk.gov.tr/Content/Post/2e0c9e1a-2cfe-4456-af10-49d3de0c58ba/Prime-Esas-Kazanc-Miktarlari-2026-01-14-10-35-39",
            "https://gib.gov.tr/vergi-konulari/1/11_ucret_geliri/11/73/327",
        ],
    )


def test_parameter_set_requires_human_approval_before_calculation(tmp_path):
    registry = PayrollParameterRegistry(tmp_path / "eay.db")
    draft = registry.create(_payload())
    with pytest.raises(ValueError, match="payroll_calculation_approved_parameters_required"):
        calculate_standard_4a_full_month(
            parameters=draft,
            request=PayrollCalculationRequest(as_of=date(2026, 8, 12), gross_pay=100000),
        )


def test_standard_4a_month_calculation_is_deterministic_and_minimum_wage_exempt(tmp_path):
    registry = PayrollParameterRegistry(tmp_path / "eay.db")
    draft = registry.create(_payload())
    approved = registry.approve(
        draft.id,
        PayrollParameterApproval(approved_by="payroll-reviewer", approval_reference="PAYROLL-2026-001"),
    )
    result = calculate_standard_4a_full_month(
        parameters=approved,
        request=PayrollCalculationRequest(as_of=date(2026, 8, 12), gross_pay=100000),
    )
    assert result.employee_sgk == Decimal("14000.00")
    assert result.employee_unemployment == Decimal("1000.00")
    assert result.income_tax_base == Decimal("85000.00")
    assert result.gross_income_tax == Decimal("12750.00")
    assert result.minimum_wage_income_tax_exemption == Decimal("4211.33")
    assert result.income_tax_payable == Decimal("8538.67")
    assert result.stamp_tax_payable == Decimal("508.30")
    assert result.net_pay == Decimal("75953.03")
    result.validate()


def test_parameter_period_and_partial_month_cases_fail_closed(tmp_path):
    registry = PayrollParameterRegistry(tmp_path / "eay.db")
    draft = registry.create(_payload())
    approved = registry.approve(
        draft.id,
        PayrollParameterApproval(approved_by="payroll-reviewer", approval_reference="PAYROLL-2026-001"),
    )
    with pytest.raises(ValueError, match="payroll_calculation_parameter_period_mismatch"):
        calculate_standard_4a_full_month(
            parameters=approved,
            request=PayrollCalculationRequest(as_of=date(2027, 1, 1), gross_pay=100000),
        )
    with pytest.raises(ValueError, match="partial_or_below_minimum"):
        calculate_standard_4a_full_month(
            parameters=approved,
            request=PayrollCalculationRequest(as_of=date(2026, 8, 12), gross_pay=20000),
        )


def test_parameter_registry_rejects_non_authoritative_sources():
    with pytest.raises(ValueError, match="enterprise_source_host_not_authoritative"):
        PayrollParameterSetCreate(
            parameter_set_id="bad",
            version="1",
            effective_from=date(2026, 1, 1),
            monthly_minimum_gross=33030,
            monthly_pek_floor=33030,
            monthly_pek_ceiling=297270,
            employee_sgk_rate=0.14,
            employee_unemployment_rate=0.01,
            stamp_tax_rate=0.00759,
            income_tax_brackets=[
                IncomeTaxBracketInput(upper_bound=190000, rate=0.15),
                IncomeTaxBracketInput(upper_bound=None, rate=0.40),
            ],
            source_urls=["https://example.com/payroll", "https://www.sgk.gov.tr/example"],
        )
