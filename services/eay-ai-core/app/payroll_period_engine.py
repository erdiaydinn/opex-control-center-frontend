from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .payroll_engine import (
    PayrollCalculationRequest,
    PayrollCalculationResult,
    PayrollParameterSet,
    calculate_standard_4a_full_month,
)


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


EarningKind = Literal["base_salary", "bonus", "premium", "overtime", "commission", "other_wage"]


class PayrollEarningInput(BaseModel):
    kind: EarningKind
    amount: float = Field(ge=0)
    source_reference: str = Field(min_length=3, max_length=300)


class PayrollPeriodCalculationRequest(BaseModel):
    as_of: date
    earnings: list[PayrollEarningInput] = Field(min_length=1)
    cumulative_tax_base_before: float = Field(default=0, ge=0)
    cumulative_minimum_wage_tax_base_before: float = Field(default=0, ge=0)
    paid_days: int = Field(default=30, ge=0, le=31)
    report_days: int = Field(default=0, ge=0, le=31)
    unpaid_leave_days: int = Field(default=0, ge=0, le=31)
    employment_started_in_period: bool = False
    employment_ended_in_period: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        base_items = [item for item in self.earnings if item.kind == "base_salary"]
        if len(base_items) != 1:
            raise ValueError("payroll_period_exactly_one_base_salary_required")
        if (
            self.paid_days != 30
            or self.report_days
            or self.unpaid_leave_days
            or self.employment_started_in_period
            or self.employment_ended_in_period
        ):
            # Partial-period and absence cases require their own reviewed day/PEK contracts.
            # Do not silently prorate by 30 or infer SGK missing-day treatment.
            raise ValueError("payroll_period_partial_or_absence_contract_not_supported")
        return self


@dataclass(frozen=True)
class PayrollPeriodCalculationResult:
    as_of: str
    deterministic_calculation_id: str
    parameter_set_fingerprint: str
    earnings_fingerprint: str
    base_salary: Decimal
    wage_like_additions: Decimal
    total_gross_pay: Decimal
    payroll: PayrollCalculationResult
    fingerprint: str

    def payload(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "deterministic_calculation_id": self.deterministic_calculation_id,
            "parameter_set_fingerprint": self.parameter_set_fingerprint,
            "earnings_fingerprint": self.earnings_fingerprint,
            "base_salary": str(self.base_salary),
            "wage_like_additions": str(self.wage_like_additions),
            "total_gross_pay": str(self.total_gross_pay),
            "payroll_fingerprint": self.payroll.fingerprint,
        }

    def validate(self) -> None:
        self.payroll.validate()
        if _sha256(self.payload()) != self.fingerprint:
            raise ValueError("payroll_period_calculation_fingerprint_drift")


def calculate_full_month_with_wage_additions(
    *,
    parameters: PayrollParameterSet,
    request: PayrollPeriodCalculationRequest,
) -> PayrollPeriodCalculationResult:
    """Compose ordinary wage-like earnings into one governed monthly payroll calculation.

    GİB guidance states that salary plus wage-character payments such as bonus, premium
    and overtime are considered together for cumulative wage taxation and the monthly
    minimum-wage exemption is applied once to the combined wage payment. This function
    deliberately does not derive overtime hours/rates or absence-day pay; callers must
    provide already-governed gross earning amounts and a source reference for each item.
    """
    request.validate_scope()
    parameters.validate()

    canonical_earnings = tuple(
        sorted(
            (
                item.kind,
                str(_money(Decimal(str(item.amount)))),
                item.source_reference,
            )
            for item in request.earnings
        )
    )
    earnings_fingerprint = _sha256(canonical_earnings)
    base_salary = sum(
        (Decimal(str(item.amount)) for item in request.earnings if item.kind == "base_salary"),
        Decimal("0"),
    )
    additions = sum(
        (Decimal(str(item.amount)) for item in request.earnings if item.kind != "base_salary"),
        Decimal("0"),
    )
    total = _money(base_salary + additions)
    if total <= 0:
        raise ValueError("payroll_period_total_gross_must_be_positive")

    payroll = calculate_standard_4a_full_month(
        parameters=parameters,
        request=PayrollCalculationRequest(
            as_of=request.as_of,
            gross_pay=float(total),
            cumulative_tax_base_before=request.cumulative_tax_base_before,
            cumulative_minimum_wage_tax_base_before=request.cumulative_minimum_wage_tax_base_before,
        ),
    )
    values = {
        "as_of": request.as_of.isoformat(),
        "deterministic_calculation_id": "tr-payroll-standard-4a-full-month-wage-additions-v1",
        "parameter_set_fingerprint": parameters.fingerprint,
        "earnings_fingerprint": earnings_fingerprint,
        "base_salary": _money(base_salary),
        "wage_like_additions": _money(additions),
        "total_gross_pay": total,
        "payroll": payroll,
    }
    result = PayrollPeriodCalculationResult(**values, fingerprint="")
    result = PayrollPeriodCalculationResult(**{**result.__dict__, "fingerprint": _sha256(result.payload())})
    result.validate()
    return result
