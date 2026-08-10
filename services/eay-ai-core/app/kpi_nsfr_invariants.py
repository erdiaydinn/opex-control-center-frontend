from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


NSFR_REQUIRED_FIELDS = (
    "successful_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
)


@dataclass(frozen=True)
class NsfrInvariantResult:
    successful_orders: Decimal
    pfr_orders: Decimal
    refund_orders: Decimal
    compensation_orders: Decimal
    nsfr_orders: Decimal

    @property
    def expected_nsfr_orders(self) -> Decimal:
        return self.pfr_orders + self.refund_orders + self.compensation_orders

    @property
    def nsfr_rate_percent(self) -> Decimal:
        if self.successful_orders == 0:
            return Decimal("0")
        return (self.nsfr_orders / self.successful_orders) * Decimal("100")


def _non_negative_decimal(row: Mapping[str, object], field: str) -> Decimal:
    if field not in row or row[field] is None:
        raise ValueError(f"nsfr_invariant_missing_field:{field}")
    try:
        value = Decimal(str(row[field]))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"nsfr_invariant_non_numeric:{field}") from exc
    if not value.is_finite():
        raise ValueError(f"nsfr_invariant_non_finite:{field}")
    if value < 0:
        raise ValueError(f"nsfr_invariant_negative:{field}")
    return value


def verify_nsfr_row(row: Mapping[str, object]) -> NsfrInvariantResult:
    """Fail closed when an aggregate NSFR row violates reviewed business semantics.

    The row contract assumes that upstream classification has already applied the
    precedence PFR > Refund > Compensation, so the three component counts must be
    mutually exclusive and sum exactly to nsfr_orders. All affected counts must also
    be bounded by successful_orders, which is the reviewed denominator for this KPI
    family.
    """

    values = {field: _non_negative_decimal(row, field) for field in NSFR_REQUIRED_FIELDS}
    result = NsfrInvariantResult(**values)

    for field in ("pfr_orders", "refund_orders", "compensation_orders", "nsfr_orders"):
        if values[field] > result.successful_orders:
            raise ValueError(f"nsfr_invariant_exceeds_denominator:{field}")

    if result.expected_nsfr_orders != result.nsfr_orders:
        raise ValueError(
            "nsfr_invariant_precedence_sum_mismatch:"
            f"expected={result.expected_nsfr_orders}:observed={result.nsfr_orders}"
        )

    return result
