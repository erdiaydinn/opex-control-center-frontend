from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Mapping, Sequence

RateAggregationKind = Literal["ratio_of_sums", "complement_ratio_of_sums"]


@dataclass(frozen=True)
class RateAggregationContract:
    """Pin the denominator lineage for aggregate rate KPIs.

    Aggregate rates such as OTP must be reconstructed from additive numerator and
    denominator fields. Averaging pre-aggregated percentages is intentionally not a
    supported aggregation mode because it changes the metric when group sizes differ.
    """

    metric: str
    numerator_field: str
    denominator_field: str
    aggregation_kind: RateAggregationKind
    output_scale: Literal["percent"] = "percent"

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "numerator_field": self.numerator_field,
            "denominator_field": self.denominator_field,
            "aggregation_kind": self.aggregation_kind,
            "output_scale": self.output_scale,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _decimal(value: object, field: str) -> Decimal:
    if value is None:
        raise ValueError(f"rate_aggregation_missing_value:{field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"rate_aggregation_non_numeric:{field}") from exc
    if not number.is_finite():
        raise ValueError(f"rate_aggregation_non_finite:{field}")
    if number < 0:
        raise ValueError(f"rate_aggregation_negative:{field}")
    return number


def validate_rate_aggregation_contract(contract: RateAggregationContract) -> None:
    if not contract.metric.strip():
        raise ValueError("rate_aggregation_metric_required")
    if not contract.numerator_field.strip() or not contract.denominator_field.strip():
        raise ValueError("rate_aggregation_lineage_field_required")
    if contract.numerator_field == contract.denominator_field:
        raise ValueError("rate_aggregation_numerator_denominator_must_differ")
    if contract.aggregation_kind not in {"ratio_of_sums", "complement_ratio_of_sums"}:
        raise ValueError("rate_aggregation_kind_unsupported")


def aggregate_rate(
    rows: Sequence[Mapping[str, object]],
    *,
    contract: RateAggregationContract,
) -> Decimal:
    """Calculate a global percentage from additive numerator/denominator lineage."""

    validate_rate_aggregation_contract(contract)
    if not rows:
        raise ValueError("rate_aggregation_rows_required")

    numerator = Decimal("0")
    denominator = Decimal("0")
    for row in rows:
        row_numerator = _decimal(row.get(contract.numerator_field), contract.numerator_field)
        row_denominator = _decimal(row.get(contract.denominator_field), contract.denominator_field)
        if row_numerator > row_denominator:
            raise ValueError("rate_aggregation_numerator_exceeds_denominator")
        numerator += row_numerator
        denominator += row_denominator

    if denominator == 0:
        raise ValueError("rate_aggregation_zero_denominator")

    ratio_percent = numerator * Decimal("100") / denominator
    if contract.aggregation_kind == "ratio_of_sums":
        result = ratio_percent
    else:
        result = Decimal("100") - ratio_percent

    if result < 0 or result > 100:
        raise ValueError("rate_aggregation_out_of_bounds")
    return result


def reject_average_of_preaggregated_rates(rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError("rate_aggregation_rows_required")
    raise ValueError("average_of_rates_forbidden:aggregate_from_numerator_denominator")
