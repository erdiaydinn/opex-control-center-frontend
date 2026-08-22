"""Evidence-bound company digital twin simulations for Jarvis.

A digital-twin run is a counterfactual decision aid, never production truth and
never an action executor.  It binds every simulation to an exact temporal
WorldSnapshot fingerprint, explicit intervention assumptions, and scenario
probabilities.  If a required baseline field is contradictory or unavailable,
the simulation fails closed rather than inventing a starting state.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .scenario_intelligence import ExecutiveScenario, ScenarioPortfolioInput, evaluate_scenarios
from .world_model import WorldSnapshot

DIGITAL_TWIN_CONTRACT = "eay-company-digital-twin-v1"


class InterventionKind(str, Enum):
    STAFFING = "staffing"
    CAPACITY = "capacity"
    INVENTORY = "inventory"
    PRICING = "pricing"
    PROMOTION = "promotion"
    SUPPLIER = "supplier"
    STORE_CLOSURE = "store_closure"
    PROCESS = "process"
    BUDGET = "budget"
    OTHER = "other"


class InterventionAssumption(BaseModel):
    assumption_id: str = Field(min_length=1)
    statement: str = Field(min_length=3)
    evidence_ref: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class InterventionSpec(BaseModel):
    intervention_id: str = Field(min_length=1)
    kind: InterventionKind
    target_entity_ids: tuple[str, ...] = Field(min_length=1)
    description: str = Field(min_length=3)
    required_baseline_field_keys: tuple[str, ...] = Field(min_length=1)
    assumptions: tuple[InterventionAssumption, ...] = Field(min_length=1)
    reversible: bool = True
    external_side_effect: bool = False


class TwinMetricProjection(BaseModel):
    metric_key: str = Field(min_length=1)
    baseline_value: float
    projected_value: float
    unit: str = Field(min_length=1)
    method_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @property
    def delta(self) -> float:
        return self.projected_value - self.baseline_value


class TwinScenario(BaseModel):
    scenario_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    probability: float = Field(ge=0.0, le=1.0)
    financial_impact: float
    service_level_impact_pct: float = 0.0
    demand_impact_pct: float = 0.0
    projections: tuple[TwinMetricProjection, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class TwinSimulationInput(BaseModel):
    intervention: InterventionSpec
    scenarios: tuple[TwinScenario, ...] = Field(min_length=2)
    probability_tolerance: float = Field(default=0.001, ge=0.0, le=0.05)

    @model_validator(mode="after")
    def probability_mass_and_metric_sets(self) -> "TwinSimulationInput":
        total = sum(item.probability for item in self.scenarios)
        if abs(total - 1.0) > self.probability_tolerance:
            raise ValueError("digital_twin_scenario_probabilities_must_sum_to_one")
        ids = [item.scenario_id for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("digital_twin_duplicate_scenario_id")
        metric_sets = [{projection.metric_key for projection in item.projections} for item in self.scenarios]
        if len({frozenset(item) for item in metric_sets}) != 1:
            raise ValueError("digital_twin_scenarios_must_project_same_metric_set")
        return self


class ExpectedMetricImpact(BaseModel):
    metric_key: str
    expected_delta: float
    expected_projected_value: float
    unit: str


class TwinSimulationResult(BaseModel):
    contract: str = DIGITAL_TWIN_CONTRACT
    intervention_id: str
    tenant_id: str
    world_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_financial_impact: float
    downside_probability: float = Field(ge=0.0, le=1.0)
    expected_metric_impacts: tuple[ExpectedMetricImpact, ...]
    best_case_scenario_id: str
    worst_case_scenario_id: str
    assumption_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence_cap: float = Field(ge=0.0, le=1.0)
    counterfactual_only: bool = True
    forecast_truth_claimed: bool = False
    execution_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def simulation_never_executes_or_claims_truth(self) -> "TwinSimulationResult":
        if self.execution_allowed:
            raise ValueError("digital_twin_never_authorizes_execution")
        if self.forecast_truth_claimed:
            raise ValueError("digital_twin_cannot_claim_forecast_truth")
        return self


def simulate_intervention(
    *,
    snapshot: WorldSnapshot,
    payload: TwinSimulationInput,
) -> TwinSimulationResult:
    intervention = payload.intervention
    blockers: list[str] = []
    entity_ids = {entity.entity_id for entity in snapshot.entities}
    unknown_targets = sorted(set(intervention.target_entity_ids) - entity_ids)
    if unknown_targets:
        blockers.append("digital_twin_target_entity_missing:" + ",".join(unknown_targets))

    field_map = {f"{field.entity_id}:{field.field_name}": field for field in snapshot.fields}
    for key in intervention.required_baseline_field_keys:
        if key in snapshot.blocked_field_keys:
            blockers.append(f"digital_twin_baseline_field_contradictory:{key}")
        elif key not in field_map:
            blockers.append(f"digital_twin_baseline_field_missing:{key}")

    scenario_input = ScenarioPortfolioInput(
        scenarios=tuple(
            ExecutiveScenario(
                scenario_id=item.scenario_id,
                label=item.label,
                probability=item.probability,
                financial_impact=item.financial_impact,
                service_level_impact_pct=item.service_level_impact_pct,
                demand_impact_pct=item.demand_impact_pct,
                evidence_refs=item.evidence_refs,
            )
            for item in payload.scenarios
        ),
        probability_tolerance=payload.probability_tolerance,
    )
    portfolio = evaluate_scenarios(scenario_input)

    expected_metrics: list[ExpectedMetricImpact] = []
    first_projection_map = {item.metric_key: item for item in payload.scenarios[0].projections}
    for metric_key in sorted(first_projection_map):
        projections = [
            (scenario.probability, next(item for item in scenario.projections if item.metric_key == metric_key))
            for scenario in payload.scenarios
        ]
        units = {projection.unit for _, projection in projections}
        baseline_values = {projection.baseline_value for _, projection in projections}
        if len(units) != 1:
            blockers.append(f"digital_twin_metric_unit_mismatch:{metric_key}")
            continue
        if len(baseline_values) != 1:
            blockers.append(f"digital_twin_metric_baseline_mismatch:{metric_key}")
            continue
        baseline = next(iter(baseline_values))
        expected_projected = sum(probability * projection.projected_value for probability, projection in projections)
        expected_metrics.append(
            ExpectedMetricImpact(
                metric_key=metric_key,
                expected_delta=round(expected_projected - baseline, 6),
                expected_projected_value=round(expected_projected, 6),
                unit=next(iter(units)),
            )
        )

    minimum_assumption_confidence = min(item.confidence for item in intervention.assumptions)
    confidence_cap = min(0.90, minimum_assumption_confidence)
    if blockers:
        confidence_cap = min(confidence_cap, 0.40)

    evidence_refs = tuple(
        dict.fromkeys(
            [item.evidence_ref for item in intervention.assumptions]
            + [ref for scenario in payload.scenarios for ref in scenario.evidence_refs]
            + [
                ref
                for scenario in payload.scenarios
                for projection in scenario.projections
                for ref in projection.evidence_refs
            ]
        )
    )
    return TwinSimulationResult(
        intervention_id=intervention.intervention_id,
        tenant_id=snapshot.tenant_id,
        world_snapshot_fingerprint=snapshot.fingerprint,
        expected_financial_impact=portfolio.expected_financial_impact,
        downside_probability=portfolio.downside_probability,
        expected_metric_impacts=tuple(expected_metrics),
        best_case_scenario_id=portfolio.best_case_scenario_id,
        worst_case_scenario_id=portfolio.worst_case_scenario_id,
        assumption_refs=tuple(item.assumption_id for item in intervention.assumptions),
        evidence_refs=evidence_refs,
        confidence_cap=confidence_cap,
        blockers=tuple(dict.fromkeys(blockers)),
    )
