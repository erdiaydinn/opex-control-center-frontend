"""Deterministic scenario war-gaming for EAY Jarvis.

Executive decisions should consider weighted upside/downside cases rather than a
single point estimate. This module aggregates explicit scenarios and reports
expected impact, downside probability and worst-case exposure. Probabilities
and impacts must come from governed callers; the LLM may explain but not invent
the arithmetic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

SCENARIO_INTELLIGENCE_CONTRACT = "eay-scenario-intelligence-v1"


class ExecutiveScenario(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=180)
    label: str = Field(min_length=1, max_length=500)
    probability: float = Field(ge=0.0, le=1.0)
    financial_impact: float
    service_level_impact_pct: float = 0.0
    demand_impact_pct: float = 0.0
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class ScenarioPortfolioInput(BaseModel):
    scenarios: tuple[ExecutiveScenario, ...] = Field(min_length=2)
    probability_tolerance: float = Field(default=0.001, ge=0.0, le=0.05)

    @model_validator(mode="after")
    def validate_probability_mass(self) -> "ScenarioPortfolioInput":
        total = sum(item.probability for item in self.scenarios)
        if abs(total - 1.0) > self.probability_tolerance:
            raise ValueError("scenario_probabilities_must_sum_to_one")
        ids = [item.scenario_id for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_scenario_id")
        return self


class ScenarioPortfolioResult(BaseModel):
    contract: str = SCENARIO_INTELLIGENCE_CONTRACT
    expected_financial_impact: float
    expected_service_level_impact_pct: float
    expected_demand_impact_pct: float
    downside_probability: float = Field(ge=0.0, le=1.0)
    severe_downside_probability: float = Field(ge=0.0, le=1.0)
    best_case_scenario_id: str
    worst_case_scenario_id: str
    most_likely_scenario_id: str
    probability_weighted_abs_exposure: float
    scenario_count: int = Field(ge=2)
    evidence_refs: tuple[str, ...]


def evaluate_scenarios(
    payload: ScenarioPortfolioInput,
    *,
    severe_downside_threshold: float = 0.0,
) -> ScenarioPortfolioResult:
    scenarios = payload.scenarios
    expected_financial = sum(item.probability * item.financial_impact for item in scenarios)
    expected_service = sum(item.probability * item.service_level_impact_pct for item in scenarios)
    expected_demand = sum(item.probability * item.demand_impact_pct for item in scenarios)
    downside_probability = sum(item.probability for item in scenarios if item.financial_impact < 0)
    severe_downside_probability = sum(
        item.probability
        for item in scenarios
        if item.financial_impact < severe_downside_threshold
    )
    best = max(scenarios, key=lambda item: (item.financial_impact, item.scenario_id))
    worst = min(scenarios, key=lambda item: (item.financial_impact, item.scenario_id))
    most_likely = max(scenarios, key=lambda item: (item.probability, item.scenario_id))
    weighted_abs = sum(item.probability * abs(item.financial_impact) for item in scenarios)
    evidence_refs = tuple(
        dict.fromkeys(ref for item in scenarios for ref in item.evidence_refs)
    )

    return ScenarioPortfolioResult(
        expected_financial_impact=round(expected_financial, 6),
        expected_service_level_impact_pct=round(expected_service, 6),
        expected_demand_impact_pct=round(expected_demand, 6),
        downside_probability=round(downside_probability, 6),
        severe_downside_probability=round(severe_downside_probability, 6),
        best_case_scenario_id=best.scenario_id,
        worst_case_scenario_id=worst.scenario_id,
        most_likely_scenario_id=most_likely.scenario_id,
        probability_weighted_abs_exposure=round(weighted_abs, 6),
        scenario_count=len(scenarios),
        evidence_refs=evidence_refs,
    )
