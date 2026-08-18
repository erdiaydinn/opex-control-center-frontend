from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256


@dataclass(frozen=True)
class BudgetTruth:
    budget_base_amount: Decimal
    actual_base_amount: Decimal
    commitment_base_amount: Decimal
    current_forecast_base_amount: Decimal
    scenario_forecast_base_amount: Decimal
    historical_mean_base_amount: Decimal
    historical_stddev_base_amount: Decimal
    drivers: Mapping[str, Decimal]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class BudgetRecommendation:
    suggested_forecast_base_amount: Decimal
    variance_to_budget: Decimal
    variance_to_current_forecast: Decimal
    anomaly: bool
    root_causes: tuple[tuple[str, Decimal], ...]
    sensitivity: tuple[tuple[str, Decimal], ...]
    input_fingerprint: str
    recommendation_only: bool = True


def build_budget_recommendation(truth: BudgetTruth) -> BudgetRecommendation:
    if not truth.provenance or any(not provenance.strip() for provenance in truth.provenance):
        raise ValueError("budget intelligence requires provenance-bound truth")

    suggestion = max(Decimal("0"), truth.scenario_forecast_base_amount)
    variance = suggestion - truth.budget_base_amount
    current_delta = suggestion - truth.current_forecast_base_amount
    threshold = truth.historical_stddev_base_amount * Decimal("3")
    anomaly = (
        truth.historical_stddev_base_amount > 0
        and abs(suggestion - truth.historical_mean_base_amount) > threshold
    )
    root_causes = tuple(
        sorted(
            ((key, value) for key, value in truth.drivers.items() if value != 0),
            key=lambda item: (-abs(item[1]), item[0]),
        )
    )
    total = sum((abs(value) for _, value in root_causes), Decimal("0"))
    sensitivity = tuple(
        (
            key,
            abs(value) / total if total else Decimal("0"),
        )
        for key, value in root_causes
    )
    payload = {
        "budget": str(truth.budget_base_amount),
        "actual": str(truth.actual_base_amount),
        "commitment": str(truth.commitment_base_amount),
        "current_forecast": str(truth.current_forecast_base_amount),
        "scenario_forecast": str(truth.scenario_forecast_base_amount),
        "drivers": [
            (key, str(value))
            for key, value in sorted(truth.drivers.items())
        ],
        "provenance": list(truth.provenance),
    }
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return BudgetRecommendation(
        suggested_forecast_base_amount=suggestion,
        variance_to_budget=variance,
        variance_to_current_forecast=current_delta,
        anomaly=anomaly,
        root_causes=root_causes,
        sensitivity=sensitivity,
        input_fingerprint=fingerprint,
    )
