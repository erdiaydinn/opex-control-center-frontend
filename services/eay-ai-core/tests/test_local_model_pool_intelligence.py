from pathlib import Path

import pytest

from app.local_model_pool import (
    CommercialUseStatus,
    LocalCapability,
    LocalModelCatalog,
    LocalModelCatalogEntry,
    LocalModelDeployment,
    LocalModelTask,
    load_local_model_catalog,
    select_local_model,
)

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"


def _deployment(**updates):
    payload = dict(
        deployment_id="local:qwen:1",
        model_family="qwen3-coder",
        model_id="qwen3-coder",
        runtime="OLLAMA",
        endpoint_ref="runtime://ollama/local",
        enabled=True,
        runtime_reachable=True,
        benchmark_score=0.91,
        benchmark_evidence_ref="benchmark://local/qwen3-coder/1",
        observed_capabilities=frozenset(
            {
                LocalCapability.TEXT,
                LocalCapability.CODE,
                LocalCapability.REASONING,
                LocalCapability.TOOL_PLANNING,
                LocalCapability.AGENTIC,
            }
        ),
        max_context_tokens=65536,
        hardware_profile_ref="hardware://dev-gpu/1",
    )
    payload.update(updates)
    return LocalModelDeployment(**payload)


def _task(**updates):
    payload = dict(
        task_ref="task:repo-review",
        task_class="CODE",
        required_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.CODE}),
        minimum_benchmark_score=0.80,
        minimum_context_tokens=32000,
    )
    payload.update(updates)
    return LocalModelTask(**payload)


def test_catalog_loads_and_keeps_conditional_license_models_out_of_production():
    catalog = load_local_model_catalog(CATALOG_PATH)
    by_family = catalog.by_family()

    assert by_family["qwen3-coder"].production_candidate is True
    assert by_family["gpt-oss-20b"].production_candidate is True
    assert by_family["mistral-small-4"].production_candidate is True
    assert by_family["gemma"].production_candidate is False
    assert by_family["deepseek"].production_candidate is False


def test_conditional_license_cannot_be_mislabeled_as_production_candidate():
    with pytest.raises(
        ValueError,
        match="local_model_production_candidate_requires_reviewed_commercial_posture",
    ):
        LocalModelCatalogEntry(
            model_family="conditional-model",
            recommended_runtime="OLLAMA",
            license="CUSTOM",
            commercial_use_status=CommercialUseStatus.CONDITIONAL_LEGAL_REVIEW_REQUIRED,
            capabilities=frozenset({LocalCapability.TEXT}),
            preferred_tasks=frozenset({"GENERAL"}),
            production_candidate=True,
            external_network_required=False,
        )


def test_enabled_local_model_requires_runtime_and_benchmark_evidence():
    with pytest.raises(
        ValueError,
        match="local_model_enabled_deployment_requires_reachable_runtime",
    ):
        _deployment(runtime_reachable=False)

    with pytest.raises(
        ValueError,
        match="local_model_enabled_deployment_requires_benchmark_evidence",
    ):
        _deployment(benchmark_score=None, benchmark_evidence_ref=None)


def test_local_task_prefers_task_specialist_and_requires_no_paid_frontier():
    catalog = load_local_model_catalog(CATALOG_PATH)
    general = _deployment(
        deployment_id="local:eay:1",
        model_family="eay-ops",
        model_id="eay-ops:0.1",
        benchmark_score=0.95,
        benchmark_evidence_ref="benchmark://local/eay/1",
        observed_capabilities=frozenset(
            {LocalCapability.TEXT, LocalCapability.CODE, LocalCapability.RETRIEVAL_SYNTHESIS, LocalCapability.OPS_REASONING}
        ),
    )
    coding = _deployment()

    selection = select_local_model(task=_task(), deployments=(general, coding), catalog=catalog)

    assert selection.local_execution_available is True
    assert selection.paid_frontier_escalation_required is False
    assert selection.model_family == "qwen3-coder"
    assert selection.model_id == "qwen3-coder"


def test_unbenchmarked_or_capability_incomplete_local_pool_escalates_but_does_not_authorize_spend():
    catalog = load_local_model_catalog(CATALOG_PATH)
    disabled = _deployment(enabled=False, runtime_reachable=False, benchmark_score=None, benchmark_evidence_ref=None, observed_capabilities=frozenset())

    selection = select_local_model(
        task=_task(required_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.IMAGE})),
        deployments=(disabled,),
        catalog=catalog,
    )

    assert selection.local_execution_available is False
    assert selection.paid_frontier_escalation_required is True
    assert selection.deployment_id is None
    assert "local_model_deployment_not_active" in selection.blockers
    # This module never grants paid frontier authority; it only declares that a
    # local solution was not available. Admin paid-token governance remains the
    # sole spend authorization boundary.
    assert not hasattr(selection, "paid_token_authorized")


def test_context_and_benchmark_floors_fail_closed():
    catalog = load_local_model_catalog(CATALOG_PATH)
    selection = select_local_model(
        task=_task(minimum_benchmark_score=0.95, minimum_context_tokens=131072),
        deployments=(_deployment(),),
        catalog=catalog,
    )

    assert selection.local_execution_available is False
    assert "local_model_benchmark_below_task_floor" in selection.blockers
    assert "local_model_context_window_insufficient" in selection.blockers


def test_catalog_cannot_contain_duplicate_model_families():
    item = LocalModelCatalogEntry(
        model_family="same",
        recommended_runtime="OLLAMA",
        license="APACHE-2.0",
        commercial_use_status=CommercialUseStatus.PERMISSIVE_LICENSE_REVIEWED,
        capabilities=frozenset({LocalCapability.TEXT}),
        preferred_tasks=frozenset({"GENERAL"}),
        production_candidate=True,
    )
    with pytest.raises(ValueError, match="local_model_catalog_duplicate_family"):
        LocalModelCatalog(version=1, models=(item, item))
