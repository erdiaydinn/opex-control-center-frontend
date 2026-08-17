from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from typing import Mapping

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
    if not truth.provenance or any(not p.strip() for p in truth.provenance):
        raise ValueError('budget intelligence requires provenance-bound truth')
    suggestion=max(Decimal('0'),truth.scenario_forecast_base_amount)
    variance=suggestion-truth.budget_base_amount
    current_delta=suggestion-truth.current_forecast_base_amount
    threshold=truth.historical_stddev_base_amount*Decimal('3')
    anomaly=truth.historical_stddev_base_amount>0 and abs(suggestion-truth.historical_mean_base_amount)>threshold
    root=tuple(sorted(((k,v) for k,v in truth.drivers.items() if v!=0),key=lambda item:(-abs(item[1]),item[0])))
    total=sum((abs(v) for _,v in root),Decimal('0'))
    sensitivity=tuple((k,(abs(v)/total if total else Decimal('0'))) for k,v in root)
    payload={'budget':str(truth.budget_base_amount),'actual':str(truth.actual_base_amount),'commitment':str(truth.commitment_base_amount),'current_forecast':str(truth.current_forecast_base_amount),'scenario_forecast':str(truth.scenario_forecast_base_amount),'drivers':[(k,str(v)) for k,v in sorted(truth.drivers.items())],'provenance':list(truth.provenance)}
    fp=sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return BudgetRecommendation(suggestion,variance,current_delta,anomaly,root,sensitivity,fp)
