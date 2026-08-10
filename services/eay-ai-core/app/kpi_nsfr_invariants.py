from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping


NSFR_REQUIRED_FIELDS = (
    "successful_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
)

NSFR_RATE_FIELDS = {
    "pfr_rate_percent": "pfr_orders",
    "refund_rate_percent": "refund_orders",
    "compensation_rate_percent": "compensation_orders",
    "nsfr_rate_percent": "nsfr_orders",
}

# Reviewed output precision for aggregate KPI rates. Query templates that expose a
# rate must round HALF_UP to exactly this scale; no epsilon/tolerance comparison is
# permitted because silent drift would hide denominator or precedence mistakes.
NSFR_RATE_DECIMAL_PLACES = 6
NSFR_RATE_QUANTUM = Decimal("1").scaleb(-NSFR_RATE_DECIMAL_PLACES)


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

    def expected_rate_percent(self, count: Decimal) -> Decimal:
        if self.successful_orders == 0:
            return Decimal("0").quantize(NSFR_RATE_QUANTUM)
        raw = (count / self.successful_orders) * Decimal("100")
        return raw.quantize(NSFR_RATE_QUANTUM, rounding=ROUND_HALF_UP)

    @property
    def nsfr_rate_percent(self) -> Decimal:
        return self.expected_rate_percent(self.nsfr_orders)


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


def _reconcile_optional_rates(
    row: Mapping[str, object], result: NsfrInvariantResult
) -> None:
    for rate_field, count_field in NSFR_RATE_FIELDS.items():
        if rate_field not in row:
            continue
        observed = _non_negative_decimal(row, rate_field)
        if observed > Decimal("100"):
            raise ValueError(f"nsfr_invariant_rate_out_of_bounds:{rate_field}")
        exponent = observed.as_tuple().exponent
        decimal_places = max(0, -exponent)
        if decimal_places > NSFR_RATE_DECIMAL_PLACES:
            raise ValueError(
                "nsfr_invariant_rate_precision_exceeded:"
                f"field={rate_field}:max_dp={NSFR_RATE_DECIMAL_PLACES}:observed_dp={decimal_places}"
            )
        count = getattr(result, count_field)
        expected = result.expected_rate_percent(count)
        observed_normalized = observed.quantize(NSFR_RATE_QUANTUM)
        if observed_normalized != expected:
            raise ValueError(
                "nsfr_invariant_rate_reconciliation_mismatch:"
                f"field={rate_field}:expected={expected}:observed={observed_normalized}"
            )


def verify_nsfr_row(row: Mapping[str, object]) -> NsfrInvariantResult:
    """Fail closed when an aggregate NSFR row violates reviewed business semantics.

    The row contract assumes that upstream classification has already applied the
    precedence PFR > Refund > Compensation, so the three component counts must be
    mutually exclusive and sum exactly to nsfr_orders. All affected counts must also
    be bounded by successful_orders, which is the reviewed denominator for this KPI
    family. If query output includes rate columns, each rate is recomputed from the
    reviewed denominator and compared exactly at the explicit six-decimal precision.
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

    _reconcile_optional_rates(row, result)
    return result
