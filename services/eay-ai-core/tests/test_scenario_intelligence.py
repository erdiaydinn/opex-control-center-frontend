import pytest

from app.scenario_intelligence import (
    ExecutiveScenario,
    ScenarioPortfolioInput,
    evaluate_scenarios,
)


def _scenario(scenario_id: str, probability: float, financial: float, demand: float):
    return ExecutiveScenario(
        scenario_id=scenario_id,
        label=scenario_id,
        probability=probability,
        financial_impact=financial,
        service_level_impact_pct=0.0,
        demand_impact_pct=demand,
        evidence_refs=(f"evidence://{scenario_id}",),
    )


def test_weighted_weather_event_scenarios_produce_expected_value_and_downside():
    result = evaluate_scenarios(
        ScenarioPortfolioInput(
            scenarios=(
                _scenario("base", 0.50, 0.0, 0.0),
                _scenario("upside", 0.30, 120_000.0, 18.0),
                _scenario("downside", 0.20, -80_000.0, -10.0),
            )
        ),
        severe_downside_threshold=-50_000.0,
    )

    assert result.expected_financial_impact == 20_000.0
    assert result.downside_probability == 0.20
    assert result.severe_downside_probability == 0.20
    assert result.best_case_scenario_id == "upside"
    assert result.worst_case_scenario_id == "downside"
    assert result.most_likely_scenario_id == "base"


def test_probability_mass_must_sum_to_one():
    with pytest.raises(ValueError, match="scenario_probabilities_must_sum_to_one"):
        ScenarioPortfolioInput(
            scenarios=(
                _scenario("a", 0.70, 0.0, 0.0),
                _scenario("b", 0.20, 10.0, 1.0),
            )
        )


def test_duplicate_scenario_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate_scenario_id"):
        ScenarioPortfolioInput(
            scenarios=(
                _scenario("same", 0.50, 0.0, 0.0),
                _scenario("same", 0.50, 10.0, 1.0),
            )
        )
