"""Internal/service composition for roadmap 15/60 intraday what-if."""

from __future__ import annotations

from .replan_authority import (
    ReplanScenario,
    ReplanScenarioRequest,
    ScenarioShock,
    build_replan_scenario,
)
from .replan_repository import (
    load_approved_replan_model,
    load_latest_replan_baseline,
    persist_replan_scenario_and_proposal,
)


def compute_and_persist_replan_scenario(
    *,
    location_id: str,
    model_version: str,
    shocks: tuple[ScenarioShock, ...],
    actor_subject: str,
) -> tuple[ReplanScenario, dict[str, object]]:
    tenant_id, baseline = load_latest_replan_baseline(location_id)
    sensitivities, cost_assumption, _model_authority_fingerprint = load_approved_replan_model(
        model_version
    )
    request = ReplanScenarioRequest(
        tenant_id=tenant_id,
        location_id=location_id,
        model_version=model_version,
        baseline=baseline,
        shocks=shocks,
        kpi_sensitivities=sensitivities,
        cost_assumption=cost_assumption,
    )
    scenario = build_replan_scenario(request)
    receipt = persist_replan_scenario_and_proposal(
        scenario,
        baseline=baseline,
        actor_subject=actor_subject,
    )
    return scenario, receipt
