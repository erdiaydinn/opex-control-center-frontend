from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Mapping, Sequence

AggregationGrain = Literal["order", "picker_day", "event"]


@dataclass(frozen=True)
class WeightedAverageContract:
    metric: str
    source_grain: AggregationGrain
    value_field: str
    weight_field: str | None
    output_unit: str

    @property
    def fingerprint(self) -> str:
        payload = {
            "metric": self.metric,
            "source_grain": self.source_grain,
            "value_field": self.value_field,
            "weight_field": self.weight_field,
            "output_unit": self.output_unit,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _decimal(value: object, field: str) -> Decimal:
    if value is None:
        raise ValueError(f"aggregation_missing_value:{field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"aggregation_non_numeric:{field}") from exc
    if not number.is_finite():
        raise ValueError(f"aggregation_non_finite:{field}")
    if number < 0:
        raise ValueError(f"aggregation_negative:{field}")
    return number


def validate_weighted_average_contract(contract: WeightedAverageContract) -> None:
    if not contract.metric.strip() or not contract.value_field.strip() or not contract.output_unit.strip():
        raise ValueError("aggregation_contract_required_field_missing")
    if contract.source_grain == "picker_day" and not contract.weight_field:
        raise ValueError("aggregation_weight_required_for_picker_day")
    if contract.source_grain == "event" and contract.weight_field:
        raise ValueError("aggregation_event_weight_must_be_implicit")


def aggregate_duration(
    rows: Sequence[Mapping[str, object]],
    *,
    contract: WeightedAverageContract,
) -> Decimal:
    """Aggregate durations without permitting average-of-averages drift.

    Order/event-grain rows are averaged directly. Picker-day aggregates must carry an
    explicit eligible-order weight; unweighted averaging of picker-day means is blocked.
    """

    validate_weighted_average_contract(contract)
    if not rows:
        raise ValueError("aggregation_rows_required")

    if contract.source_grain in {"order", "event"}:
        values = [_decimal(row.get(contract.value_field), contract.value_field) for row in rows]
        return sum(values, Decimal("0")) / Decimal(len(values))

    assert contract.source_grain == "picker_day"
    assert contract.weight_field is not None
    weighted_sum = Decimal("0")
    total_weight = Decimal("0")
    for row in rows:
        value = _decimal(row.get(contract.value_field), contract.value_field)
        weight = _decimal(row.get(contract.weight_field), contract.weight_field)
        if weight == 0:
            continue
        weighted_sum += value * weight
        total_weight += weight
    if total_weight == 0:
        raise ValueError("aggregation_zero_total_weight")
    return weighted_sum / total_weight


def reject_unweighted_picker_day_average(rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError("aggregation_rows_required")
    raise ValueError("average_of_averages_forbidden:picker_day_requires_order_weight")
